import os, importlib, pytest
from unittest.mock import patch

def test_settings_loads_from_env():
    env = {
        "GONIC_URL": "http://gonic:4533",
        "GONIC_USER": "testuser",
        "GONIC_PASS": "testpass",
        "GONIC_MUSIC_DIR": "/tmp/music",
        "PROXY_PORT": "4041",
        "PREFETCH_COUNT": "5",
        "YTDLP_FORMAT": "bestaudio",
    }
    with patch.dict(os.environ, env, clear=True):
        import config
        importlib.reload(config)
        s = config.settings
        assert s.gonic_url == "http://gonic:4533"
        assert s.gonic_user == "testuser"
        assert s.proxy_port == 4041
        assert s.prefetch_count == 5
