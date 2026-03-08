import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("sonyaproxy.yandex_music")


async def check_token(token: str) -> bool:
    try:
        from yandex_music import ClientAsync
        client = await ClientAsync(token).init()
        return client.me is not None
    except Exception:
        return False


async def search_yandex(token: str, query: str, limit: int = 10) -> list[dict[str, Any]]:
    if not token:
        return []
    try:
        from yandex_music import ClientAsync
        client = await ClientAsync(token).init()
        result = await client.search(query)
        if not result or not result.tracks or not result.tracks.results:
            return []

        tracks = []
        for t in result.tracks.results[:limit]:
            artists = ", ".join(a.name for a in (t.artists or []))
            album = t.albums[0].title if t.albums else "Yandex Music"
            tracks.append({
                "id": f"virt_ym_{t.id}",
                "title": t.title or "",
                "artist": artists or "Unknown",
                "album": album,
                "duration": (t.duration_ms or 0) / 1000,
                "source": "ym",
                "source_id": str(t.id),
                "ym_track_id": t.id,
            })
        return tracks
    except Exception:
        logger.warning("Yandex Music search failed", exc_info=True)
        return []


async def download_yandex(
    token: str, track_id: int, artist: str, title: str, output_dir: Path
) -> str | None:
    if not token:
        return None
    try:
        from yandex_music import ClientAsync
        client = await ClientAsync(token).init()

        track_list = await client.tracks([track_id])
        if not track_list:
            logger.error("YM track %s not found", track_id)
            return None

        track = track_list[0]
        output_dir.mkdir(parents=True, exist_ok=True)

        import re
        safe = lambda s: re.sub(r'[<>:"/\\|?*]', '_', s)
        filename = f"{safe(artist)} - {safe(title)}__ym_{track_id}.mp3"
        filepath = output_dir / filename

        await track.download_async(str(filepath), codec="mp3", bitrate_in_kbps=320)
        logger.info("YM downloaded: %s -> %s", track_id, filepath)
        return str(filepath)
    except Exception:
        logger.warning("Yandex Music download failed for %s", track_id, exc_info=True)
        return None
