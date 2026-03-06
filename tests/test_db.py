import pytest, aiosqlite

async def test_db_init_creates_tables(tmp_path):
    db_path = str(tmp_path / "test.db")
    import db
    conn = await db.init_db(db_path)
    # Проверить что таблицы созданы
    async with conn.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        tables = {row[0] async for row in cur}
    assert "track_index" in tables
    assert "downloads" in tables
    await conn.close()
