"""Waktu & zona waktu pengguna. Server cloud memakai UTC; ChunAI memakai CHUNAI_TZ (default Asia/Jakarta = WIB)."""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

HARI = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"]
ABBR = {"Asia/Jakarta": "WIB", "Asia/Pontianak": "WIB", "Asia/Makassar": "WITA", "Asia/Jayapura": "WIT"}


def tz_name() -> str:
    return os.environ.get("CHUNAI_TZ", "Asia/Jakarta")


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(tz_name())
    except Exception:
        return ZoneInfo("Asia/Jakarta")


def now() -> datetime:
    return datetime.now(tz())


def describe(dt: datetime | None = None) -> str:
    """Contoh: 'Kamis, 15 Oktober 2026, pukul 12.09 WIB (UTC+7)'."""
    dt = dt or now()
    off = dt.utcoffset()
    hours = (off.total_seconds() / 3600) if off else 0
    utc = f"UTC{int(hours):+d}" if hours == int(hours) else f"UTC{hours:+.1f}"
    abbr = ABBR.get(getattr(dt.tzinfo, "key", ""), utc)
    return f"{HARI[dt.weekday()]}, {dt.day} {BULAN[dt.month - 1]} {dt.year}, pukul {dt:%H.%M} {abbr} ({utc})"
