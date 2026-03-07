import pytest
from httpx import AsyncClient, ASGITransport
from fastapi.responses import Response as FastAPIResponse
from unittest.mock import patch, AsyncMock

GONIC_SEARCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<subsonic-response status="ok" version="1.16.1">
  <searchResult3>
    <song id="1" title="Real Song" artist="Artist" album="Album" duration="200"/>
  </searchResult3>
</subsonic-response>"""

VIRTUAL_TRACKS = [
    {"id": "virt_yt1", "title": "Virtual Song", "artist": "YT Artist",
     "album": "YouTube", "duration": 180, "youtube_url": "https://yt.com/yt1"},
]

async def test_search3_includes_virtual_tracks():
    import app.main as main
    await main.startup()

    async def mock_forward(request):
        return FastAPIResponse(
            content=GONIC_SEARCH_XML.encode(),
            media_type="application/xml",
        )

    with patch("app.main.forward_to_gonic", mock_forward), \
         patch("app.main.search_virtual", AsyncMock(return_value=VIRTUAL_TRACKS)), \
         patch("app.musicbrainz.enrich_tracks", AsyncMock(side_effect=lambda t: t)):
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/rest/search3?query=test&u=a&p=b&v=1.16.1&c=test")

    assert r.status_code == 200
    assert b"virt_yt1" in r.content
    assert b"Real Song" in r.content

async def test_stream_virtual_triggers_download(tmp_path):
    import app.main as main
    await main.startup()

    mock_download = AsyncMock(return_value=str(tmp_path / "file.opus"))
    (tmp_path / "file.opus").write_bytes(b"fake audio")
    with patch.object(main.download_queue, "download", mock_download), \
         patch("app.main._verify_client_auth", AsyncMock(return_value=True)):
        transport = ASGITransport(app=main.app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/rest/stream?id=virt_dQw4w9WgXcQ&u=a&p=b&v=1.16.1&c=test")
        mock_download.assert_called_once()
