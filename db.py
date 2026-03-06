import aiosqlite

CREATE_TRACK_INDEX = """
CREATE TABLE IF NOT EXISTS track_index (
    id TEXT PRIMARY KEY,
    artist TEXT,
    album TEXT,
    title TEXT,
    normalized_key TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_DOWNLOADS = """
CREATE TABLE IF NOT EXISTS downloads (
    id TEXT PRIMARY KEY,
    youtube_url TEXT,
    status TEXT DEFAULT 'pending',
    local_path TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP
);
"""

CREATE_INDEX_ON_NORMALIZED = """
CREATE INDEX IF NOT EXISTS idx_track_normalized ON track_index(normalized_key);
"""

async def init_db(path: str = "sonyaproxy.db") -> aiosqlite.Connection:
    conn = await aiosqlite.connect(path)
    conn.row_factory = aiosqlite.Row
    await conn.execute(CREATE_TRACK_INDEX)
    await conn.execute(CREATE_DOWNLOADS)
    await conn.execute(CREATE_INDEX_ON_NORMALIZED)
    await conn.commit()
    return conn
