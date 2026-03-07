import pytest, aiosqlite

async def test_db_init_creates_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    from app.db import init_db
    conn = await init_db(db_path)
    async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        tables = {row[0] async for row in cur}
    assert "track_index" in tables
    assert "downloads" in tables
    await conn.close()
