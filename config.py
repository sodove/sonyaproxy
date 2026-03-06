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
    ytdlp_format: str = os.getenv("YTDLP_FORMAT", "bestaudio[ext=opus]/bestaudio")
    ytdlp_path: str = os.getenv("YTDLP_PATH", "yt-dlp")

settings = Settings()
