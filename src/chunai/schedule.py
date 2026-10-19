"""Jadwal: pengingat dan tugas terjadwal. Disimpan di data/schedules.json; waktu selalu zona pengguna (CHUNAI_TZ, default WIB).
Murni (tanpa jaringan/agen): perhitungan waktu berikutnya, validasi, penyimpanan."""
from __future__ import annotations

import json
import os
import re
import secrets
from datetime import datetime, time, timedelta
from pathlib import Path

from .timeutil import BULAN, HARI, describe, now, tz

MAX_TASKS = 20
MAX_AGENT_TASKS = 10
TIPE = ("sekali", "harian", "mingguan", "bulanan")
JENIS = ("pengingat", "tugas")
_HARI = {n.lower(): i for i, n in enumerate(HARI)}
_HARI.update({"sen": 0, "sel": 1, "rab": 2, "kam": 3, "jum": 4, "sab": 5, "min": 6, "ahad": 6})
_HHMM = re.compile(r"^([01]?\d|2[0-3])[:.]([0-5]\d)$")


class ScheduleError(ValueError):
    ...


def default_path() -> Path:
    return Path(os.environ.get("CHUNAI_SCHEDULE_FILE", "data/schedules.json"))


def parse_hari(v) -> list[int]:
    items = v if isinstance(v, (list, tuple)) else re.split(r"[,\s/]+", str(v or ""))
    out = []
    for it in items:
        s = str(it).strip().lower()
        if not s:
            continue
        if s.isdigit() and 0 <= int(s) <= 6:
            out.append(int(s))
        elif s in _HARI:
            out.append(_HARI[s])
        else:
            raise ScheduleError(f"Hari '{it}' tidak dikenal (senin..minggu).")
    return sorted(set(out))


def normalize_spec(args: dict) -> dict:
    """Ubah argumen tool jadi spesifikasi jadwal yang bersih; lempar ScheduleError bila tidak valid."""
    tipe = str(args.get("tipe", "")).strip().lower()
    if tipe not in TIPE:
        raise ScheduleError(f"'tipe' harus salah satu dari {', '.join(TIPE)}.")
    m = _HHMM.match(str(args.get("waktu", "")).strip())
    if not m:
        raise ScheduleError("'waktu' harus format JJ:MM (24 jam, zona waktu pengguna), mis. 08:00.")
    spec: dict = {"tipe": tipe, "waktu": f"{int(m.group(1)):02d}:{m.group(2)}"}
    if tipe == "sekali":
        try:
            spec["tanggal"] = datetime.strptime(str(args.get("tanggal", "")).strip(), "%Y-%m-%d").date().isoformat()
        except ValueError:
            raise ScheduleError("Jadwal 'sekali' butuh 'tanggal' format YYYY-MM-DD.") from None
    elif tipe == "mingguan":
        days = parse_hari(args.get("hari"))
        if not days:
            raise ScheduleError("Jadwal 'mingguan' butuh 'hari' (mis. 'senin' atau 'senin,kamis').")
        spec["hari"] = days
    elif tipe == "bulanan":
        try:
            d = int(args.get("tgl"))
        except (TypeError, ValueError):
            raise ScheduleError("Jadwal 'bulanan' butuh 'tgl' (1-28).") from None
        if not 1 <= d <= 28:
            raise ScheduleError("'tgl' bulanan harus 1-28 (agar ada di semua bulan).")
        spec["tgl"] = d
    return spec


def _at(day, hhmm: str) -> datetime:
    h, mi = map(int, hhmm.split(":"))
    return datetime.combine(day, time(h, mi), tzinfo=tz())


def next_run(spec: dict, after: datetime) -> datetime | None:
    """Waktu eksekusi pertama yang STRICTLY setelah `after`; None bila jadwal 'sekali' sudah lewat."""
    after = after.astimezone(tz())
    t, w = spec["tipe"], spec["waktu"]
    if t == "sekali":
        dt = _at(datetime.strptime(spec["tanggal"], "%Y-%m-%d").date(), w)
        return dt if dt > after else None
    day = after.date()
    for _ in range(0, 400):
        cand = _at(day, w)
        if cand > after:
            if t == "harian" or (t == "mingguan" and day.weekday() in spec["hari"]) or (t == "bulanan" and day.day == spec["tgl"]):
                return cand
        day += timedelta(days=1)
    return None


def render_spec(spec: dict) -> str:
    w = spec["waktu"].replace(":", ".")
    t = spec["tipe"]
    if t == "sekali":
        d = datetime.strptime(spec["tanggal"], "%Y-%m-%d")
        return f"sekali, {d.day} {BULAN[d.month - 1]} {d.year} pukul {w}"
    if t == "harian":
        return f"setiap hari pukul {w}"
    if t == "mingguan":
        return f"setiap {', '.join(HARI[i] for i in spec['hari'])} pukul {w}"
    return f"setiap tanggal {spec['tgl']} pukul {w}"


# ---------- penyimpanan ----------
def load(path: Path) -> list[dict]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return [t for t in data if isinstance(t, dict) and "id" in t] if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def save(path: Path, tasks: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(tasks, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def add(path: Path, nama: str, jenis: str, isi: str, spec: dict, at: datetime | None = None) -> dict:
    jenis = str(jenis).strip().lower()
    if jenis not in JENIS:
        raise ScheduleError("'jenis' harus 'pengingat' (hanya pesan) atau 'tugas' (agen mengerjakan perintah).")
    isi = str(isi).strip()
    if not isi:
        raise ScheduleError("'isi' kosong.")
    if len(isi) > 1500:
        raise ScheduleError("'isi' terlalu panjang (maks 1500 karakter).")
    at = at or now()
    nxt = next_run(spec, at)
    if nxt is None:
        raise ScheduleError("Waktu itu sudah lewat. Pilih waktu di masa depan.")
    tasks = load(path)
    if len(tasks) >= MAX_TASKS:
        raise ScheduleError(f"Jadwal penuh (maks {MAX_TASKS}). Hapus yang tidak perlu dulu.")
    if jenis == "tugas" and sum(1 for t in tasks if t.get("jenis") == "tugas") >= MAX_AGENT_TASKS:
        raise ScheduleError(f"Tugas agen terjadwal penuh (maks {MAX_AGENT_TASKS}).")
    task = {"id": secrets.token_hex(3), "nama": str(nama).strip()[:60] or "tanpa nama", "jenis": jenis, "isi": isi, "jadwal": spec,
            "berikutnya": nxt.isoformat(), "dibuat": at.isoformat(), "terakhir": None, "hasil": None}
    tasks.append(task)
    save(path, tasks)
    return task


def remove(path: Path, tid: str) -> bool:
    tasks = load(path)
    keep = [t for t in tasks if t["id"] != str(tid).strip().lower()]
    if len(keep) == len(tasks):
        return False
    save(path, keep)
    return True


def render_list(tasks: list[dict]) -> str:
    if not tasks:
        return "(belum ada jadwal)"
    rows = []
    for t in tasks:
        nxt = t.get("berikutnya")
        nxt_txt = describe(parse_dt(nxt)) if nxt else "selesai"
        rows.append(f"- [{t['id']}] {t['nama']} ({t['jenis']}): {render_spec(t['jadwal'])}. Berikutnya: {nxt_txt}. "
                    f"{'Isi: ' + t['isi'][:120]}")
    return "\n".join(rows)


def parse_dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso).astimezone(tz())


def due(tasks: list[dict], at: datetime) -> list[dict]:
    return [t for t in tasks if t.get("berikutnya") and parse_dt(t["berikutnya"]) <= at]
