import asyncio, json, logging
from typing import Any
from app.normalizer import normalize
from app.config import settings

logger = logging.getLogger("sonyaproxy.ytdlp")

_SUBPROCESS_TIMEOUT = 15


async def _search_source(prefix: str, query: str, count: int) -> list[dict[str, Any]]:
    cmd = [
        settings.ytdlp_path,
        f"{prefix}{count}:{query}",
        "--flat-playlist",
        "--print", "%()j",
        "--no-warnings",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=_SUBPROCESS_TIMEOUT)
    except asyncio.TimeoutError:
        proc.kill()
        logger.warning("%s search timed out after %ds", prefix, _SUBPROCESS_TIMEOUT)
        return []

    source = "yt" if prefix.startswith("yt") else "sc"
    results = []
    for line in stdout.decode().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        raw_id = entry.get("id", "")
        if not raw_id:
            continue
        virt_id = f"virt_{source}_{raw_id}"
        results.append({
            "id": virt_id,
            "title": entry.get("title", "Unknown"),
            "artist": entry.get("uploader", "Unknown"),
            "album": "YouTube" if source == "yt" else "SoundCloud",
            "duration": entry.get("duration", 0),
            "youtube_url": entry.get("webpage_url", ""),
        })
    return results


async def search_virtual(query: str, count: int = 10) -> list[dict[str, Any]]:
    yt_task = asyncio.create_task(_search_source("ytsearch", query, count))
    sc_task = asyncio.create_task(_search_source("scsearch", query, count))
    results = await asyncio.gather(yt_task, sc_task, return_exceptions=True)

    seen: set[str] = set()
    merged = []
    for batch in results:
        if isinstance(batch, BaseException):
            logger.warning("Search source failed: %s", batch)
            continue
        for track in batch:
            key = normalize(f"{track['artist']} {track['title']}")
            if key not in seen:
                seen.add(key)
                merged.append(track)

    return merged
