import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.autopop.loop import run_autopop_cycle, _detect_language, _apply_language_filter, _is_boost_day
from app.autopop.flavor import FlavorConfig, ReleaseDayBoost


def _make_track(source_id, title, artist, source="yt", url=None):
    return {
        "url": url or f"https://example.com/{source_id}",
        "title": title,
        "artist": artist,
        "duration": 200,
        "source_id": source_id,
        "source": source,
        "genre_hint": "electronic",
    }


async def test_run_autopop_cycle_skips_existing():
    index = AsyncMock()
    index.exists_normalized = AsyncMock(side_effect=lambda key: "existing" in key)
    index.upsert = AsyncMock()
    queue = AsyncMock()
    queue.download = AsyncMock(return_value="/path/to/file.opus")
    queue.trigger_rescan = AsyncMock()

    candidates = [
        _make_track("new1", "New Song", "Artist A"),
        _make_track("old1", "existing track", "Artist B"),
    ]

    flavor = FlavorConfig(
        genres={"electronic": 1.0},
        languages={"en": 1.0},
        chart_regions=["US"],
        max_tracks_per_cycle=10,
    )

    with patch("app.autopop.loop.fetch_all_charts", return_value=candidates), \
         patch("app.autopop.loop.compute_quotas", return_value=[{"genre": "electronic", "region": "US", "count": 5}]):
        count = await run_autopop_cycle(index, queue, flavor)

    assert count == 1
    assert queue.download.call_count == 1


async def test_dedup_uses_title_only():
    index = AsyncMock()
    index.exists_normalized = AsyncMock(
        side_effect=lambda key: "Cool Song" in key
    )
    index.upsert = AsyncMock()
    queue = AsyncMock()
    queue.download = AsyncMock(return_value="/path/to/file.opus")
    queue.trigger_rescan = AsyncMock()

    candidates = [
        _make_track("id1", "Cool Song", "Different Artist"),
        _make_track("id2", "Brand New", "Another Artist"),
    ]

    flavor = FlavorConfig(
        genres={"electronic": 1.0},
        languages={"en": 1.0},
        chart_regions=["US"],
        max_tracks_per_cycle=10,
    )

    with patch("app.autopop.loop.fetch_all_charts", return_value=candidates), \
         patch("app.autopop.loop.compute_quotas", return_value=[{"genre": "electronic", "region": "US", "count": 5}]):
        count = await run_autopop_cycle(index, queue, flavor)

    assert count == 1
    calls = [c.args[0] for c in index.exists_normalized.call_args_list]
    assert "Cool Song" in calls
    assert "Brand New" in calls


async def test_upsert_called_after_download():
    index = AsyncMock()
    index.exists_normalized = AsyncMock(return_value=False)
    index.upsert = AsyncMock()
    queue = AsyncMock()
    queue.download = AsyncMock(return_value="/path/to/file.opus")
    queue.trigger_rescan = AsyncMock()

    candidates = [_make_track("id1", "New Track", "Artist X")]

    flavor = FlavorConfig(
        genres={"electronic": 1.0},
        languages={"en": 1.0},
        chart_regions=["US"],
        max_tracks_per_cycle=10,
    )

    with patch("app.autopop.loop.fetch_all_charts", return_value=candidates), \
         patch("app.autopop.loop.compute_quotas", return_value=[{"genre": "electronic", "region": "US", "count": 5}]):
        count = await run_autopop_cycle(index, queue, flavor)

    assert count == 1
    index.upsert.assert_called_once_with(
        id="virt_yt_id1",
        artist="Artist X",
        album="Auto-Populate",
        title="New Track",
    )


async def test_run_autopop_cycle_respects_max_tracks():
    index = AsyncMock()
    index.exists_normalized = AsyncMock(return_value=False)
    index.upsert = AsyncMock()
    queue = AsyncMock()
    queue.download = AsyncMock(return_value="/path/to/file.opus")
    queue.trigger_rescan = AsyncMock()

    candidates = [_make_track(f"id{i}", f"Track {i}", "Artist") for i in range(30)]

    flavor = FlavorConfig(
        genres={"electronic": 1.0},
        languages={"en": 1.0},
        chart_regions=["US"],
        max_tracks_per_cycle=5,
    )

    with patch("app.autopop.loop.fetch_all_charts", return_value=candidates), \
         patch("app.autopop.loop.compute_quotas", return_value=[{"genre": "electronic", "region": "US", "count": 10}]):
        count = await run_autopop_cycle(index, queue, flavor)

    assert count == 5
    assert queue.download.call_count == 5


async def test_language_filter():
    ru_tracks = [_make_track(f"ru{i}", f"Песня {i}", "Артист") for i in range(5)]
    en_tracks = [_make_track(f"en{i}", f"Song {i}", "Artist") for i in range(5)]
    all_tracks = ru_tracks + en_tracks

    result = _apply_language_filter(
        all_tracks, {"ru": 0.5, "en": 0.5}, max_count=6
    )
    assert len(result) == 6
    ru_count = sum(1 for t in result if _detect_language(t["title"]) == "ru")
    en_count = sum(1 for t in result if _detect_language(t["title"]) == "en")
    assert ru_count == 3
    assert en_count == 3


def test_detect_language():
    assert _detect_language("Привет мир") == "ru"
    assert _detect_language("Hello world") == "en"
    assert _detect_language("Mix Микс") == "ru"
    assert _detect_language("123 abc") == "en"


async def test_autopop_cycle_handles_download_error():
    index = AsyncMock()
    index.exists_normalized = AsyncMock(return_value=False)
    index.upsert = AsyncMock()

    call_count = 0

    async def mock_download(**kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise RuntimeError("download failed")
        return "/path/to/file.opus"

    queue = AsyncMock()
    queue.download = AsyncMock(side_effect=mock_download)
    queue.trigger_rescan = AsyncMock()

    candidates = [_make_track(f"id{i}", f"Track {i}", "Artist") for i in range(3)]

    flavor = FlavorConfig(
        genres={"electronic": 1.0},
        languages={"en": 1.0},
        chart_regions=["US"],
        max_tracks_per_cycle=10,
    )

    with patch("app.autopop.loop.fetch_all_charts", return_value=candidates), \
         patch("app.autopop.loop.compute_quotas", return_value=[{"genre": "electronic", "region": "US", "count": 5}]):
        count = await run_autopop_cycle(index, queue, flavor)

    assert count == 2
    assert queue.trigger_rescan.called
    assert index.upsert.call_count == 2


def test_is_boost_day_friday():
    flavor = FlavorConfig(release_day_boost=ReleaseDayBoost(days=["friday"]))
    with patch("app.autopop.loop.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "Friday"
        assert _is_boost_day(flavor) is True


def test_is_boost_day_not_boost():
    flavor = FlavorConfig(release_day_boost=ReleaseDayBoost(days=["friday"]))
    with patch("app.autopop.loop.datetime") as mock_dt:
        mock_dt.now.return_value.strftime.return_value = "Monday"
        assert _is_boost_day(flavor) is False
