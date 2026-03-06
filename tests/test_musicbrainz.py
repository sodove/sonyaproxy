import pytest
from unittest.mock import patch
from musicbrainz import enrich_track

MOCK_MB_RESPONSE = {
    "recording-list": [{
        "title": "Never Gonna Give You Up",
        "artist-credit": [{"artist": {"name": "Rick Astley"}}],
        "release-list": [{
            "title": "Whenever You Need Somebody",
            "date": "1987",
        }],
    }]
}

async def test_enrich_adds_album_and_year():
    track = {
        "id": "virt_yt_abc",
        "title": "Never Gonna Give You Up",
        "artist": "Rick Astley",
        "album": "YouTube",
        "duration": 213,
        "youtube_url": "https://yt.com/abc",
    }

    with patch("musicbrainzngs.search_recordings", return_value=MOCK_MB_RESPONSE):
        enriched = await enrich_track(track)

    assert enriched["album"] == "Whenever You Need Somebody"
    assert enriched["year"] == "1987"

async def test_enrich_fallback_on_no_result():
    track = {
        "id": "virt_yt_xyz",
        "title": "Rare Obscure Track",
        "artist": "Unknown Artist",
        "album": "YouTube",
        "duration": 100,
        "youtube_url": "https://yt.com/xyz",
    }

    with patch("musicbrainzngs.search_recordings", return_value={"recording-list": []}):
        enriched = await enrich_track(track)

    assert enriched["album"] == "YouTube"
    assert "year" not in enriched or enriched.get("year") is None
