import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Settings:
    gonic_url: str = os.getenv("GONIC_URL", "http://localhost:4533")
    gonic_user: str = os.getenv("GONIC_USER", "admin")
    gonic_pass: str = os.getenv("GONIC_PASS", "secret")
    gonic_music_dir: str = os.getenv("GONIC_MUSIC_DIR", "/music")
    proxy_port: int = int(os.getenv("PROXY_PORT", "4040"))
    prefetch_count: int = int(os.getenv("PREFETCH_COUNT", "3"))
    ytdlp_format: str = os.getenv("YTDLP_FORMAT", "bestaudio")
    ytdlp_audio_format: str = os.getenv("YTDLP_AUDIO_FORMAT", "mp3")
    ytdlp_path: str = os.getenv("YTDLP_PATH", "yt-dlp")
    autopop_enabled: bool = os.getenv("AUTOPOP_ENABLED", "false").lower() == "true"
    autopop_flavor_path: str = os.getenv("AUTOPOP_FLAVOR_PATH", "flavor.yml")
    autopop_startup_delay: int = int(os.getenv("AUTOPOP_STARTUP_DELAY", "60"))
    db_path: str = os.getenv("DB_PATH", "sonyaproxy.db")
    telegram_bot_token: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
    yandex_music_token: str = os.getenv("YANDEX_MUSIC_TOKEN", "")

settings = Settings()
