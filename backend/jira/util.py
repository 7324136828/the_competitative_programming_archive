import re
import secrets
import time
from datetime import datetime, timezone
from urllib.parse import quote

# ---------------------------------------------------------------------------
# Clock: fakeable in tests (replaces vitest fake timers)
# ---------------------------------------------------------------------------

_fake_ms: float | None = None


def set_fake_time_ms(ms: float | None):
    global _fake_ms
    _fake_ms = ms


def now_ms() -> float:
    return _fake_ms if _fake_ms is not None else time.time() * 1000


def now_iso() -> str:
    dt = datetime.fromtimestamp(now_ms() / 1000, tz=timezone.utc)
    return dt.isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def to_iso(v) -> str | None:
    if not v:
        return None
    s = str(v).strip()
    if not s:
        return None
    # Legacy 'YYYY-MM-DD HH:MM:SS' (optionally fractional) -> UTC ISO
    m = re.match(r'^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})(\.\d+)?(Z)?$', s)
    if m and not s.endswith('Z') and not re.search(r'[+-]\d{2}:?\d{2}$', s):
        return f"{m.group(1)}T{m.group(2)}{m.group(3) or ''}Z"
    return s


def parse_ms(v) -> float | None:
    if not v:
        return None
    iso = to_iso(v)
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso.replace('Z', '+00:00'))
    except ValueError:
        return None
    return dt.timestamp() * 1000


def format_duration(seconds) -> str:
    if seconds is None:
        return '0s'
    try:
        if seconds != seconds:  # NaN
            return '0s'
    except TypeError:
        return '0s'
    s = max(0, round(seconds))
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    parts = []
    if d:
        parts.append(f'{d}d')
    if h:
        parts.append(f'{h}h')
    if m:
        parts.append(f'{m}m')
    if s or not parts:
        parts.append(f'{s}s')
    return ' '.join(parts)


# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------

_BASE36 = '0123456789abcdefghijklmnopqrstuvwxyz'


def _to_base36(n: int) -> str:
    if n <= 0:
        return '0'
    out = ''
    while n:
        n, r = divmod(n, 36)
        out = _BASE36[r] + out
    return out


def new_id(prefix: str) -> str:
    return f"{prefix}_{_to_base36(int(now_ms()))}{secrets.token_hex(4)}"


# ---------------------------------------------------------------------------
# Avatars
# ---------------------------------------------------------------------------

_AVATAR_COLORS = [
    '#0052CC', '#36B37E', '#FF5630', '#6554C0', '#FFAB00',
    '#00B8D9', '#FF8B00', '#00875A', '#DE350B', '#5243AA',
]


def _hash_name(name: str) -> int:
    h = 0
    for ch in name:
        h = (h * 31 + ord(ch)) & 0xFFFFFFFF
    return h


def generate_avatar(name: str) -> str:
    words = [w for w in re.split(r'\s+', name) if w]
    initials = ''.join(w[0].upper() for w in words[:2]) or '?'
    color = _AVATAR_COLORS[_hash_name(name) % len(_AVATAR_COLORS)]
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        f'<rect width="100" height="100" fill="{color}"/>'
        f'<text x="50" y="50" dy="0.35em" text-anchor="middle" font-family="sans-serif" '
        f'font-size="40" fill="#ffffff">{initials}</text></svg>'
    )
    return 'data:image/svg+xml;utf8,' + quote(svg)
