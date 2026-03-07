import json
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.sources.ytmusic import (
    fetch_ytmusic_chart,
    _extract_playlist_ids,
    _fetch_playlist_tracks,
)


def _make_browse_response(playlist_ids: list[str]) -> dict:
    items = []
    for pid in playlist_ids:
        items.append({
            "musicCarouselShelfRenderer": {
                "header": {"browseId": pid},
                "contents": [],
            }
        })
    return {
        "contents": {
            "singleColumnBrowseResultsRenderer": {
                "tabs": [{"tabRenderer": {"content": {"sectionListRenderer": {"contents": items}}}}]
            }
        }
    }


def _make_ytdlp_entry(vid_id, title, uploader):
    return json.dumps({
        "id": vid_id,
        "title": title,
        "uploader": uploader,
        "duration": 210,
        "webpage_url": f"https://www.youtube.com/watch?v={vid_id}",
    })


def _mock_exec_factory(output: str):
    async def mock_exec(*args, **kwargs):
        class P:
            stdout = output.encode()
            returncode = 0
            async def communicate(self_p):
                return self_p.stdout, b""
        return P()
    return mock_exec


def test_extract_playlist_ids():
    data = _make_browse_response(["VLPL_top50", "VLPL_trending"])
    ids = _extract_playlist_ids(data)
    assert ids == ["VLPL_top50", "VLPL_trending"]


def test_extract_playlist_ids_empty():
    assert _extract_playlist_ids({}) == []
    assert _extract_playlist_ids({"contents": {}}) == []


async def test_fetch_playlist_tracks():
    output = (
        _make_ytdlp_entry("abc1", "Miyagi - Captain", "Miyagi") + "\n"
        + _make_ytdlp_entry("abc2", "Xcho - Moya", "Xcho") + "\n"
    )
    with patch("asyncio.create_subprocess_exec", _mock_exec_factory(output)):
        tracks = await _fetch_playlist_tracks("VLPL_test", 10)
    assert len(tracks) == 2
    assert tracks[0]["title"] == "Miyagi - Captain"
    assert tracks[0]["source"] == "yt"
    assert tracks[1]["artist"] == "Xcho"


async def test_fetch_ytmusic_chart_full():
    browse_data = _make_browse_response(["VLPL_chart1"])
    ytdlp_output = _make_ytdlp_entry("v1", "Track 1", "Artist 1") + "\n"

    async def mock_browse(region):
        return browse_data

    with patch("app.sources.ytmusic._fetch_chart_browse", side_effect=mock_browse), \
         patch("asyncio.create_subprocess_exec", _mock_exec_factory(ytdlp_output)):
        tracks = await fetch_ytmusic_chart("RU", limit=5)

    assert len(tracks) == 1
    assert tracks[0]["title"] == "Track 1"


async def test_fetch_ytmusic_chart_no_playlists():
    async def mock_browse(region):
        return {}

    with patch("app.sources.ytmusic._fetch_chart_browse", side_effect=mock_browse):
        tracks = await fetch_ytmusic_chart("RU", limit=5)
    assert tracks == []
