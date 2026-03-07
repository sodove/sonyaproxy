import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import Response, FileResponse
from app.config import settings
from app.proxy import forward_to_gonic
from app.index import TrackIndex
from app.downloader import DownloadQueue
from app.ytdlp import search_virtual
from app.search import augment_search3
import httpx

app = FastAPI(title="sonyaproxy")

track_index = TrackIndex(db_path=settings.db_path)
download_queue = DownloadQueue(
    db_path=settings.db_path,
    music_dir=settings.gonic_music_dir,
    ytdlp_format=settings.ytdlp_format,
)

_sync_task: asyncio.Task | None = None
_autopop_task: asyncio.Task | None = None


async def startup():
    await track_index.init()
    await download_queue.init()
    asyncio.create_task(_initial_sync())


async def _initial_sync():
    try:
        await track_index.sync_from_gonic(
            settings.gonic_url, settings.gonic_user, settings.gonic_pass
        )
    except Exception:
        pass


async def _sync_loop():
    while True:
        await asyncio.sleep(300)
        try:
            await track_index.sync_from_gonic(
                settings.gonic_url, settings.gonic_user, settings.gonic_pass
            )
        except Exception:
            pass


async def _start_autopop():
    await asyncio.sleep(settings.autopop_startup_delay)
    from app.autopop.loop import autopop_loop
    await autopop_loop(track_index, download_queue, settings.autopop_flavor_path)


@app.on_event("startup")
async def on_startup():
    global _sync_task, _autopop_task
    await startup()
    _sync_task = asyncio.create_task(_sync_loop())
    if settings.autopop_enabled:
        _autopop_task = asyncio.create_task(_start_autopop())


@app.api_route("/rest/{path:path}", methods=["GET", "POST"])
async def subsonic_handler(request: Request, path: str) -> Response:
    params = dict(request.query_params)

    if path == "stream" and params.get("id", "").startswith("virt_"):
        return await handle_virtual_stream(request, params)

    if path == "search3":
        return await handle_search3(request, params)

    return await forward_to_gonic(request)


async def handle_search3(request: Request, params: dict) -> Response:
    query = params.get("query", "")
    gonic_resp, virtual_tracks = await asyncio.gather(
        forward_to_gonic(request),
        search_virtual(query, count=10),
    )

    gonic_xml = gonic_resp.body.decode()

    from app.musicbrainz import enrich_tracks
    virtual_tracks = await enrich_tracks(virtual_tracks)

    augmented_xml = await augment_search3(
        gonic_xml=gonic_xml,
        virtual_tracks=virtual_tracks,
        index=track_index,
    )

    top_virtuals = virtual_tracks[:settings.prefetch_count]
    for vt in top_virtuals:
        asyncio.create_task(_prefetch(vt))

    return Response(
        content=augmented_xml.encode(),
        media_type="application/xml",
    )


async def _prefetch(vt: dict):
    try:
        await download_queue.download(
            virt_id=vt["id"],
            youtube_url=vt["youtube_url"],
            artist=vt["artist"],
            title=vt["title"],
        )
    except Exception:
        pass


async def _verify_client_auth(params: dict) -> bool:
    auth_params = {k: v for k, v in params.items() if k in ("u", "p", "t", "s", "v", "c", "f")}
    if "u" not in auth_params:
        return False
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.gonic_url}/rest/ping",
                params=auth_params,
            )
            return r.status_code == 200 and "error" not in r.text.lower()
    except Exception:
        return False


async def handle_virtual_stream(request: Request, params: dict) -> Response:
    if not await _verify_client_auth(params):
        return Response(
            content='<?xml version="1.0" encoding="UTF-8"?>'
            '<subsonic-response status="failed" version="1.16.1">'
            '<error code="40" message="Wrong username or password"/>'
            '</subsonic-response>',
            media_type="application/xml",
            status_code=401,
        )

    virt_id = params["id"]
    youtube_id = virt_id.removeprefix("virt_")

    local_path = await download_queue.download(
        virt_id=virt_id,
        youtube_url=f"https://www.youtube.com/watch?v={youtube_id}",
        artist="Unknown",
        title=youtube_id,
    )

    from pathlib import Path
    ext = Path(local_path).suffix.lstrip(".")
    mime_map = {"mp3": "audio/mpeg", "opus": "audio/opus", "m4a": "audio/mp4", "ogg": "audio/ogg"}
    media_type = mime_map.get(ext, "audio/mpeg")

    return FileResponse(
        path=local_path,
        media_type=media_type,
        filename=f"{youtube_id}.{ext}",
    )
