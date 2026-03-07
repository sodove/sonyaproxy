import asyncio
import json
from typing import Any

import httpx

from config import settings

_YTMUSIC_API = "https://music.youtube.com/youtubei/v1/browse"
_YTMUSIC_CONTEXT = {
    "client": {
        "clientName": "WEB_REMIX",
        "clientVersion": "1.20231204.01.00",
    }
}


async def _fetch_chart_browse(region: str) -> dict:
    """POST to YT Music browse API for charts in a region."""
    payload = {
        "browseId": "FEmusic_charts",
        "context": _YTMUSIC_CONTEXT,
    }
    params = {"key": "AIzaSyC9XL3ZjWddXya6X74dJoCTL-WEYFDNX30"}
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://music.youtube.com",
        "Referer": "https://music.youtube.com/",
        "X-Goog-Visitor-Id": "",
    }
    if region:
        payload["context"]["client"]["gl"] = region

    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _YTMUSIC_API, json=payload, params=params, headers=headers
        )
        r.raise_for_status()
        return r.json()


def _extract_playlist_ids(data: dict) -> list[str]:
    """Walk the browse response to find chart playlist browseIds (VL...)."""
    ids = []
    _walk_for_playlists(data, ids)
    return ids


def _walk_for_playlists(obj: Any, result: list[str]):
    if isinstance(obj, dict):
        browse_id = obj.get("browseId", "")
        if isinstance(browse_id, str) and browse_id.startswith("VL"):
            result.append(browse_id)
        for v in obj.values():
            _walk_for_playlists(v, result)
    elif isinstance(obj, list):
        for item in obj:
            _walk_for_playlists(item, result)


async def _fetch_playlist_tracks(playlist_id: str, limit: int) -> list[dict]:
    """Use yt-dlp --flat-playlist to get tracks from a YouTube playlist."""
    # Strip VL prefix to get the real playlist ID
    yt_playlist_id = playlist_id[2:] if playlist_id.startswith("VL") else playlist_id
    url = f"https://www.youtube.com/playlist?list={yt_playlist_id}"

    cmd = [
        settings.ytdlp_path,
        url,
        "--flat-playlist",
        "--print", "%()j",
        "--no-warnings",
        "--playlist-end", str(limit),
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()

    tracks = []
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
        tracks.append({
            "url": entry.get("webpage_url", entry.get("url", "")),
            "title": entry.get("title", "Unknown"),
            "artist": entry.get("uploader", entry.get("channel", "Unknown")),
            "duration": entry.get("duration", 0),
            "source_id": raw_id,
            "source": "yt",
        })
    return tracks


async def fetch_ytmusic_chart(region: str, limit: int = 20) -> list[dict]:
    """Fetch trending tracks from YT Music charts for a region.

    1. Browse FEmusic_charts for region
    2. Extract first playlist ID
    3. Fetch tracks via yt-dlp
    """
    data = await _fetch_chart_browse(region)
    playlist_ids = _extract_playlist_ids(data)
    if not playlist_ids:
        return []
    # Use first chart playlist (usually "Top songs" / "Trending")
    return await _fetch_playlist_tracks(playlist_ids[0], limit)
