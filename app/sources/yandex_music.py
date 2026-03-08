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
    token: str, track_id: int, artist: str = "", title: str = "", output_dir: Path | None = None
) -> dict | None:
    """Download track from YM. Returns {"path": str, "artist": str, "title": str, "album": str} or None."""
    if not token:
        return None
    try:
        import asyncio, re
        from yandex_music import ClientAsync
        client = await ClientAsync(token).init()

        track_list = await client.tracks([track_id])
        if not track_list:
            logger.error("YM track %s not found", track_id)
            return None

        track = track_list[0]

        # Use metadata from YM API
        real_artist = ", ".join(a.name for a in (track.artists or [])) or artist or "Unknown"
        real_title = track.title or title or str(track_id)
        real_album = track.albums[0].title if track.albums else "Yandex Music"

        if output_dir is None:
            output_dir = Path("/music/Virtual Downloads") / _safe(real_artist) / "Singles"
        output_dir.mkdir(parents=True, exist_ok=True)

        filename = f"{_safe(real_artist)} - {_safe(real_title)}__ym_{track_id}.mp3"
        filepath = output_dir / filename

        # Skip if already downloaded
        if filepath.exists() and filepath.stat().st_size > 0:
            logger.info("YM already exists: %s", filepath)
            return {"path": str(filepath), "artist": real_artist, "title": real_title, "album": real_album}

        # Download with retry (YM CDN drops connections sometimes)
        last_err = None
        for attempt in range(3):
            try:
                await track.download_async(str(filepath), codec="mp3", bitrate_in_kbps=320)
                last_err = None
                break
            except Exception as e:
                last_err = e
                logger.warning("YM download attempt %d/3 failed for %s: %s", attempt + 1, track_id, e)
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)

        # Fallback: try without codec preference if mp3 failed
        if last_err:
            logger.info("YM mp3 failed for %s, trying default codec", track_id)
            try:
                await track.download_async(str(filepath))
                last_err = None
            except Exception as e:
                logger.warning("YM fallback download also failed for %s: %s", track_id, e)
                raise last_err

        # Write ID3 tags via ffmpeg
        tagged = str(filepath) + ".tagged.mp3"
        tag_cmd = [
            "ffmpeg", "-y", "-i", str(filepath),
            "-c", "copy",
            "-metadata", f"artist={real_artist}",
            "-metadata", f"title={real_title}",
            "-metadata", f"album={real_album}",
            tagged,
        ]
        proc = await asyncio.create_subprocess_exec(
            *tag_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        if proc.returncode == 0:
            Path(tagged).replace(filepath)

        logger.info("YM downloaded: %s - %s -> %s", real_artist, real_title, filepath)
        return {"path": str(filepath), "artist": real_artist, "title": real_title, "album": real_album}
    except Exception:
        logger.warning("Yandex Music download failed for %s", track_id, exc_info=True)
        return None


def _safe(s: str) -> str:
    import re
    return re.sub(r'[<>:"/\\|?*]', '_', s)
