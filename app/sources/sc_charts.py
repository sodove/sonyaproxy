import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("sonyaproxy.sc_charts")

_GENRE_MAP = {
    "electronic": "electronic",
    "hip-hop": "hip-hop",
    "bass": "electronic",
    "rock": "rock",
}

_SUPPORTED_REGIONS = {"US": "us", "UK": "uk"}

_CACHE_DIR = Path("/tmp/sc-playwright-cache")
_GOTO_TIMEOUT = 180_000
_RETRY_TIMEOUT = 60_000


def _chart_url(genre: str, region: str) -> str | None:
    sc_genre = _GENRE_MAP.get(genre)
    sc_region = _SUPPORTED_REGIONS.get(region)
    if not sc_genre or not sc_region:
        return None
    return f"https://soundcloud.com/music-charts-{sc_region}/sets/{sc_genre}"


async def _extract_tracks(page) -> list[dict]:
    try:
        accept_btn = page.locator("button#onetrust-accept-btn-handler")
        await accept_btn.click(timeout=3000)
    except Exception:
        pass

    await page.wait_for_selector(".trackList__item", timeout=15000)

    return await page.evaluate("""
        () => {
            const items = document.querySelectorAll('.trackList__item');
            return Array.from(items).map(item => {
                const titleEl = item.querySelector('.trackItem__trackTitle');
                const artistEl = item.querySelector('.trackItem__username');
                const linkEl = item.querySelector('a.trackItem__trackTitle');
                return {
                    title: titleEl ? titleEl.textContent.trim() : '',
                    artist: artistEl ? artistEl.textContent.trim() : '',
                    url: linkEl ? 'https://soundcloud.com' + linkEl.getAttribute('href') : '',
                };
            }).filter(t => t.title && t.artist);
        }
    """)


async def _scrape_sc_playlist(url: str) -> list[dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("playwright not installed, skipping SC charts")
        return []

    tracks = []
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)

    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir=str(_CACHE_DIR),
                headless=True,
            )
            page = await context.new_page()

            # First attempt
            try:
                await page.goto(url, wait_until="networkidle", timeout=_GOTO_TIMEOUT)
                tracks = await _extract_tracks(page)
            except Exception as first_err:
                logger.warning("SC chart first attempt failed, retrying: %s", first_err)
                # Retry once with reload
                try:
                    await page.reload(wait_until="networkidle", timeout=_RETRY_TIMEOUT)
                    tracks = await _extract_tracks(page)
                except Exception:
                    logger.warning("SC chart retry also failed: %s", url, exc_info=True)

            await context.close()
    except Exception:
        logger.warning("Failed to scrape SC chart: %s", url, exc_info=True)
        return []

    return [
        {
            "url": t["url"],
            "title": t["title"],
            "artist": t["artist"],
            "duration": 0,
            "source_id": t["url"].split("/")[-1] if t["url"] else "",
            "source": "sc",
        }
        for t in tracks
    ]


async def fetch_sc_chart(
    genre: str, region: str, limit: int = 20
) -> list[dict[str, Any]]:
    url = _chart_url(genre, region)
    if not url:
        return []
    tracks = await _scrape_sc_playlist(url)
    return tracks[:limit]
