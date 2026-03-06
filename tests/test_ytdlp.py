import pytest
from unittest.mock import patch
from ytdlp import search_virtual

YT_OUTPUT = '{"id": "dQw4w9WgXcQ", "title": "Never Gonna Give You Up", "uploader": "Rick Astley", "duration": 213, "webpage_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}\n'
SC_OUTPUT = '{"id": "sc_111", "title": "Never Gonna Give You Up (SC)", "uploader": "Rick Astley", "duration": 213, "webpage_url": "https://soundcloud.com/rickastley/never"}\n'
SC_DUP_OUTPUT = '{"id": "sc_dup", "title": "Never Gonna Give You Up", "uploader": "Rick Astley", "duration": 213, "webpage_url": "https://soundcloud.com/rickastley/dup"}\n'

async def test_search_virtual_merges_yt_and_sc():
    call_count = 0

    async def mock_exec(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        is_sc = any("scsearch" in str(a) for a in args)
        output = (SC_OUTPUT + SC_DUP_OUTPUT) if is_sc else YT_OUTPUT

        class P:
            stdout = output.encode()
            returncode = 0
            async def communicate(self_p): return self_p.stdout, b""
        return P()

    with patch("asyncio.create_subprocess_exec", mock_exec):
        results = await search_virtual("never gonna give you up", count=5)

    assert call_count == 2  # оба поиска запустились
    ids = [r["id"] for r in results]
    assert "virt_yt_dQw4w9WgXcQ" in ids
    assert "virt_sc_sc_111" in ids
    # Дубликат SC (тот же title+artist) должен быть удалён
    assert "virt_sc_sc_dup" not in ids

async def test_search_virtual_yt_prefix():
    async def mock_exec(*args, **kwargs):
        class P:
            stdout = YT_OUTPUT.encode()
            returncode = 0
            async def communicate(self_p): return self_p.stdout, b""
        return P()

    with patch("asyncio.create_subprocess_exec", mock_exec):
        results = await search_virtual("test", count=5)

    yt_results = [r for r in results if "youtube" in r.get("youtube_url", "")]
    assert yt_results[0]["id"].startswith("virt_yt_")
