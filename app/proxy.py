import httpx
from fastapi import Request
from fastapi.responses import Response
from app.config import settings


async def forward_to_gonic(request: Request) -> Response:
    path = request.url.path
    params = dict(request.query_params)
    body = await request.body()

    url = f"{settings.gonic_url}{path}"

    async with httpx.AsyncClient() as client:
        resp = await client.request(
            method=request.method,
            url=url,
            params=params,
            content=body,
            headers={k: v for k, v in request.headers.items()
                     if k.lower() not in ("host", "content-length")},
        )

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=dict(resp.headers),
        media_type=resp.headers.get("content-type"),
    )
