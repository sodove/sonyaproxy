import re
from unidecode import unidecode

_FEAT_RE = re.compile(r'\(feat\.?[^)]*\)|\[feat\.?[^\]]*\]', re.IGNORECASE)
_PROD_RE = re.compile(r'\(prod\.?[^)]*\)|\[prod\.?[^\]]*\]', re.IGNORECASE)
_REMIX_RE = re.compile(r'\((?:official\s+)?remix\)', re.IGNORECASE)
_DASH_PREFIX_RE = re.compile(r'^[^-]+-\s+')  # "Artist - Title" -> "Title"

def normalize(text: str) -> str:
    t = text.strip()
    t = unidecode(t)
    t = t.lower()
    t = _FEAT_RE.sub('', t)
    t = _PROD_RE.sub('', t)
    t = _REMIX_RE.sub('', t)
    t = _DASH_PREFIX_RE.sub('', t)
    t = re.sub(r'[^\w\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t
