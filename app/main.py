import asyncio
import logging
from fastapi import FastAPI, Request
from fastapi.responses import Response, FileResponse
from app.config import settings
from app.proxy import forward_to_gonic
from app.index import TrackIndex
from app.downloader import DownloadQueue
from app.ytdlp import search_virtual
from app.search import augment_search3
from app.db import get_setting
from app.admin import router as admin_router
import httpx

logger = logging.getLogger("sonyaproxy")

app = FastAPI(title="sonyaproxy")
app.include_router(admin_router)

track_index = TrackIndex(db_path=settings.db_path)
download_queue = DownloadQueue(
    db_path=settings.db_path,
    music_dir=settings.gonic_music_dir,
    ytdlp_format=settings.ytdlp_format,
)

_sync_task: asyncio.Task | None = None
_autopop_task: asyncio.Task | None = None
_bot_task: asyncio.Task | None = None
_bot_instance = None
_dp_instance = None


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


_YTDLP_UPDATE_INTERVAL = 24 * 3600  # once per day


async def _ytdlp_update_loop():
    while True:
        await asyncio.sleep(_YTDLP_UPDATE_INTERVAL)
        try:
            proc = await asyncio.create_subprocess_exec(
                settings.ytdlp_path, "-U",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await proc.communicate()
            logger.info("yt-dlp update: %s", stdout.decode().strip())
        except Exception:
            logger.warning("yt-dlp update failed", exc_info=True)


async def _start_bot():
    global _bot_instance, _dp_instance
    conn = download_queue._conn
    token = await get_setting(conn, "telegram_bot_token")
    if not token:
        token = settings.telegram_bot_token
    if not token:
        logger.info("No Telegram bot token, skipping bot startup")
        return

    try:
        from app.bot import start_bot, run_polling
        _bot_instance, _dp_instance = await start_bot(token)
        await run_polling(_bot_instance, _dp_instance)
    except Exception:
        logger.exception("Telegram bot failed")


async def restart_bot():
    global _bot_task, _bot_instance, _dp_instance
    if _bot_instance:
        try:
            await _dp_instance.stop_polling()
            await _bot_instance.session.close()
        except Exception:
            pass
        _bot_instance = None
        _dp_instance = None

    if _bot_task and not _bot_task.done():
        _bot_task.cancel()

    _bot_task = asyncio.create_task(_start_bot())
    logger.info("Telegram bot restarted")


@app.on_event("startup")
async def on_startup():
    global _sync_task, _autopop_task, _bot_task
    await startup()
    _sync_task = asyncio.create_task(_sync_loop())
    asyncio.create_task(_ytdlp_update_loop())
    if settings.autopop_enabled:
        _autopop_task = asyncio.create_task(_start_autopop())
    _bot_task = asyncio.create_task(_start_bot())


@app.api_route("/rest/{path:path}", methods=["GET", "POST"])
async def subsonic_handler(request: Request, path: str) -> Response:
    params = dict(request.query_params)

    if path in ("stream", "stream.view") and params.get("id", "").startswith("virt_"):
        return await handle_virtual_stream(request, params)

    if path in ("search3", "search3.view"):
        query = params.get("query", "").strip().strip('"')
        if query:
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

    return Response(
        content=augmented_xml.encode(),
        media_type="application/xml",
    )


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

    # Determine URL based on prefix
    if virt_id.startswith("virt_ym_"):
        # Yandex Music — download via API
        ym_track_id = int(virt_id.removeprefix("virt_ym_"))
        conn = download_queue._conn
        ym_token = await get_setting(conn, "yandex_token")
        if not ym_token:
            return Response(content="Yandex Music token not configured", status_code=503)

        from app.sources.yandex_music import download_yandex
        from pathlib import Path
        output_dir = Path(settings.gonic_music_dir) / "Virtual Downloads" / "Yandex Music" / "Singles"
        result = await download_yandex(ym_token, ym_track_id, output_dir=output_dir)
        if not result:
            return Response(content="Download failed", status_code=502)
        local_path = result["path"]
        await download_queue.trigger_rescan()
    elif virt_id.startswith("virt_sc_"):
        sc_id = virt_id.removeprefix("virt_sc_")
        url = f"https://api.soundcloud.com/tracks/{sc_id}"
        local_path = await download_queue.download(
            virt_id=virt_id, youtube_url=url, artist="Unknown", title=sc_id,
        )
    else:
        youtube_id = virt_id.removeprefix("virt_yt_")
        url = f"https://www.youtube.com/watch?v={youtube_id}"
        local_path = await download_queue.download(
            virt_id=virt_id, youtube_url=url, artist="Unknown", title=youtube_id,
        )

    from pathlib import Path
    ext = Path(local_path).suffix.lstrip(".")
    mime_map = {"mp3": "audio/mpeg", "opus": "audio/opus", "m4a": "audio/mp4", "ogg": "audio/ogg"}
    media_type = mime_map.get(ext, "audio/mpeg")

    return FileResponse(
        path=local_path,
        media_type=media_type,
        filename=Path(local_path).name,
    )
