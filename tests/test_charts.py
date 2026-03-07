import pytest
from unittest.mock import AsyncMock, patch
from app.autopop.charts import fetch_all_charts


def _track(source_id, title, artist, source="yt"):
    return {
        "url": f"https://example.com/{source_id}",
        "title": title,
        "artist": artist,
        "duration": 200,
        "source_id": source_id,
        "source": source,
    }


async def test_merge_yt_and_sc():
    yt_tracks = [_track("yt1", "Song A", "Artist 1")]
    sc_tracks = [_track("sc1", "Song B", "Artist 2", source="sc")]

    with patch("app.autopop.charts.fetch_ytmusic_chart", new_callable=AsyncMock, return_value=yt_tracks), \
         patch("app.autopop.charts.fetch_sc_chart", new_callable=AsyncMock, return_value=sc_tracks):
        quotas = [{"genre": "electronic", "region": "US", "count": 5}]
        result = await fetch_all_charts(quotas)

    assert len(result) == 2
    titles = {t["title"] for t in result}
    assert titles == {"Song A", "Song B"}


async def test_cross_source_dedup():
    yt_tracks = [_track("yt1", "Same Song", "Same Artist")]
    sc_tracks = [_track("sc1", "Same Song", "Same Artist", source="sc")]

    with patch("app.autopop.charts.fetch_ytmusic_chart", new_callable=AsyncMock, return_value=yt_tracks), \
         patch("app.autopop.charts.fetch_sc_chart", new_callable=AsyncMock, return_value=sc_tracks):
        quotas = [{"genre": "electronic", "region": "US", "count": 5}]
        result = await fetch_all_charts(quotas)

    assert len(result) == 1


async def test_source_failure_resilience():
    yt_tracks = [_track("yt1", "Good Track", "Good Artist")]

    with patch("app.autopop.charts.fetch_ytmusic_chart", new_callable=AsyncMock, return_value=yt_tracks), \
         patch("app.autopop.charts.fetch_sc_chart", new_callable=AsyncMock, side_effect=RuntimeError("SC down")):
        quotas = [{"genre": "electronic", "region": "US", "count": 5}]
        result = await fetch_all_charts(quotas)

    assert len(result) == 1
    assert result[0]["title"] == "Good Track"


async def test_sc_only_for_supported_regions():
    yt_tracks = [_track("yt1", "Russian Track", "Russian Artist")]

    mock_yt = AsyncMock(return_value=yt_tracks)
    mock_sc = AsyncMock(return_value=[])

    with patch("app.autopop.charts.fetch_ytmusic_chart", mock_yt), \
         patch("app.autopop.charts.fetch_sc_chart", mock_sc):
        quotas = [{"genre": "electronic", "region": "RU", "count": 5}]
        result = await fetch_all_charts(quotas)

    assert len(result) == 1
    mock_sc.assert_not_called()


async def test_multiple_regions_one_yt_per_region():
    yt_tracks = [_track("yt1", "Track", "Artist")]

    mock_yt = AsyncMock(return_value=yt_tracks)
    mock_sc = AsyncMock(return_value=[])

    with patch("app.autopop.charts.fetch_ytmusic_chart", mock_yt), \
         patch("app.autopop.charts.fetch_sc_chart", mock_sc):
        quotas = [
            {"genre": "electronic", "region": "US", "count": 3},
            {"genre": "rock", "region": "US", "count": 3},
        ]
        result = await fetch_all_charts(quotas)

    assert mock_yt.call_count == 1


async def test_empty_quotas():
    result = await fetch_all_charts([])
    assert result == []
