"""Penyimpanan data saham lokal dengan jejak sumber (provenance). data/saham/<KODE>/prices.csv + meta.json."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

import pandas as pd

from ..timeutil import now

_KODE = re.compile(r"^[A-Z0-9^][A-Z0-9.\-]{0,11}$")
COLS = ["open", "high", "low", "close", "volume"]


class SahamError(ValueError):
    ...


def root() -> Path:
    return Path(os.environ.get("CHUNAI_SAHAM_DIR", "data/saham"))


def norm_kode(kode: str) -> str:
    k = str(kode or "").strip().upper()
    if k.endswith(".JK"):
        k = k[:-3]
    if not _KODE.match(k):
        raise SahamError(f"Kode saham '{str(kode)[:20]}' tidak valid (huruf/angka, mis. BBCA, TLKM, ^JKSE).")
    return k


def dir_of(kode: str) -> Path:
    return root() / norm_kode(kode).replace("^", "_")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_meta(kode: str) -> list[dict]:
    try:
        return json.loads((dir_of(kode) / "meta.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_prices(kode: str, df: pd.DataFrame, sumber: str, metode: str, berkas: str = "", digest: str = "", catatan: list[str] | None = None) -> dict:
    """Gabung dengan data lama (tanggal sama: data baru menimpa), simpan, catat jejak sumber."""
    d = dir_of(kode)
    d.mkdir(parents=True, exist_ok=True)
    old = load_prices(kode) if (d / "prices.csv").exists() else None
    new = df.copy()
    replaced = 0
    if old is not None and len(old):
        replaced = int(new.index.isin(old.index).sum())
        new = pd.concat([old[~old.index.isin(new.index)], new]).sort_index()
    new.to_csv(d / "prices.csv", index_label="date")
    entry = {"jenis": "harga", "sumber": str(sumber)[:200], "metode": metode, "berkas": berkas, "sha256": digest,
             "diambil": now().isoformat(timespec="seconds"), "periode": f"{df.index.min().date()}..{df.index.max().date()}",
             "baris": int(len(df)), "menimpa": replaced, "catatan": catatan or []}
    meta = load_meta(kode) + [entry]
    (d / "meta.json").write_text(json.dumps(meta[-50:], ensure_ascii=False, indent=1), encoding="utf-8")
    return entry


def load_prices(kode: str) -> pd.DataFrame:
    p = dir_of(kode) / "prices.csv"
    if not p.is_file():
        raise SahamError(f"Belum ada data harga untuk {norm_kode(kode)}. Unggah berkas harga lalu panggil impor_data_saham.")
    df = pd.read_csv(p, parse_dates=["date"], index_col="date").sort_index()
    return df


def list_codes() -> list[str]:
    r = root()
    if not r.is_dir():
        return []
    return sorted(p.name.replace("_", "^", 1) if p.name.startswith("_") else p.name for p in r.iterdir() if (p / "prices.csv").is_file())
