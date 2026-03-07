import asyncio
import logging
from typing import Any

from normalizer import normalize
from ytmusic import fetch_ytmusic_chart
from sc_charts import fetch_sc_chart, _SUPPORTED_REGIONS

logger = logging.getLogger("sonyaproxy.charts")


async def fetch_all_charts(quotas: list[dict]) -> list[dict[str, Any]]:
    """Fetch charts from YT Music + SoundCloud, merge and dedup.

    - YT Music: one chart per unique region (returns trending for that region)
    - SoundCloud: one chart per genre+region (only US/UK)
    - Dedup by normalize(artist + title)
    - return_exceptions=True so one source failing doesn't break the other
    """
    tasks: list[asyncio.Task] = []

    # YT Music: one request per unique region
    seen_regions: set[str] = set()
    total_per_region: dict[str, int] = {}
    for q in quotas:
        region = q["region"]
        total_per_region[region] = total_per_region.get(region, 0) + q["count"]

    for region, count in total_per_region.items():
        if region not in seen_regions:
            seen_regions.add(region)
            tasks.append(asyncio.ensure_future(
                fetch_ytmusic_chart(region, limit=count)
            ))

    # SoundCloud: one per genre+region (only supported regions)
    seen_sc: set[tuple[str, str]] = set()
    for q in quotas:
        genre, region = q["genre"], q["region"]
        if region in _SUPPORTED_REGIONS and (genre, region) not in seen_sc:
            seen_sc.add((genre, region))
            tasks.append(asyncio.ensure_future(
                fetch_sc_chart(genre, region, limit=q["count"])
            ))

    if not tasks:
        return []

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Merge + dedup
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
