import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch
import httpx

async def test_proxy_passes_through_ping():
    from app.main import app

    gonic_response = b'<?xml version="1.0"?><subsonic-response status="ok" version="1.16.1"/>'

    async def mock_request(self, method, url, **kwargs):
        class R:
            status_code = 200
            content = gonic_response
            headers = {"content-type": "application/xml"}
            def raise_for_status(self): pass
        return R()

    with patch.object(httpx.AsyncClient, "request", mock_request):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.get("/rest/ping?u=admin&p=secret&v=1.16.1&c=test")
    assert r.status_code == 200
    assert b"subsonic-response" in r.content
