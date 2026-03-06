import pytest
from unittest.mock import AsyncMock, patch
from search import augment_search3

GONIC_XML = """<?xml version="1.0" encoding="UTF-8"?>
<subsonic-response status="ok" version="1.16.1" xmlns="http://subsonic.org/restapi">
  <searchResult3>
    <song id="1" title="Пососи" artist="Ляпис" album="Album" duration="240"/>
  </searchResult3>
</subsonic-response>"""

VIRTUAL_TRACKS = [
    {"id": "virt_abc", "title": "Never Gonna Give You Up", "artist": "Rick Astley",
     "album": "YouTube", "duration": 213, "youtube_url": "https://youtube.com/watch?v=abc"},
    # Дубликат реального трека
    {"id": "virt_dup", "title": "Пободи", "artist": "Ляпис",
     "album": "YouTube", "duration": 240, "youtube_url": "https://youtube.com/watch?v=dup"},
]

async def test_augment_deduplicates_and_merges(tmp_path):
    from index import TrackIndex
    idx = TrackIndex(db_path=str(tmp_path / "test.db"))
    await idx.init()
    # Добавить реальный трек в индекс (тот же title что у virt_dup)
    await idx.upsert(id="1", artist="Ляпис", album="Album", title="Пободи")

    result_xml = await augment_search3(
        gonic_xml=GONIC_XML,
        virtual_tracks=VIRTUAL_TRACKS,
        index=idx,
    )
    # Дубликат должен быть отфильтрован
    assert "virt_dup" not in result_xml
    # Новый виртуальный трек должен быть в результате
    assert "virt_abc" in result_xml
    # Реальный трек должен остаться
    assert 'id="1"' in result_xml
