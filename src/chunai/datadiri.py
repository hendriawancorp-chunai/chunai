"""Lembar data diri pengguna (untuk pengisian form/lamaran). Disimpan lokal (data/data_diri.json, izin 600), tidak pernah di repo.
Tiap butir punya tingkat: umum (profesional), pribadi (kontak/alamat/tgl lahir), sensitif (NIK, keluarga, rekening, dst.)."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from .browser import scan_injection

TINGKAT = ("umum", "pribadi", "sensitif")
MAX_ITEMS, MAX_VALUE = 120, 3000
_KEY = re.compile(r"^[a-z0-9_ ./-]{1,60}$")
# rahasia akses (bukan data diri): ditolak
_SECRET = re.compile(r"(sk-ant-|oat01|api[_ -]?key|kata sandi|password|passwd|\botp\b|\bcvv\b|\bcvc\b|token|bot\d{6,}:|\bpin\b)", re.I)


class DataDiriError(ValueError):
    ...


def default_path() -> Path:
    return Path(os.environ.get("CHUNAI_DATA_DIRI", "data/data_diri.json"))


def load(path: Path) -> dict[str, dict]:
    try:
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return {k: v for k, v in d.items() if isinstance(v, dict) and "nilai" in v} if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(path: Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    if os.name == "posix":
        os.chmod(tmp, 0o600)
    tmp.replace(path)


def clean_key(k: str) -> str:
    k = re.sub(r"\s+", " ", str(k).strip().lower())
    if not _KEY.match(k):
        raise DataDiriError(f"Kunci '{k[:30]}' tidak valid (huruf/angka/spasi, maks 60).")
    return k


def validate_items(items) -> list[tuple[str, str, str]]:
    if not isinstance(items, list) or not items:
        raise DataDiriError("'butir' harus daftar [{kunci, nilai, tingkat}] yang tidak kosong.")
    out, errors = [], []
    for n, it in enumerate(items, 1):
        try:
            if not isinstance(it, dict):
                raise DataDiriError("bukan objek")
            k, v, t = clean_key(it.get("kunci", "")), str(it.get("nilai", "")).strip(), str(it.get("tingkat", "")).strip().lower()
            if not v:
                raise DataDiriError("nilai kosong")
            if len(v) > MAX_VALUE:
                raise DataDiriError(f"nilai terlalu panjang (maks {MAX_VALUE})")
            if t not in TINGKAT:
                raise DataDiriError(f"tingkat harus salah satu dari {', '.join(TINGKAT)}")
            if _SECRET.search(v) or _SECRET.search(k):
                raise DataDiriError("berisi rahasia akses (kata sandi/token/PIN/OTP): tidak disimpan")
            if scan_injection(v):
                raise DataDiriError("tampak berisi instruksi untuk agen, bukan data")
            out.append((k, v, t))
        except DataDiriError as e:
            errors.append(f"butir {n}: {e}")
    if errors:
        raise DataDiriError("Tidak ada yang disimpan. Perbaiki:\n- " + "\n- ".join(errors))
    return out


def save_items(path: Path, items) -> int:
    data = load(path)
    valid = validate_items(items)
    new_keys = {k for k, _, _ in valid if k not in data}
    if len(data) + len(new_keys) > MAX_ITEMS:
        raise DataDiriError(f"Lembar data penuh (maks {MAX_ITEMS} butir).")
    for k, v, t in valid:
        data[k] = {"nilai": v, "tingkat": t}
    _save(path, data)
    return len(valid)


def delete(path: Path, key: str) -> bool:
    data = load(path)
    k = clean_key(key)
    if k not in data:
        return False
    del data[k]
    _save(path, data)
    return True


def render(data: dict[str, dict], tingkat: list[str] | None = None) -> str:
    rows = [(k, v) for k, v in sorted(data.items()) if not tingkat or v["tingkat"] in tingkat]
    if not rows:
        return "(lembar data kosong)"
    return "\n".join(f"- [{v['tingkat']}] {k}: {v['nilai']}" for k, v in rows)
