import pytest
from unittest.mock import AsyncMock, patch
from app.sources.sc_charts import fetch_sc_chart, _chart_url, _SUPPORTED_REGIONS


def test_chart_url_supported():
    url = _chart_url("electronic", "US")
    assert url == "https://soundcloud.com/music-charts-us/sets/electronic"


def test_chart_url_hip_hop():
    url = _chart_url("hip-hop", "UK")
    assert url == "https://soundcloud.com/music-charts-uk/sets/hip-hop"


def test_chart_url_bass_maps_to_electronic():
    url = _chart_url("bass", "US")
    assert url == "https://soundcloud.com/music-charts-us/sets/electronic"


def test_chart_url_unsupported_region():
    assert _chart_url("electronic", "RU") is None


def test_chart_url_unsupported_genre():
    assert _chart_url("jazz", "US") is None


async def test_fetch_sc_chart_supported():
    fake_tracks = [
        {"url": "https://soundcloud.com/artist/track1", "title": "Track 1",
         "artist": "DJ Test", "duration": 0, "source_id": "track1", "source": "sc"},
        {"url": "https://soundcloud.com/artist/track2", "title": "Track 2",
         "artist": "Producer X", "duration": 0, "source_id": "track2", "source": "sc"},
    ]
    with patch("app.sources.sc_charts._scrape_sc_playlist", new_callable=AsyncMock, return_value=fake_tracks):
        result = await fetch_sc_chart("electronic", "US", limit=5)
    assert len(result) == 2
    assert result[0]["source"] == "sc"
    assert result[0]["title"] == "Track 1"


async def test_fetch_sc_chart_unsupported_region():
    result = await fetch_sc_chart("electronic", "RU", limit=5)
    assert result == []


async def test_fetch_sc_chart_limit():
    fake_tracks = [
        {"url": f"https://soundcloud.com/a/t{i}", "title": f"T{i}",
         "artist": "A", "duration": 0, "source_id": f"t{i}", "source": "sc"}
        for i in range(10)
    ]
    with patch("app.sources.sc_charts._scrape_sc_playlist", new_callable=AsyncMock, return_value=fake_tracks):
        result = await fetch_sc_chart("electronic", "US", limit=3)
    assert len(result) == 3


async def test_fetch_sc_chart_scrape_failure():
    with patch("app.sources.sc_charts._scrape_sc_playlist", new_callable=AsyncMock, return_value=[]):
        result = await fetch_sc_chart("electronic", "US", limit=5)
    assert result == []
