import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import Response, FileResponse
from config import settings
from proxy import forward_to_gonic
from index import TrackIndex
from downloader import DownloadQueue
from ytdlp import search_virtual
from search import augment_search3
import httpx

app = FastAPI(title="sonyaproxy")

track_index = TrackIndex()
download_queue = DownloadQueue(
    db_path="sonyaproxy.db",
    music_dir=settings.gonic_music_dir,
    ytdlp_format=settings.ytdlp_format,
)

_sync_task: asyncio.Task | None = None


async def startup():
    await track_index.init()
    await download_queue.init()
    try:
        await track_index.sync_from_gonic(
            settings.gonic_url, settings.gonic_user, settings.gonic_pass
        )
    except Exception:
        pass  # GONIC может быть недоступен при старте


async def _sync_loop():
    while True:
        await asyncio.sleep(300)
        try:
            await track_index.sync_from_gonic(
                settings.gonic_url, settings.gonic_user, settings.gonic_pass
            )
        except Exception:
            pass


@app.on_event("startup")
async def on_startup():
    global _sync_task
    await startup()
    _sync_task = asyncio.create_task(_sync_loop())


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

    from musicbrainz import enrich_tracks
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


async def handle_virtual_stream(request: Request, params: dict) -> Response:
    virt_id = params["id"]
    youtube_id = virt_id.removeprefix("virt_")

    local_path = await download_queue.download(
        virt_id=virt_id,
        youtube_url=f"https://www.youtube.com/watch?v={youtube_id}",
        artist="Unknown",
        title=youtube_id,
    )

    return FileResponse(
        path=local_path,
        media_type="audio/opus",
        filename=f"{youtube_id}.opus",
    )
