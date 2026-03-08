import asyncio, logging, re, httpx
from pathlib import Path
from app.db import init_db
from app.config import settings

logger = logging.getLogger("sonyaproxy.downloader")


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

    def _cleanup_partials(self, out_template: str, virt_id: str):
        """Remove .part, .ytdl and other temp files left by yt-dlp."""
        folder = Path(out_template).parent
        youtube_id = virt_id.removeprefix("virt_")
        if folder.exists():
            for f in folder.glob(f"*{youtube_id}*"):
                if f.suffix in (".part", ".ytdl") or ".part-Frag" in f.name:
                    try:
                        f.unlink()
                        logger.info("Cleaned up: %s", f.name)
                    except OSError:
                        pass

    async def trigger_rescan(self):
        try:
            async with httpx.AsyncClient() as client:
                await client.get(
                    f"{settings.gonic_url}/rest/startScan",
                    params={"u": settings.gonic_user, "p": settings.gonic_pass, "v": "1.16.1", "c": "sonyaproxy"},
                )
        except Exception:
            pass

    async def download(
        self, virt_id: str, youtube_url: str, artist: str, title: str,
        trigger_rescan: bool = True,
    ) -> dict:
        async with self._conn.execute(
            "SELECT status, local_path FROM downloads WHERE id = ?", (virt_id,)
        ) as cur:
            row = await cur.fetchone()

        if row and row["status"] == "done":
            logger.debug("Already downloaded: %s", virt_id)
            return {"path": row["local_path"], "artist": artist, "title": title}

        if virt_id in self._events:
            await self._events[virt_id].wait()
            async with self._conn.execute(
                "SELECT local_path FROM downloads WHERE id = ?", (virt_id,)
            ) as cur:
                row = await cur.fetchone()
            return {"path": row["local_path"], "artist": artist, "title": title}

        event = asyncio.Event()
        self._events[virt_id] = event

        try:
            await self._conn.execute(
                "INSERT OR REPLACE INTO downloads (id, youtube_url, status) VALUES (?, ?, 'downloading')",
                (virt_id, youtube_url)
            )
            await self._conn.commit()

            # Fetch metadata first (artist/title) if not provided
            if artist in ("Unknown", "") and "url" in virt_id:
                meta_cmd = [
                    settings.ytdlp_path, "--no-download",
                    "--print", "%(artist,uploader,channel)s",
                    "--print", "%(title)s",
                    "--socket-timeout", "15",
                    youtube_url,
                ]
                meta_proc = await asyncio.create_subprocess_exec(
                    *meta_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                )
                try:
                    meta_out, _ = await asyncio.wait_for(meta_proc.communicate(), timeout=30)
                    lines = meta_out.decode().strip().split("\n")
                    if len(lines) >= 2:
                        meta_artist = lines[0].strip()
                        meta_title = lines[1].strip()
                        if meta_artist and meta_artist not in ("NA", "None"):
                            artist = meta_artist
                        if meta_title and meta_title not in ("NA", "None"):
                            title = meta_title
                        # Rebuild output path with real metadata
                        out_template = str(self._output_path(artist, title, virt_id))
                        logger.info("Resolved metadata: %s - %s", artist, title)
                except (asyncio.TimeoutError, Exception):
                    logger.warning("Metadata fetch failed for %s, using defaults", virt_id)

            logger.info("Downloading: %s - %s (%s)", artist, title, virt_id)
            out_template = str(self._output_path(artist, title, virt_id))
            cmd = [
                settings.ytdlp_path,
                "-f", self._format,
                "-x", "--audio-format", settings.ytdlp_audio_format,
                "-o", out_template,
                "--no-playlist",
                "--socket-timeout", "30",
                "--retries", "3",
                youtube_url,
            ]
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                logger.error("yt-dlp timed out (300s) for %s: %s", virt_id, youtube_url)
                self._cleanup_partials(out_template, virt_id)
                raise RuntimeError(f"yt-dlp timeout for {virt_id}")
            if proc.returncode != 0:
                logger.error("yt-dlp failed (rc=%d) for %s: %s", proc.returncode, virt_id, stderr.decode()[-500:])
                self._cleanup_partials(out_template, virt_id)

            folder = Path(out_template).parent
            youtube_id = virt_id.removeprefix("virt_")
            matches = [f for f in folder.glob(f"*{youtube_id}*")
                       if f.suffix not in (".part", ".ytdl") and ".part-Frag" not in f.name]
            local_path = str(matches[0]) if matches else out_template.replace("%(ext)s", settings.ytdlp_audio_format)

            # Validate file size (< 50KB is likely a preview/garbage)
            lp = Path(local_path)
            if not lp.exists() or lp.stat().st_size < 50_000:
                logger.error("Download too small or missing (%s bytes): %s",
                             lp.stat().st_size if lp.exists() else 0, local_path)
                self._cleanup_partials(out_template, virt_id)
                raise RuntimeError(f"Download failed or too small for {virt_id}")

            # Write ID3 tags via ffmpeg
            if Path(local_path).exists():
                tagged = local_path + ".tagged.mp3"
                tag_cmd = [
                    "ffmpeg", "-y", "-i", local_path,
                    "-c", "copy",
                    "-metadata", f"artist={artist}",
                    "-metadata", f"title={title}",
                    tagged,
                ]
                tag_proc = await asyncio.create_subprocess_exec(
                    *tag_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                await tag_proc.communicate()
                if tag_proc.returncode == 0:
                    Path(tagged).replace(local_path)
                    logger.info("Downloaded OK: %s -> %s", virt_id, local_path)
                else:
                    logger.warning("ffmpeg tagging failed (rc=%d) for %s", tag_proc.returncode, virt_id)

            await self._conn.execute(
                "UPDATE downloads SET status='done', local_path=?, finished_at=CURRENT_TIMESTAMP WHERE id=?",
                (local_path, virt_id)
            )
            await self._conn.commit()

            if trigger_rescan:
                await self.trigger_rescan()

            return {"path": local_path, "artist": artist, "title": title}

        except Exception:
            await self._conn.execute(
                "UPDATE downloads SET status='failed' WHERE id=?", (virt_id,)
            )
            await self._conn.commit()
            raise
        finally:
            event.set()
            self._events.pop(virt_id, None)
