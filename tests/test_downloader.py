import pytest, asyncio
from pathlib import Path
from unittest.mock import patch
from downloader import DownloadQueue

async def test_download_creates_file(tmp_path):
    q = DownloadQueue(
        db_path=str(tmp_path / "test.db"),
        music_dir=str(tmp_path / "music"),
        ytdlp_format="bestaudio",
    )
    await q.init()

    async def mock_exec(*args, **kwargs):
        output_path = None
        for i, arg in enumerate(args):
            if arg == "-o":
                output_path = args[i + 1]
                break
        if output_path:
            real_path = output_path.replace("%(ext)s", "opus")
            Path(real_path).parent.mkdir(parents=True, exist_ok=True)
            Path(real_path).write_bytes(b"fake audio data")

        class P:
            returncode = 0
            async def communicate(self):
                return b"", b""
            async def wait(self):
                return 0
        return P()

    with patch("asyncio.create_subprocess_exec", mock_exec):
        local_path = await q.download(
            virt_id="virt_dQw4w9WgXcQ",
            youtube_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            artist="Rick Astley",
            title="Never Gonna Give You Up",
        )

    assert Path(local_path).exists()

async def test_concurrent_download_same_id(tmp_path):
    """Два одновременных запроса одного трека — только одно скачивание."""
    q = DownloadQueue(
        db_path=str(tmp_path / "test.db"),
        music_dir=str(tmp_path / "music"),
        ytdlp_format="bestaudio",
    )
    await q.init()

    download_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal download_count
        download_count += 1
        for i, arg in enumerate(args):
            if arg == "-o":
                p = args[i+1].replace("%(ext)s", "opus")
                Path(p).parent.mkdir(parents=True, exist_ok=True)
                Path(p).write_bytes(b"fake audio")
        class P:
            returncode = 0
            async def communicate(self): return b"", b""
            async def wait(self): return 0
        return P()

    with patch("asyncio.create_subprocess_exec", mock_exec):
        results = await asyncio.gather(
            q.download("virt_abc", "https://yt.com/abc", "Artist", "Song"),
            q.download("virt_abc", "https://yt.com/abc", "Artist", "Song"),
        )

    assert download_count == 1  # Скачано только раз
    assert results[0] == results[1]

async def test_rescan_triggered_after_download(tmp_path):
    from config import settings
    q = DownloadQueue(
        db_path=str(tmp_path / "test.db"),
        music_dir=str(tmp_path / "music"),
        ytdlp_format="bestaudio",
    )
    await q.init()

    rescan_called = False

    async def mock_rescan(self_inner):
        nonlocal rescan_called
        rescan_called = True

    async def mock_exec(*args, **kwargs):
        for i, arg in enumerate(args):
            if arg == "-o":
                p = args[i+1].replace("%(ext)s", "opus")
                Path(p).parent.mkdir(parents=True, exist_ok=True)
                Path(p).write_bytes(b"audio")
        class P:
            returncode = 0
            async def communicate(self): return b"", b""
        return P()

    with patch("asyncio.create_subprocess_exec", mock_exec), \
         patch.object(DownloadQueue, "trigger_rescan", mock_rescan):
        await q.download("virt_x", "https://yt.com/x", "A", "B")

    assert rescan_called
