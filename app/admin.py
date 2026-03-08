import asyncio
import logging
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from app.db import get_setting, set_setting

logger = logging.getLogger("sonyaproxy.admin")

router = APIRouter(prefix="/admin")

_ADMIN_HTML = """<!DOCTYPE html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>sonyaproxy admin</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;padding:20px;max-width:600px;margin:0 auto}
h1{color:#e94560;margin-bottom:20px;font-size:1.5em}
h2{color:#0f3460;background:#e94560;padding:8px 12px;border-radius:6px;margin:20px 0 10px;font-size:1em}
.card{background:#16213e;border-radius:8px;padding:16px;margin-bottom:12px}
label{display:block;font-size:.85em;color:#888;margin-bottom:4px}
input[type=text],input[type=password]{width:100%;padding:8px;border:1px solid #333;border-radius:4px;background:#0f3460;color:#e0e0e0;font-family:monospace;font-size:.9em}
button{background:#e94560;color:#fff;border:none;padding:8px 20px;border-radius:4px;cursor:pointer;margin-top:8px;font-size:.9em}
button:hover{background:#c73e54}
.status{font-size:.85em;color:#888;margin-top:4px}
.ok{color:#4ecca3}.err{color:#e94560}
.mask{cursor:pointer;user-select:none}
</style>
</head><body>
<h1>sonyaproxy</h1>

<h2>Tokens</h2>
<div class="card">
<form method="POST" action="/admin/settings">
<label>Yandex Music Token</label>
<input type="password" name="yandex_token" value="{yandex_token}" placeholder="not set">
<div class="status">{ym_status}</div>

<label style="margin-top:12px">Telegram Bot Token</label>
<input type="password" name="telegram_bot_token" value="{telegram_bot_token}" placeholder="not set">
<div class="status">{tg_status}</div>

<button type="submit">Save</button>
</form>
</div>

<h2>Status</h2>
<div class="card">
<div>yt-dlp: <span class="{ytdlp_class}">{ytdlp_version}</span></div>
<div>Track index: <strong>{track_count}</strong> tracks</div>
<div>Downloads: <strong>{download_count}</strong> completed</div>
<div>Autopop: <span class="{autopop_class}">{autopop_status}</span></div>
</div>
</body></html>"""


async def _get_db():
    from app.main import download_queue
    return download_queue._conn


async def _verify_admin(request: Request) -> bool:
    from app.main import _verify_client_auth
    params = dict(request.query_params)
    if "u" not in params:
        auth = request.headers.get("authorization", "")
        if auth.startswith("Basic "):
            import base64
            decoded = base64.b64decode(auth[6:]).decode()
            u, p = decoded.split(":", 1)
            params["u"] = u
            params["p"] = p
            params["v"] = "1.16.1"
            params["c"] = "admin"
    return await _verify_client_auth(params)


@router.get("/", response_class=HTMLResponse)
async def admin_page(request: Request):
    if not await _verify_admin(request):
        return HTMLResponse(
            status_code=401,
            content="Unauthorized",
            headers={"WWW-Authenticate": 'Basic realm="sonyaproxy"'},
        )

    conn = await _get_db()

    ym_token = await get_setting(conn, "yandex_token") or ""
    tg_token = await get_setting(conn, "telegram_bot_token") or ""

    # ym status
    ym_status = '<span class="err">not set</span>'
    if ym_token:
        try:
            from app.sources.yandex_music import check_token
            valid = await check_token(ym_token)
            ym_status = f'<span class="ok">valid</span>' if valid else '<span class="err">invalid token</span>'
        except Exception:
            ym_status = '<span class="status">token set (unchecked)</span>'

    tg_status = f'<span class="ok">set</span>' if tg_token else '<span class="err">not set</span>'

    # yt-dlp version
    try:
        proc = await asyncio.create_subprocess_exec(
            "yt-dlp", "--version",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        ytdlp_version = stdout.decode().strip()
        ytdlp_class = "ok"
    except Exception:
        ytdlp_version = "not found"
        ytdlp_class = "err"

    # counts
    from app.config import settings
    try:
        async with conn.execute("SELECT COUNT(*) as c FROM track_index") as cur:
            track_count = (await cur.fetchone())["c"]
    except Exception:
        track_count = "?"

    try:
        async with conn.execute("SELECT COUNT(*) as c FROM downloads WHERE status='done'") as cur:
            download_count = (await cur.fetchone())["c"]
    except Exception:
        download_count = "?"

    autopop_status = "enabled" if settings.autopop_enabled else "disabled"
    autopop_class = "ok" if settings.autopop_enabled else "status"

    html = _ADMIN_HTML.format(
        yandex_token=ym_token,
        telegram_bot_token=tg_token,
        ym_status=ym_status,
        tg_status=tg_status,
        ytdlp_version=ytdlp_version,
        ytdlp_class=ytdlp_class,
        track_count=track_count,
        download_count=download_count,
        autopop_status=autopop_status,
        autopop_class=autopop_class,
    )
    return HTMLResponse(html)


@router.post("/settings")
async def save_settings(request: Request):
    if not await _verify_admin(request):
        return HTMLResponse(status_code=401, content="Unauthorized",
                            headers={"WWW-Authenticate": 'Basic realm="sonyaproxy"'})

    conn = await _get_db()
    form = await request.form()

    for key in ("yandex_token", "telegram_bot_token"):
        value = form.get(key, "").strip()
        if value:
            await set_setting(conn, key, value)
            logger.info("Setting updated: %s", key)

    # Notify bot to restart if token changed
    tg_token = form.get("telegram_bot_token", "").strip()
    if tg_token:
        try:
            from app.main import restart_bot
            await restart_bot()
        except Exception:
            pass

    return RedirectResponse(url="/admin/?u=" + dict(request.query_params).get("u", "admin") +
                           "&p=" + dict(request.query_params).get("p", ""),
                           status_code=303)


@router.get("/status")
async def admin_status(request: Request):
    if not await _verify_admin(request):
        return JSONResponse(status_code=401, content={"error": "unauthorized"})

    conn = await _get_db()
    from app.config import settings

    async with conn.execute("SELECT COUNT(*) as c FROM track_index") as cur:
        track_count = (await cur.fetchone())["c"]
    async with conn.execute("SELECT COUNT(*) as c FROM downloads WHERE status='done'") as cur:
        done = (await cur.fetchone())["c"]
    async with conn.execute("SELECT COUNT(*) as c FROM downloads WHERE status='failed'") as cur:
        failed = (await cur.fetchone())["c"]

    return JSONResponse({
        "tracks_indexed": track_count,
        "downloads_done": done,
        "downloads_failed": failed,
        "autopop_enabled": settings.autopop_enabled,
    })
