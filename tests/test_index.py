import pytest
from index import TrackIndex

@pytest.fixture
async def idx(tmp_path):
    i = TrackIndex(db_path=str(tmp_path / "test.db"))
    await i.init()
    return i

async def test_upsert_and_exists(idx):
    await idx.upsert(id="1", artist="Ляпис", album="Album", title="Пососи")
    assert await idx.exists_normalized("pososi")

async def test_latin_and_cyrillic_are_same(idx):
    await idx.upsert(id="1", artist="A", album="B", title="Пососи")
    assert await idx.exists_normalized("POSOSI")

async def test_feat_stripped_for_dedup(idx):
    await idx.upsert(id="1", artist="A", album="B", title="Track (feat. Someone)")
    assert await idx.exists_normalized("track")

async def test_not_exists(idx):
    assert not await idx.exists_normalized("nonexistent track xyz")
