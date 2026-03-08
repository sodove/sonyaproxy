# sonyaproxy v3 — Telegram Bot + Yandex Music + Admin Panel

## Milestone 1: Settings DB + Admin Panel

### 1.1 Settings table in SQLite
- Таблица `settings (key TEXT PK, value TEXT)` в `db.py`
- Хелперы: `get_setting(key)`, `set_setting(key, value)`
- Миграция при `init_db()`

### 1.2 Mini admin panel
- `GET /admin/` — HTML страничка (Jinja2-free, просто f-string HTML)
- Basic Auth через gonic credentials (`_verify_client_auth` уже есть)
- Поля:
  - Yandex Music token (маскированный, кнопка обновить)
  - Telegram Bot token
  - Статус: yt-dlp version, YM token valid?, last autopop cycle, SC charts status
- `POST /admin/settings` — обновляет ключ в DB
- `GET /admin/status` — JSON со статусами

## Milestone 2: Yandex Music source

### 2.1 yandex-music-api integration
- `app/sources/yandex_music.py`
- `pip install yandex-music` в requirements.txt
- Token читается из DB (`get_setting("yandex_token")`)
- `search_yandex(query, limit=10)` — async поиск, возвращает `list[dict]`
- `download_yandex(track_id, artist, title, output_dir)` — скачивание трека

### 2.2 Integrate into search3
- `handle_search3` дополнительно ищет в YM если токен задан
- Виртуальные треки с `virt_ym_{track_id}`
- `handle_virtual_stream` обрабатывает `virt_ym_` prefix

### 2.3 Integrate into autopop
- Новый источник чартов: YM "Chart" плейлист (не требует Playwright)
- Добавить в `charts.py` как третий источник

## Milestone 3: Telegram Bot

### 3.1 Bot core
- `app/bot.py` — aiogram 3.x (async, fits FastAPI event loop)
- Token из DB (`get_setting("telegram_bot_token")`)
- Запуск polling в background task при startup (если токен задан)
- Hot-reload: при обновлении токена через admin — перезапуск polling

### 3.2 Commands
- `/start` — приветствие
- `/search <query>` или просто текст — поиск YT + SC + YM
  - Inline keyboard с результатами (artist — title, source icon)
  - Кнопка "Download" → скачивание → уведомление "Done, rescan triggered"
- URL detection:
  - `youtube.com/watch?v=...` → скачать через yt-dlp
  - `soundcloud.com/...` → скачать через yt-dlp
  - `music.yandex.ru/...` → скачать через yandex-music-api
  - Автоопределение по домену
- `/status` — статус сервисов, последний autopop, количество треков в индексе

### 3.3 Download flow
- Текст → `search_virtual()` + `search_yandex()` → inline buttons
- Выбор трека → `download_queue.download()` → ffmpeg tags → rescan
- URL → определение источника → прямое скачивание
- Progress: "Downloading...", "Tagging...", "Done! 🎵 Artist - Title"

## Milestone 4: Observability

### 4.1 Already done (this commit)
- Downloader: log start/finish/yt-dlp errors/ffmpeg tagging
- SC charts: log scrape attempts, retry, track counts
- Chart orchestrator: log source counts, failures

### 4.2 Structured logging (optional)
- JSON logging format for docker logs parsing
- Log levels configurable via env `LOG_LEVEL`

## New dependencies
- `aiogram>=3.0` — Telegram bot framework
- `yandex-music>=2.0` — Yandex Music API

## Config additions (.env)
```
TELEGRAM_BOT_TOKEN=     # (or set via admin panel)
YANDEX_MUSIC_TOKEN=     # (or set via admin panel)
LOG_LEVEL=INFO
```

## Docker changes
- Add `aiogram` and `yandex-music` to requirements.txt
- No new volumes needed

## File structure after implementation
```
app/
  main.py              — FastAPI + startup (bot, autopop, sync)
  bot.py               — Telegram bot (aiogram polling)
  config.py            — Settings from .env
  db.py                — SQLite init + settings helpers
  admin.py             — Admin panel routes
  downloader.py        — DownloadQueue + ffmpeg tags
  index.py             — TrackIndex
  search.py            — search3 XML augmentation
  proxy.py             — forward_to_gonic()
  normalizer.py        — text normalization
  musicbrainz.py       — MB enrichment
  ytdlp.py             — yt-dlp on-demand search
  sources/
    ytmusic.py         — YT Music Charts API
    sc_charts.py       — SoundCloud Playwright scraper
    yandex_music.py    — Yandex Music search + download
  autopop/
    loop.py            — autopop cycle
    charts.py          — chart orchestrator
    flavor.py          — FlavorConfig
```
