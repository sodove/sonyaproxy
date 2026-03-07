import asyncio
import logging
import re
from datetime import datetime

from app.autopop.flavor import FlavorConfig, load_flavor, compute_quotas
from app.autopop.charts import fetch_all_charts
from app.index import TrackIndex
from app.downloader import DownloadQueue
from app.normalizer import normalize

logger = logging.getLogger("sonyaproxy.autopop")

_CYRILLIC_RE = re.compile(r'[\u0400-\u04FF]')


def _detect_language(text: str) -> str:
    return "ru" if _CYRILLIC_RE.search(text) else "en"


def _apply_language_filter(
    tracks: list[dict], language_weights: dict[str, float], max_count: int
) -> list[dict]:
    buckets: dict[str, list[dict]] = {}
    for t in tracks:
        lang = _detect_language(f"{t.get('artist', '')} {t.get('title', '')}")
        if lang not in language_weights:
            lang = "other"
        buckets.setdefault(lang, []).append(t)

    weight_sum = sum(language_weights.values()) or 1.0
    result = []
    allocated = 0
    langs = list(language_weights.keys())
    for i, lang in enumerate(langs):
        w = language_weights[lang]
        if i < len(langs) - 1:
            limit = int(max_count * w / weight_sum)
        else:
            limit = max_count - allocated
        picked = buckets.get(lang, [])[:limit]
        result.extend(picked)
        allocated += len(picked)

    return result[:max_count]


async def run_autopop_cycle(
    track_index: TrackIndex,
    download_queue: DownloadQueue,
    flavor: FlavorConfig,
) -> int:
    quotas = compute_quotas(flavor)
    if not quotas:
        return 0

    candidates = await fetch_all_charts(quotas)
    logger.info("Fetched %d chart candidates", len(candidates))

    # Filter out tracks already in index (title-only key to match index.upsert)
    new_tracks = []
    for t in candidates:
        if not await track_index.exists_normalized(t["title"]):
            new_tracks.append(t)

    logger.info("%d new tracks after dedup", len(new_tracks))

    filtered = _apply_language_filter(
        new_tracks, flavor.languages, flavor.max_tracks_per_cycle
    )

    downloaded = 0
    for t in filtered[:flavor.max_tracks_per_cycle]:
        virt_id = f"virt_{t['source']}_{t['source_id']}"
        try:
            await download_queue.download(
                virt_id=virt_id,
                youtube_url=t["url"],
                artist=t["artist"],
                title=t["title"],
                trigger_rescan=False,
            )
            await track_index.upsert(
                id=virt_id,
                artist=t["artist"],
                album="Auto-Populate",
                title=t["title"],
            )
            downloaded += 1
        except Exception:
            logger.warning("Failed to download %s - %s", t["artist"], t["title"], exc_info=True)

    if downloaded > 0:
        await download_queue.trigger_rescan()
        logger.info("Auto-populated %d tracks, rescan triggered", downloaded)

    return downloaded


def _is_boost_day(flavor: FlavorConfig) -> bool:
    today = datetime.now().strftime("%A").lower()
    return today in flavor.release_day_boost.days


async def autopop_loop(
    track_index: TrackIndex,
    download_queue: DownloadQueue,
    flavor_path: str,
):
    while True:
        flavor = load_flavor(flavor_path)
        boost = _is_boost_day(flavor)
        if boost:
            original_max = flavor.max_tracks_per_cycle
            flavor.max_tracks_per_cycle = int(
                original_max * flavor.release_day_boost.track_multiplier
            )
            logger.info(
                "Boost day! max_tracks: %d -> %d",
                original_max, flavor.max_tracks_per_cycle,
            )
        try:
            count = await run_autopop_cycle(track_index, download_queue, flavor)
            logger.info("Auto-populate cycle done: %d tracks", count)
        except Exception:
            logger.exception("Auto-populate cycle failed")
        sleep_hours = (
            flavor.release_day_boost.interval_hours
            if boost
            else flavor.refresh_interval_hours
        )
        await asyncio.sleep(sleep_hours * 3600)
