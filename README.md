# sonyaproxy

Прокси между Subsonic-клиентами (Symfonium, DSub и т.д.) и [gonic](https://github.com/sentriz/gonic), добавляющий виртуальные треки из YouTube, SoundCloud и Яндекс.Музыки.

## Что умеет

- **Поиск** — при поиске в клиенте результаты дополняются треками из YouTube и SoundCloud. Выбираешь трек — он скачивается на лету и стримится. Работает только если клиент отправляет поисковые запросы на сервер через `search3`. Некоторые клиенты (например, Symfonium) ищут локально по своему кешу и не обращаются к серверу — в таком случае виртуальные треки в поиске не появятся, используй Telegram-бот.
- **Telegram-бот** — поиск треков, скачивание по ссылкам (YouTube, SoundCloud, Яндекс.Музыка). Поддерживает несколько ссылок в одном сообщении. Авторизация через gonic-креды.
- **Autopop** — автоматически подкачивает треки из чартов YT Music и SoundCloud по расписанию. Настраивается через `flavor.yml` (жанры, языки, регионы, пятничный буст).
- **Админка** — веб-панель `/admin/` для управления токенами (Яндекс.Музыка, Telegram-бот) и просмотра статуса. Авторизация через gonic.

## Быстрый старт

1. Создай `.env`:

```env
GONIC_URL=http://localhost:4533
GONIC_USER=admin
GONIC_PASS=yourpassword
GONIC_MUSIC_DIR=/path/to/music
PROXY_PORT=4040

# Опционально
AUTOPOP_ENABLED=true
TELEGRAM_BOT_TOKEN=123456:ABC...
```

2. Запусти:

```bash
docker compose up -d --build
```

3. В Subsonic-клиенте укажи адрес `http://your-server:4040` вместо gonic.

## Настройка autopop

Файл `flavor.yml` управляет автоматической подкачкой треков:

```yaml
genres:
  electronic: 0.3
  hip-hop: 0.3
  bass: 0.2
  rock: 0.1
  other: 0.1

languages:
  ru: 0.4
  en: 0.5
  other: 0.1

chart_regions:
  - RU
  - US

refresh_interval_hours: 12
max_tracks_per_cycle: 20

release_day_boost:
  days: [friday]
  interval_hours: 4
  track_multiplier: 2.0
```

## Переменные окружения

| Переменная | По умолчанию | Описание |
|---|---|---|
| `GONIC_URL` | `http://localhost:4533` | Адрес gonic |
| `GONIC_USER` | `admin` | Пользователь gonic |
| `GONIC_PASS` | `secret` | Пароль gonic |
| `GONIC_MUSIC_DIR` | `/music` | Путь к музыке (должен совпадать с gonic) |
| `PROXY_PORT` | `4040` | Порт прокси |
| `AUTOPOP_ENABLED` | `false` | Включить autopop |
| `AUTOPOP_STARTUP_DELAY` | `60` | Задержка перед первым циклом (сек) |
| `AUTOPOP_FLAVOR_PATH` | `flavor.yml` | Путь к конфигу autopop |
| `TELEGRAM_BOT_TOKEN` | — | Токен Telegram-бота (или через админку) |
| `YTDLP_FORMAT` | `bestaudio` | Формат yt-dlp |

## Telegram-бот

1. Создай бота через [@BotFather](https://t.me/BotFather)
2. Укажи токен в `.env` или через админку (`/admin/`)
3. Напиши боту `/start` и авторизуйся через gonic логин/пароль
4. Отправляй текст для поиска или ссылки для скачивания

## Стек

- Python 3.12, FastAPI, uvicorn
- yt-dlp + ffmpeg
- Playwright (SoundCloud-чарты)
- aiogram 3 (Telegram-бот)
- yandex-music (Яндекс.Музыка)
- aiosqlite (SQLite для индекса и настроек)
