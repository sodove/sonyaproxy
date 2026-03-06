import asyncio, re, httpx
from pathlib import Path
from db import init_db
from config import settings


class DownloadQueue:
    def __init__(self, db_path: str, music_dir: str, ytdlp_format: str):
        self._db_path = db_path
        self._music_dir = music_dir
        self._format = ytdlp_format
        self._conn = None
        self._events: dict[str, asyncio.Event] = {}

    async def init(self):
        self._conn = await init_db(self._db_path)

    def _safe_path(self, s: str) -> str:
        return re.sub(r'[<>:"/\\|?*]', '_', s)

    def _output_path(self, artist: str, title: str, virt_id: str) -> Path:
        youtube_id = virt_id.removeprefix("virt_")
        folder = Path(self._music_dir) / "Virtual Downloads" / self._safe_path(artist) / "Singles"
        return folder / f"{self._safe_path(title)}__{youtube_id}.%(ext)s"

    async def _trigger_rescan(self, gonic_url: str, user: str, password: str):
        """Запустить пересканирование библиотеки GONIC."""
        try:
            async with httpx.AsyncClient() as client:
                await client.get(
                    f"{gonic_url}/rest/startScan",
                    params={"u": user, "p": password, "v": "1.16.1", "c": "sonyaproxy"},
                )
        except Exception:
            pass

    async def download(
        self, virt_id: str, youtube_url: str, artist: str, title: str
    ) -> str:
        # Проверить done в БД
        async with self._conn.execute(
            "SELECT status, local_path FROM downloads WHERE id = ?", (virt_id,)
        ) as cur:
            row = await cur.fetchone()

        if row and row["status"] == "done":
            return row["local_path"]

        # Если уже качается — ждать Event
        if virt_id in self._events:
            await self._events[virt_id].wait()
            async with self._conn.execute(
                "SELECT local_path FROM downloads WHERE id = ?", (virt_id,)
            ) as cur:
                row = await cur.fetchone()
            return row["local_path"]

        # Начать скачивание
        event = asyncio.Event()
        self._events[virt_id] = event

        try:
            await self._conn.execute(
                "INSERT OR REPLACE INTO downloads (id, youtube_url, status) VALUES (?, ?, 'downloading')",
                (virt_id, youtube_url)
            )
            await self._conn.commit()

            out_template = str(self._output_path(artist, title, virt_id))
            cmd = [
                "yt-dlp",
                "-f", self._format,
                "-o", out_template,
                "--no-playlist",
                youtube_url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            # Найти скачанный файл (ext может быть любым)
            folder = Path(out_template).parent
            youtube_id = virt_id.removeprefix("virt_")
            matches = list(folder.glob(f"*{youtube_id}*"))
            local_path = str(matches[0]) if matches else out_template.replace("%(ext)s", "opus")

            await self._conn.execute(
                "UPDATE downloads SET status='done', local_path=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (local_path, virt_id)
            )
            await self._conn.commit()

            await self._trigger_rescan(settings.gonic_url, settings.gonic_user, settings.gonic_pass)

            return local_path

        except Exception:
            await self._conn.execute(
                "UPDATE downloads SET status='failed' WHERE id=?", (virt_id,)
            )
            await self._conn.commit()
            raise
        finally:
            event.set()
            self._events.pop(virt_id, None)
