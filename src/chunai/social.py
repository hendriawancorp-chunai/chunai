"""Pagar media sosial: batas tindakan keluar per hari dan jeda minimum. Hanya pengaman; tidak ada trik menghindari deteksi."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlparse

from .timeutil import now

SOCIAL_DOMAINS = {"instagram.com", "linkedin.com", "facebook.com", "x.com", "twitter.com", "tiktok.com", "threads.net", "threads.com"}
DEFAULT_LIMIT = 15
MIN_GAP = 20.0                    # detik, tetap (bukan acak)


def is_social(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == d or host.endswith("." + d) for d in SOCIAL_DOMAINS)


def daily_limit() -> int:
    try:
        return int(os.environ.get("CHUNAI_SOCIAL_DAILY_LIMIT", DEFAULT_LIMIT))
    except ValueError:
        return DEFAULT_LIMIT


def default_path() -> Path:
    return Path(os.environ.get("CHUNAI_SOCIAL_FILE", "data/social_actions.json"))


def _load(path: Path) -> dict:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def count_today(path: Path) -> int:
    return int(_load(path).get(now().date().isoformat(), 0))


def check(path: Path) -> str | None:
    """Pesan penolakan bila batas harian tercapai; None bila boleh."""
    lim = daily_limit()
    if lim > 0 and count_today(path) >= lim:
        return (f"Batas tindakan media sosial hari ini tercapai ({lim}). Lanjutkan besok, atau naikkan CHUNAI_SOCIAL_DAILY_LIMIT di .env "
                "(batas ini melindungi akun Anda dari pembatasan platform).")
    return None


def record(path: Path) -> None:
    d = _load(path)
    today = now().date().isoformat()
    d = {k: v for k, v in d.items() if k >= today[:8] + "00"}      # simpan bulan berjalan saja
    d[today] = int(d.get(today, 0)) + 1
    d["_terakhir"] = time.time()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(d), encoding="utf-8")


def wait_needed(path: Path) -> float:
    last = float(_load(path).get("_terakhir", 0))
    return max(0.0, MIN_GAP - (time.time() - last)) if last else 0.0
