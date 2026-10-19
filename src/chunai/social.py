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


# Batas karakter umum (dapat berubah; platform yang menentukan). (platform, jenis) -> maks karakter
LIMITS = {("linkedin", "posting"): 3000, ("linkedin", "komentar"): 1250, ("linkedin", "headline"): 220, ("linkedin", "about"): 2600,
          ("linkedin", "catatan_koneksi"): 300, ("linkedin", "pesan"): 8000,
          ("instagram", "caption"): 2200, ("instagram", "bio"): 150, ("instagram", "komentar"): 2200, ("instagram", "dm"): 1000}
MAX_HASHTAGS = {"instagram": 30, "linkedin": 10}


def periksa_draf(platform: str, jenis: str, teks: str, pribadi: dict[str, str] | None = None) -> list[str]:
    """Daftar masalah draf: melebihi batas, hashtag berlebih, memuat data pribadi/sensitif pengguna. Kosong = layak ditinjau."""
    import re
    platform, jenis = platform.strip().lower(), jenis.strip().lower()
    issues = []
    lim = LIMITS.get((platform, jenis))
    if lim is None:
        known = sorted({f"{p}/{j}" for p, j in LIMITS})
        issues.append(f"jenis '{platform}/{jenis}' tidak dikenal (batas panjang tidak diperiksa). Dikenal: {', '.join(known)}")
    elif len(teks) > lim:
        issues.append(f"{len(teks)} karakter melebihi batas {lim} untuk {platform}/{jenis}")
    tags = len(re.findall(r"(?<!\w)#\w+", teks))
    if tags > MAX_HASHTAGS.get(platform, 30):
        issues.append(f"{tags} hashtag terlalu banyak (maks {MAX_HASHTAGS.get(platform, 30)}); kurangi agar tidak tampak spam")
    flat = re.sub(r"[\s\-\.\(\)]", "", teks.lower())
    for k, v in (pribadi or {}).items():
        vv = re.sub(r"[\s\-\.\(\)]", "", str(v).lower())
        if len(vv) >= 6 and vv in flat:
            issues.append(f"memuat data pribadi/sensitif '{k}': jangan dipublikasikan")
    return issues


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
