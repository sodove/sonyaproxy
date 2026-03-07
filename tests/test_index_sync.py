import pytest
from unittest.mock import patch
from app.index import TrackIndex

MOCK_SEARCH3_XML = """<?xml version="1.0" encoding="UTF-8"?>
<subsonic-response status="ok" version="1.16.1">
  <searchResult3>
    <song id="10" title="Пососи" artist="Ляпис Трубецкой" album="Матерный альбом"/>
    <song id="11" title="Track (feat. Morg)" artist="Artist" album="Album"/>
  </searchResult3>
</subsonic-response>"""

async def test_sync_from_gonic(tmp_path):
    idx = TrackIndex(db_path=str(tmp_path / "test.db"))
    await idx.init()

    async def mock_get(self, url, **kwargs):
        class R:
            text = MOCK_SEARCH3_XML
            def raise_for_status(self): pass
        return R()

    with patch("httpx.AsyncClient.get", mock_get):
        await idx.sync_from_gonic(
            gonic_url="http://fake:4533",
            gonic_user="u", gonic_pass="p"
        )

    assert await idx.exists_normalized("pososi")
    assert await idx.exists_normalized("track")
