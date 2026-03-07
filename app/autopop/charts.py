import asyncio
import logging
from typing import Any

from app.normalizer import normalize
from app.sources.ytmusic import fetch_ytmusic_chart
from app.sources.sc_charts import fetch_sc_chart, _SUPPORTED_REGIONS

logger = logging.getLogger("sonyaproxy.charts")


async def fetch_all_charts(quotas: list[dict]) -> list[dict[str, Any]]:
    # YT Music: parallel per region
    yt_tasks: list[asyncio.Task] = []
    total_per_region: dict[str, int] = {}
    for q in quotas:
        region = q["region"]
        total_per_region[region] = total_per_region.get(region, 0) + q["count"]

    for region, count in total_per_region.items():
        yt_tasks.append(asyncio.ensure_future(
            fetch_ytmusic_chart(region, limit=count)
        ))

    # SoundCloud: collect unique genre+region pairs, run sequentially below
    sc_jobs: list[tuple[str, str, int]] = []
    seen_sc: set[tuple[str, str]] = set()
    for q in quotas:
        genre, region = q["genre"], q["region"]
        if region in _SUPPORTED_REGIONS and (genre, region) not in seen_sc:
            seen_sc.add((genre, region))
            sc_jobs.append((genre, region, q["count"]))

    # Run YT and SC concurrently, but SC charts are sequential among themselves
    async def _fetch_sc_sequential() -> list[dict]:
        all_tracks: list[dict] = []
        for genre, region, count in sc_jobs:
            try:
                tracks = await fetch_sc_chart(genre, region, limit=count)
                all_tracks.extend(tracks)
            except Exception as e:
                logger.warning("SC chart failed (%s/%s): %s", genre, region, e)
        return all_tracks

    results = await asyncio.gather(
        *yt_tasks,
        _fetch_sc_sequential(),
        return_exceptions=True,
    )

    seen: set[str] = set()
    merged: list[dict] = []
    for batch in results:
        if isinstance(batch, BaseException):
            logger.warning("Chart source failed: %s", batch)
            continue
        for track in batch:
            key = normalize(f"{track['artist']} {track['title']}")
            if key not in seen:
                seen.add(key)
                merged.append(track)

    return merged
