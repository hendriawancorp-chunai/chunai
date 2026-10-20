"""Rekam jejak rekomendasi dan watchlist. Rekomendasi dicatat saat dikeluarkan lalu dievaluasi terhadap harga yang tersimpan sesudahnya."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..timeutil import now
from . import store, teknikal, validasi
from .store import SahamError, root

AKSI = ("beli", "beli_bertahap", "tahan", "kurangi", "jual", "pantau", "hindari")
BULLISH = {"beli", "beli_bertahap", "tahan"}
BEARISH = {"kurangi", "jual", "hindari"}
KEYAKINAN = ("tinggi", "sedang", "rendah")


def rec_path() -> Path:
    return root() / "rekomendasi.jsonl"


def wl_path() -> Path:
    return root() / "watchlist.json"


def catat(kode: str, aksi: str, tesis: str, keyakinan: str, harga_ref: float | None = None, tanggal_ref: str | None = None, pembatalan: float | None = None,
          target: float | None = None, horizon: str = "") -> dict:
    kode, aksi, keyakinan = store.norm_kode(kode), str(aksi).strip().lower(), str(keyakinan).strip().lower()
    if aksi not in AKSI:
        raise SahamError(f"aksi harus salah satu dari {', '.join(AKSI)}.")
    if keyakinan not in KEYAKINAN:
        raise SahamError(f"keyakinan harus salah satu dari {', '.join(KEYAKINAN)}.")
    if not str(tesis).strip():
        raise SahamError("tesis (alasan singkat) wajib.")
    if harga_ref is None:
        df = store.load_prices(kode)
        harga_ref, tanggal_ref = float(df["close"].iloc[-1]), str(df.index[-1].date())
    if aksi in BULLISH and pembatalan is not None and pembatalan >= harga_ref:
        raise SahamError("pembatalan untuk posisi beli harus di bawah harga referensi.")
    if aksi in BULLISH and target is not None and target <= harga_ref:
        raise SahamError("target untuk posisi beli harus di atas harga referensi.")
    rec = {"id": f"{kode}-{now():%Y%m%d%H%M%S}", "kode": kode, "aksi": aksi, "tesis": str(tesis)[:500], "keyakinan": keyakinan, "harga_ref": harga_ref, "tanggal_ref": tanggal_ref,
           "pembatalan": pembatalan, "target": target, "horizon": str(horizon)[:40], "dicatat": now().isoformat(timespec="seconds")}
    p = rec_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def load_recs() -> list[dict]:
    p = rec_path()
    if not p.is_file():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def evaluate(rec: dict, bench: pd.Series | None = None) -> dict:
    df = store.load_prices(rec["kode"])
    after = df[df.index > pd.Timestamp(rec["tanggal_ref"])]
    if after.empty:
        return {"id": rec["id"], "status": "belum ada data setelah tanggal referensi"}
    p0, last = rec["harga_ref"], float(after["close"].iloc[-1])
    ret = last / p0 - 1
    hi = after["high"].where(after["high"].notna(), after["close"])
    lo = after["low"].where(after["low"].notna(), after["close"])
    out = {"id": rec["id"], "kode": rec["kode"], "aksi": rec["aksi"], "keyakinan": rec["keyakinan"], "return": ret, "hari": int(len(after)), "tanggal_akhir": str(after.index[-1].date()),
           "mfe": float(hi.max() / p0 - 1), "mae": float(lo.min() / p0 - 1)}
    status = "berjalan"
    cancel, target = rec.get("pembatalan"), rec.get("target")
    if rec["aksi"] in BULLISH:
        first = lambda mask: (after.index[mask][0] if mask.any() else None)
        t_hit = first(hi >= target) if target else None
        c_hit = first(lo <= cancel) if cancel else None
        if t_hit is not None and (c_hit is None or t_hit <= c_hit):
            status = f"target tercapai ({t_hit.date()})"
        elif c_hit is not None:
            status = f"pembatalan terkena ({c_hit.date()})"
    if bench is not None and len(bench):
        b = bench[bench.index >= pd.Timestamp(rec["tanggal_ref"])]
        if len(b) > 1:
            out["return_indeks"] = float(b.iloc[-1] / b.iloc[0] - 1)
            out["relatif"] = ret - out["return_indeks"]
    out["status"] = status
    sign = -1 if rec["aksi"] in BEARISH else 1
    out["benar"] = (sign * (out["relatif"] if "relatif" in out else ret)) > 0 if rec["aksi"] != "pantau" else None
    return out


def summarize(evals: list[dict]) -> str:
    good = [e for e in evals if "return" in e]
    if not good:
        return "Belum ada rekomendasi yang dapat dievaluasi (butuh data harga setelah tanggal referensi)."
    lines = ["| ID | Aksi | Keyakinan | Return | vs indeks | Hari | Status |", "|---|---|---|---|---|---|---|"]
    for e in good:
        lines.append(f"| {e['id']} | {e['aksi']} | {e['keyakinan']} | {e['return']:+.1%} | {('%+.1f%%' % (e['relatif'] * 100)) if 'relatif' in e else 'n/a'} | {e['hari']} | {e['status']} |")
    judged = [e for e in good if e["benar"] is not None]
    if judged:
        lines.append(f"\nKetepatan arah (menurut aksi; relatif indeks bila ada): {sum(e['benar'] for e in judged)}/{len(judged)}")
        for kel in KEYAKINAN:
            sub = [e for e in judged if e["keyakinan"] == kel]
            if sub:
                lines.append(f"- keyakinan {kel}: {sum(e['benar'] for e in sub)}/{len(sub)} tepat")
    n = len(judged)
    lines.append(f"Catatan: sampel {n} rekomendasi" + (" (< 20: BELUM bermakna secara statistik, jangan menyimpulkan kemampuan)." if n < 20 else ".") +
                 " Hasil masa lalu tidak menjamin hasil ke depan; evaluasi memakai data harga yang tersimpan.")
    return "\n".join(lines)


# ---------- watchlist ----------
def load_wl() -> dict:
    try:
        d = json.loads(wl_path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_wl(d: dict) -> None:
    p = wl_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def check_watchlist() -> str:
    wl = load_wl()
    if not wl:
        return "(watchlist kosong)"
    lines = []
    for kode, item in sorted(wl.items()):
        try:
            df = store.load_prices(kode)
        except SahamError:
            lines.append(f"- {kode}: belum ada data harga tersimpan")
            continue
        v = validasi.validate_prices(df)
        a = teknikal.analyze(df)
        last = a["harga"]
        flags = []
        if v["status"] == "ditolak":
            lines.append(f"- {kode}: data DITOLAK validasi, tidak dianalisis")
            continue
        if v["umur_hari"] > validasi.STALE_DAYS:
            flags.append(f"DATA TIDAK SEGAR ({v['terakhir']}, {v['umur_hari']} hari lalu: perbarui)")
        if item.get("alert_atas") and last >= item["alert_atas"]:
            flags.append(f"MENEMBUS atas {item['alert_atas']:,.0f}")
        if item.get("alert_bawah") and last <= item["alert_bawah"]:
            flags.append(f"MENEMBUS bawah {item['alert_bawah']:,.0f}")
        if a.get("rsi14") is not None and (a["rsi14"] > 70 or a["rsi14"] < 30):
            flags.append(f"RSI {a['rsi14']:.0f} ({'jenuh beli' if a['rsi14'] > 70 else 'jenuh jual'})")
        if a.get("rasio_volume") and a["rasio_volume"] >= 2:
            flags.append(f"volume {a['rasio_volume']:.1f}x rata-rata")
        d1 = df["close"].iloc[-1] / df["close"].iloc[-2] - 1 if len(df) > 1 else 0
        d5 = df["close"].iloc[-1] / df["close"].iloc[-6] - 1 if len(df) > 5 else None
        lines.append(f"- {kode}: {last:,.0f} ({a['tanggal']}), 1h {d1:+.1%}" + (f", 5h {d5:+.1%}" if d5 is not None else "") + f", tren {a['tren'].split(' (')[0]}" +
                     (f" | {'; '.join(flags)}" if flags else " | tidak ada peringatan") + (f" | catatan: {item['catatan']}" if item.get("catatan") else ""))
    return "WATCHLIST (dari data tersimpan; tidak mengambil data baru):\n" + "\n".join(lines).replace(",", ".") if False else "WATCHLIST (dari data tersimpan; tidak mengambil data baru):\n" + "\n".join(lines)
