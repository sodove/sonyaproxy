import asyncio, json
from typing import Any
from normalizer import normalize
from config import settings


async def _search_source(prefix: str, query: str, count: int) -> list[dict[str, Any]]:
    """Поиск через yt-dlp для одного источника (ytsearch / scsearch)."""
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
    stdout, _ = await proc.communicate()

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
    """Параллельный поиск на YouTube и SoundCloud с дедупликацией."""
    yt_task = asyncio.create_task(_search_source("ytsearch", query, count))
    sc_task = asyncio.create_task(_search_source("scsearch", query, count))
    yt_results, sc_results = await asyncio.gather(yt_task, sc_task)

    # Дедупликация: YT первыми, SC — только если нет аналога из YT
    seen: set[str] = set()
    merged = []
    for track in yt_results:
        key = normalize(f"{track['artist']} {track['title']}")
        if key not in seen:
            seen.add(key)
            merged.append(track)

    for track in sc_results:
        key = normalize(f"{track['artist']} {track['title']}")
        if key not in seen:
            seen.add(key)
            merged.append(track)

    return merged
