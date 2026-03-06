import asyncio
from typing import Any
import musicbrainzngs

musicbrainzngs.set_useragent("sonyaproxy", "0.1", "https://github.com/sonyaproxy")


def _search_sync(artist: str, title: str) -> dict | None:
    """Синхронный поиск в MusicBrainz (запускается в thread)."""
    try:
        result = musicbrainzngs.search_recordings(
            query=f"{artist} {title}", limit=1
        )
        recordings = result.get("recording-list", [])
        if not recordings:
            return None
        rec = recordings[0]
        releases = rec.get("release-list", [])
        release = releases[0] if releases else {}
        return {
            "album": release.get("title"),
            "year": release.get("date", "")[:4] or None,
        }
    except Exception:
        return None


async def enrich_track(track: dict[str, Any]) -> dict[str, Any]:
    """Обогатить виртуальный трек метаданными из MusicBrainz."""
    mb_data = await asyncio.to_thread(
        _search_sync, track.get("artist", ""), track.get("title", "")
    )
    if mb_data:
        enriched = dict(track)
        if mb_data.get("album"):
            enriched["album"] = mb_data["album"]
        if mb_data.get("year"):
            enriched["year"] = mb_data["year"]
        return enriched
    return track


async def enrich_tracks(tracks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Параллельное обогащение списка треков."""
    return list(await asyncio.gather(*[enrich_track(t) for t in tracks]))
