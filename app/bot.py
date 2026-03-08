import asyncio
import logging
import re
from typing import Any

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.db import get_setting, set_setting

logger = logging.getLogger("sonyaproxy.bot")

router = Router()

_URL_RE = re.compile(
    r'https?://(www\.)?(youtube\.com/watch\?v=|youtu\.be/|soundcloud\.com/|music\.yandex\.(ru|com)/)'
)


class AuthStates(StatesGroup):
    waiting_username = State()
    waiting_password = State()


async def _is_authorized(user_id: int) -> bool:
    from app.main import download_queue
    from app.db import get_setting
    val = await get_setting(download_queue._conn, f"tg_auth_{user_id}")
    return val == "1"


async def _set_authorized(user_id: int, value: bool):
    from app.main import download_queue
    from app.db import set_setting
    await set_setting(download_queue._conn, f"tg_auth_{user_id}", "1" if value else "0")


async def _verify_gonic_auth(username: str, password: str) -> bool:
    import httpx
    from app.config import settings
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.gonic_url}/rest/ping",
                params={"u": username, "p": password, "v": "1.16.1", "c": "sonyaproxy-bot"},
            )
            return r.status_code == 200 and "error" not in r.text.lower()
    except Exception:
        return False


# --- Auth handlers ---

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    if await _is_authorized(message.from_user.id):
        await message.answer(
            "sonyaproxy bot\n\n"
            "Send me:\n"
            "- Text to search tracks\n"
            "- YouTube/SoundCloud/Yandex Music URL to download\n"
            "- /status for service status\n"
            "- /logout to deauthorize"
        )
        return

    await message.answer("Welcome to sonyaproxy!\nPlease enter your gonic username:")
    await state.set_state(AuthStates.waiting_username)


@router.message(AuthStates.waiting_username)
async def auth_username(message: Message, state: FSMContext):
    await state.update_data(username=message.text.strip())
    await message.answer("Now enter your password:")
    await message.delete()
    await state.set_state(AuthStates.waiting_password)


@router.message(AuthStates.waiting_password)
async def auth_password(message: Message, state: FSMContext):
    data = await state.get_data()
    username = data.get("username", "")
    password = message.text.strip()

    # Delete password message for security
    try:
        await message.delete()
    except Exception:
        pass

    if await _verify_gonic_auth(username, password):
        await _set_authorized(message.from_user.id, True)
        await message.answer("Authorized! Send me a search query or URL.")
        logger.info("Bot: user %s authorized as %s", message.from_user.id, username)
    else:
        await message.answer("Wrong credentials. Try /start again.")
        logger.warning("Bot: failed auth for user %s", message.from_user.id)

    await state.clear()


@router.message(Command("logout"))
async def cmd_logout(message: Message):
    await _set_authorized(message.from_user.id, False)
    await message.answer("Logged out. /start to re-authenticate.")


# --- Authorized commands ---

@router.message(Command("status"))
async def cmd_status(message: Message):
    if not await _is_authorized(message.from_user.id):
        await message.answer("Please /start and authenticate first.")
        return

    from app.main import download_queue, track_index
    from app.config import settings

    conn = download_queue._conn
    async with conn.execute("SELECT COUNT(*) as c FROM track_index") as cur:
        tracks = (await cur.fetchone())["c"]
    async with conn.execute("SELECT COUNT(*) as c FROM downloads WHERE status='done'") as cur:
        done = (await cur.fetchone())["c"]
    async with conn.execute("SELECT COUNT(*) as c FROM downloads WHERE status='failed'") as cur:
        failed = (await cur.fetchone())["c"]

    ym_token = await get_setting(conn, "yandex_token")

    text = (
        f"Track index: {tracks}\n"
        f"Downloads: {done} done, {failed} failed\n"
        f"Autopop: {'on' if settings.autopop_enabled else 'off'}\n"
        f"Yandex Music: {'token set' if ym_token else 'no token'}"
    )
    await message.answer(text)


# --- Search & Download ---

@router.message(F.text)
async def handle_text(message: Message):
    if not await _is_authorized(message.from_user.id):
        await message.answer("Please /start and authenticate first.")
        return

    text = message.text.strip()

    # URL detection — extract all URLs from message
    urls = _URL_RE.findall(text)
    if urls:
        # Extract full URLs from the text
        full_urls = re.findall(r'https?://\S+', text)
        supported = [u for u in full_urls if _URL_RE.search(u)]
        if supported:
            await _handle_urls(message, supported)
            return

    # Text search
    await _handle_search(message, text)


async def _handle_search(message: Message, query: str):
    status_msg = await message.answer("Searching...")

    from app.ytdlp import search_virtual
    from app.main import download_queue

    conn = download_queue._conn
    ym_token = await get_setting(conn, "yandex_token")

    # Search YT+SC
    results = await search_virtual(query, count=5)

    # Search Yandex Music
    if ym_token:
        from app.sources.yandex_music import search_yandex
        ym_results = await search_yandex(ym_token, query, limit=5)
        results.extend(ym_results)

    if not results:
        await status_msg.edit_text("Nothing found.")
        return

    # Build inline keyboard
    buttons = []
    # Store results temporarily for callback
    _search_cache[message.from_user.id] = results

    for i, t in enumerate(results[:10]):
        source = t.get("source", "yt")
        icon = {"yt": "YT", "sc": "SC", "ym": "YM"}.get(source, "?")
        dur = int(t.get("duration", 0))
        dur_str = f"{dur // 60}:{dur % 60:02d}" if dur else ""
        label = f"[{icon}] {t['artist']} — {t['title']}"
        if dur_str:
            label += f" ({dur_str})"
        if len(label) > 60:
            label = label[:57] + "..."
        buttons.append([InlineKeyboardButton(
            text=label,
            callback_data=f"dl:{message.from_user.id}:{i}",
        )])

    await status_msg.edit_text(
        f"Found {len(results)} tracks for \"{query}\":",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
    )


# In-memory search results cache per user
_search_cache: dict[int, list[dict]] = {}


@router.callback_query(F.data.startswith("dl:"))
async def callback_download(callback: CallbackQuery):
    parts = callback.data.split(":")
    if len(parts) != 3:
        await callback.answer("Invalid callback")
        return

    user_id = int(parts[1])
    idx = int(parts[2])

    if not await _is_authorized(user_id):
        await callback.answer("Not authorized")
        return

    results = _search_cache.get(user_id, [])
    if idx >= len(results):
        await callback.answer("Result expired, search again")
        return

    track = results[idx]
    await callback.answer("Starting download...")
    await callback.message.edit_text(
        f"Downloading: {track['artist']} — {track['title']}..."
    )

    try:
        path = await _download_track(track)
        if path:
            await callback.message.edit_text(
                f"Done! {track['artist']} — {track['title']}"
            )
        else:
            await callback.message.edit_text(
                f"Failed to download: {track['artist']} — {track['title']}"
            )
    except Exception as e:
        logger.warning("Bot download failed", exc_info=True)
        await callback.message.edit_text(f"Error: {e}")


async def _download_track(track: dict) -> str | None:
    from app.main import download_queue
    from app.config import settings
    from pathlib import Path

    source = track.get("source", "yt")
    virt_id = track.get("id", "")

    if source == "ym":
        # Yandex Music download
        conn = download_queue._conn
        ym_token = await get_setting(conn, "yandex_token")
        if not ym_token:
            return None

        from app.sources.yandex_music import download_yandex
        output_dir = Path(settings.gonic_music_dir) / "Virtual Downloads" / _safe(track["artist"]) / "Singles"
        result = await download_yandex(
            ym_token, track["ym_track_id"], track["artist"], track["title"], output_dir
        )
        if result:
            await download_queue.trigger_rescan()
            return result["path"]
        return None
    else:
        # YT/SC download via yt-dlp
        url = track.get("youtube_url") or track.get("url", "")
        if not url and "yt" in virt_id:
            yt_id = virt_id.replace("virt_yt_", "")
            url = f"https://www.youtube.com/watch?v={yt_id}"
        if not url and "sc" in virt_id:
            sc_id = virt_id.replace("virt_sc_", "")
            url = f"https://api.soundcloud.com/tracks/{sc_id}"

        if not url:
            return None

        result = await download_queue.download(
            virt_id=virt_id,
            youtube_url=url,
            artist=track.get("artist", "Unknown"),
            title=track.get("title", "Unknown"),
        )
        return result["path"]


def _safe(s: str) -> str:
    import re as _re
    return _re.sub(r'[<>:"/\\|?*]', '_', s)


async def _download_single_url(url: str) -> str:
    """Download a single URL, return status string."""
    from app.main import download_queue
    from app.config import settings
    from pathlib import Path

    try:
        if "music.yandex." in url:
            m = re.search(r'/track/(\d+)', url)
            if not m:
                return f"Can't parse YM URL: {url}"

            track_id = int(m.group(1))
            conn = download_queue._conn
            ym_token = await get_setting(conn, "yandex_token")
            if not ym_token:
                return "YM token not set"

            from app.sources.yandex_music import download_yandex
            output_dir = Path(settings.gonic_music_dir) / "Virtual Downloads" / "Yandex Music" / "Singles"
            result = await download_yandex(ym_token, track_id, output_dir=output_dir)
            if result:
                return f"{result['artist']} — {result['title']}"
            return f"YM unavailable: track {track_id}"
        else:
            virt_id = f"virt_url_{hash(url) & 0xFFFFFFFF:08x}"
            result = await download_queue.download(
                virt_id=virt_id,
                youtube_url=url,
                artist="Unknown",
                title=url.split("/")[-1][:50],
            )
            return f"{result['artist']} — {result['title']}"
    except Exception as e:
        logger.warning("URL download failed: %s", url, exc_info=True)
        return f"Error: {url.split('/')[-1][:30]}"


async def _handle_urls(message: Message, urls: list[str]):
    from app.main import download_queue

    status_msg = await message.answer(f"Downloading {len(urls)} link(s)...")

    results = []
    for i, url in enumerate(urls):
        if len(urls) > 1:
            try:
                await status_msg.edit_text(f"Downloading {i+1}/{len(urls)}...")
            except Exception:
                pass
        result = await _download_single_url(url)
        results.append(result)

    await download_queue.trigger_rescan()

    text = "\n".join(f"• {r}" for r in results)
    await status_msg.edit_text(f"Done!\n{text}")


def _make_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    new_router = Router()
    # Re-register all handlers on a fresh router
    new_router.message.register(cmd_start, Command("start"))
    new_router.message.register(auth_username, AuthStates.waiting_username)
    new_router.message.register(auth_password, AuthStates.waiting_password)
    new_router.message.register(cmd_logout, Command("logout"))
    new_router.message.register(cmd_status, Command("status"))
    new_router.message.register(handle_text, F.text)
    new_router.callback_query.register(callback_download, F.data.startswith("dl:"))
    dp.include_router(new_router)
    return dp


async def start_bot(token: str) -> tuple[Bot, Dispatcher]:
    bot = Bot(token=token)
    dp = _make_dispatcher()
    logger.info("Telegram bot starting polling...")
    return bot, dp


async def run_polling(bot: Bot, dp: Dispatcher):
    try:
        await dp.start_polling(bot)
    except Exception:
        logger.exception("Bot polling failed")
    finally:
        await bot.session.close()
