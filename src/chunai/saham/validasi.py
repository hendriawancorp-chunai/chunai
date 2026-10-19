"""Validasi data harga: kesegaran, kelengkapan, konsistensi OHLC, lonjakan tak wajar. Hasil: lolos / lolos_dengan_catatan / ditolak."""
from __future__ import annotations

import pandas as pd

from ..timeutil import now

STALE_DAYS = 5           # hari kalender (mencakup akhir pekan/libur pendek)
GAP_DAYS = 7             # bolong antar-tanggal (hari kalender) yang dianggap mencurigakan
JUMP = 0.35              # |return harian| di atas ini = anomali (batas auto reject IDX 15-35%)
MIN_ROWS = 60


def validate_prices(df: pd.DataFrame, today=None) -> dict:
    today = pd.Timestamp(today or now().date())
    issues, notes = [], []
    n = len(df)
    if n < 2:
        return {"status": "ditolak", "ditolak": ["data kurang dari 2 baris"], "catatan": [], "baris": n}
    if n < MIN_ROWS:
        notes.append(f"hanya {n} baris (< {MIN_ROWS}): indikator jangka panjang (SMA200, dsb.) tidak dapat dihitung")
    last = df.index.max()
    age = (today - last).days
    if age > STALE_DAYS:
        notes.append(f"data terakhir {last.date()} ({age} hari lalu): TIDAK SEGAR; jangan dipakai untuk keputusan hari ini sebelum diperbarui")
    if (df["close"] <= 0).any():
        issues.append("ada harga penutupan <= 0")
    full = df.dropna(subset=["open", "high", "low"])
    if len(full):
        bad = full[(full["high"] < full[["open", "close", "low"]].max(axis=1)) | (full["low"] > full[["open", "close", "high"]].min(axis=1))]
        if len(bad):
            frac = len(bad) / len(full)
            (issues if frac > 0.02 else notes).append(f"{len(bad)} baris OHLC tidak konsisten (high < open/close/low atau low > ...), contoh {bad.index[0].date()}")
    gaps = df.index.to_series().diff().dt.days.dropna()
    big = gaps[gaps > GAP_DAYS]
    if len(big):
        notes.append(f"{len(big)} bolong tanggal > {GAP_DAYS} hari (mis. {big.index[0].date()}, {int(big.iloc[0])} hari): data mungkin tidak lengkap/saham disuspensi")
    ret = df["close"].pct_change().dropna()
    jumps = ret[ret.abs() > JUMP]
    if len(jumps):
        ex = ", ".join(f"{d.date()} ({r:+.0%})" for d, r in jumps.head(3).items())
        notes.append(f"{len(jumps)} lonjakan harian > {JUMP:.0%}: {ex}. Bisa aksi korporasi (pemecahan saham/dividen/rights) yang belum disesuaikan atau salah data; "
                     "indikator terdampak, periksa dulu")
    if df["volume"].notna().any():
        zero = float((df["volume"].fillna(0) == 0).mean())
        if zero > 0.2:
            notes.append(f"{zero:.0%} hari bervolume nol: likuiditas rendah atau data volume tidak lengkap")
    elif len(df):
        notes.append("kolom volume tidak ada: analisis volume/likuiditas tidak tersedia")
    if df.index.duplicated().any():
        issues.append("tanggal ganda")
    status = "ditolak" if issues else ("lolos_dengan_catatan" if notes else "lolos")
    return {"status": status, "ditolak": issues, "catatan": notes, "baris": n, "terakhir": str(last.date()), "umur_hari": int(age)}


def render(kode: str, v: dict) -> str:
    head = {"lolos": "LOLOS", "lolos_dengan_catatan": "LOLOS DENGAN CATATAN", "ditolak": "DITOLAK"}[v["status"]]
    lines = [f"Validasi data {kode}: {head} ({v['baris']} baris, terakhir {v.get('terakhir', '-')})"]
    lines += [f"- DITOLAK: {x}" for x in v["ditolak"]] + [f"- catatan: {x}" for x in v["catatan"]]
    return "\n".join(lines)
