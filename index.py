import httpx
import xmltodict
from db import init_db
from normalizer import normalize


class TrackIndex:
    def __init__(self, db_path: str = "sonyaproxy.db"):
        self._db_path = db_path
        self._conn = None

    async def init(self):
        self._conn = await init_db(self._db_path)

    async def upsert(self, id: str, artist: str, album: str, title: str):
        key = normalize(title)
        await self._conn.execute(
            """INSERT OR REPLACE INTO track_index (id, artist, album, title, normalized_key)
               VALUES (?, ?, ?, ?, ?)""",
            (id, artist, album, title, key)
        )
        await self._conn.commit()

    async def exists_normalized(self, query: str) -> bool:
        norm = normalize(query)
        async with self._conn.execute(
            "SELECT 1 FROM track_index WHERE normalized_key = ? LIMIT 1",
            (norm,)
        ) as cur:
            return await cur.fetchone() is not None

    async def sync_from_gonic(self, gonic_url: str, gonic_user: str, gonic_pass: str):
        """Скачать все треки из GONIC и обновить индекс."""
        params_base = {"u": gonic_user, "p": gonic_pass, "v": "1.16.1", "c": "sonyaproxy", "f": "xml"}
        async with httpx.AsyncClient() as client:
            offset = 0
            while True:
                params = {**params_base, "query": "", "songCount": 500, "songOffset": offset}
                r = await client.get(f"{gonic_url}/rest/search3", params=params)
                r.raise_for_status()
                data = xmltodict.parse(r.text)
                songs = data.get("subsonic-response", {}).get("searchResult3", {}).get("song", [])
                if isinstance(songs, dict):
                    songs = [songs]
                if not songs:
                    break
                for song in songs:
                    key = normalize(song.get("@title", ""))
                    await self._conn.execute(
                        """INSERT OR REPLACE INTO track_index (id, artist, album, title, normalized_key)
                           VALUES (?, ?, ?, ?, ?)""",
                        (song["@id"], song.get("@artist", ""), song.get("@album", ""),
                         song.get("@title", ""), key)
                    )
                # один commit на страницу (500 треков) вместо 500 отдельных
                await self._conn.commit()
                if len(songs) < 500:
                    break
                offset += 500

    async def close(self):
        if self._conn:
            await self._conn.close()
