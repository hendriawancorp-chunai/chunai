"""Indikator teknikal dan rencana trading. Semua dihitung dari data tersimpan; tidak ada angka karangan."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

LOT = 100                      # 1 lot IDX = 100 lembar
FEE_BELI, FEE_JUAL = 0.0015, 0.0025   # estimasi biaya (beli 0.15%, jual 0.25% termasuk pajak); sesuaikan dengan broker


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def _wilder(values: np.ndarray, n: int) -> np.ndarray:
    """Rata-rata Wilder dengan benih SMA(n) (seperti TA-Lib): out[n-1] = mean(values[:n]) lalu out[i] = (out[i-1]*(n-1)+v)/n."""
    out = np.full(len(values), np.nan)
    if len(values) < n:
        return out
    out[n - 1] = values[:n].mean()
    for i in range(n, len(values)):
        out[i] = (out[i - 1] * (n - 1) + values[i]) / n
    return out


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff().to_numpy()
    gain, loss = np.where(d > 0, d, 0.0), np.where(d < 0, -d, 0.0)
    ag = np.full(len(d), np.nan)
    al = np.full(len(d), np.nan)
    if len(d) > n:
        ag[1:], al[1:] = _wilder(gain[1:], n), _wilder(loss[1:], n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = ag / al
        out = np.where(al == 0, 100.0, 100 - 100 / (1 + rs))
    out = np.where(np.isnan(ag), np.nan, out)
    return pd.Series(out, index=close.index)


def atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    pc = df["close"].shift(1)
    tr = pd.concat([df["high"] - df["low"], (df["high"] - pc).abs(), (df["low"] - pc).abs()], axis=1).max(axis=1).to_numpy()
    out = np.full(len(tr), np.nan)
    if len(tr) > n:
        out[1:] = _wilder(tr[1:], n)
    return pd.Series(out, index=df.index)


def macd(close: pd.Series, fast: int = 12, slow: int = 26, sig: int = 9):
    line = ema(close, fast) - ema(close, slow)
    signal = line.ewm(span=sig, adjust=False, min_periods=sig).mean()
    return line, signal, line - signal


def tick_size(price: float) -> int:
    """Fraksi harga IDX."""
    return 1 if price < 200 else 2 if price < 500 else 5 if price < 2000 else 10 if price < 5000 else 25


def round_tick(price: float, mode: str = "nearest") -> float:
    t = tick_size(price)
    q = price / t
    return float((math.floor(q) if mode == "down" else math.ceil(q) if mode == "up" else round(q)) * t)


def swing_levels(df: pd.DataFrame, window: int = 5, tol: float = 0.015) -> tuple[list[dict], list[dict]]:
    """Level support/resistance dari pivot swing (high/low lokal), dikelompokkan dalam toleransi tol."""
    hi, lo = (df["high"], df["low"]) if df[["high", "low"]].notna().all().all() else (df["close"], df["close"])
    piv_hi = [(i, hi.iloc[i]) for i in range(window, len(df) - window) if hi.iloc[i] == hi.iloc[i - window:i + window + 1].max()]
    piv_lo = [(i, lo.iloc[i]) for i in range(window, len(df) - window) if lo.iloc[i] == lo.iloc[i - window:i + window + 1].min()]

    def cluster(pts):
        out: list[dict] = []
        for _, p in sorted(pts, key=lambda x: x[1]):
            if out and abs(p - out[-1]["harga"]) / out[-1]["harga"] <= tol:
                c = out[-1]
                c["harga"] = (c["harga"] * c["sentuhan"] + p) / (c["sentuhan"] + 1)
                c["sentuhan"] += 1
            else:
                out.append({"harga": float(p), "sentuhan": 1})
        return out
    last = df["close"].iloc[-1]
    sup = sorted([c for c in cluster(piv_lo) if c["harga"] < last], key=lambda c: -c["harga"])
    res = sorted([c for c in cluster(piv_hi) if c["harga"] > last], key=lambda c: c["harga"])
    return sup, res


def analyze(df: pd.DataFrame, bench: pd.Series | None = None) -> dict:
    c = df["close"]
    n = len(df)
    last = float(c.iloc[-1])
    out: dict = {"tanggal": str(df.index[-1].date()), "harga": last, "baris": n}
    for k in (20, 50, 200):
        v = sma(c, k).iloc[-1]
        out[f"sma{k}"] = None if pd.isna(v) else float(v)
    r = rsi(c).iloc[-1]
    out["rsi14"] = None if pd.isna(r) else float(r)
    m, s, h = macd(c)
    out["macd"] = None if pd.isna(m.iloc[-1]) else {"macd": float(m.iloc[-1]), "sinyal": float(s.iloc[-1]) if not pd.isna(s.iloc[-1]) else None,
                                                    "histogram": float(h.iloc[-1]) if not pd.isna(h.iloc[-1]) else None}
    bb_m, bb_s = sma(c, 20), c.rolling(20, min_periods=20).std(ddof=0)
    if not pd.isna(bb_m.iloc[-1]):
        out["bollinger"] = {"tengah": float(bb_m.iloc[-1]), "atas": float(bb_m.iloc[-1] + 2 * bb_s.iloc[-1]), "bawah": float(bb_m.iloc[-1] - 2 * bb_s.iloc[-1])}
    if df[["high", "low"]].notna().all().all():
        a = atr(df).iloc[-1]
        out["atr14"] = None if pd.isna(a) else float(a)
        out["atr_persen"] = None if pd.isna(a) else float(a / last * 100)
    for label, d in (("1b", 21), ("3b", 63), ("6b", 126), ("12b", 252)):
        if n > d:
            out[f"return_{label}"] = float(c.iloc[-1] / c.iloc[-1 - d] - 1)
    yr = c.iloc[-252:]
    out["tertinggi_52m"], out["terendah_52m"] = float(yr.max()), float(yr.min())
    out["jarak_dari_tertinggi_52m"] = float(last / yr.max() - 1)
    dd = (yr / yr.cummax() - 1).min()
    out["max_drawdown_1t"] = float(dd)
    rets = c.pct_change().dropna().iloc[-252:]
    out["volatilitas_tahunan"] = float(rets.std() * math.sqrt(252)) if len(rets) > 20 else None
    if df["volume"].notna().any():
        v20 = df["volume"].iloc[-20:]
        out["rata_volume_20"] = float(v20.mean())
        out["rata_nilai_transaksi_20"] = float((df["volume"].iloc[-20:] * c.iloc[-20:]).mean())
        out["rasio_volume"] = float(df["volume"].iloc[-1] / v20.mean()) if v20.mean() else None
    # tren
    s50, s200 = out["sma50"], out["sma200"]
    if s50 and s200:
        slope = float(sma(c, 50).iloc[-1] / sma(c, 50).iloc[-11] - 1) if n > 60 else 0.0
        if last > s50 > s200 and slope > 0:
            out["tren"] = "naik (harga > SMA50 > SMA200, SMA50 menanjak)"
        elif last < s50 < s200 and slope < 0:
            out["tren"] = "turun (harga < SMA50 < SMA200, SMA50 menurun)"
        else:
            out["tren"] = "campuran/sideways (susunan harga dan rata-rata tidak searah)"
    elif s50:
        out["tren"] = "naik jangka menengah (harga > SMA50)" if last > s50 else "turun jangka menengah (harga < SMA50)"
    else:
        out["tren"] = "belum dapat ditentukan (data < 50 baris)"
    sup, res = swing_levels(df) if n > 30 else ([], [])
    out["support"], out["resistance"] = sup[:3], res[:3]
    if bench is not None and len(bench):
        b = bench.reindex(c.index).ffill().dropna()
        if len(b) > 63 and len(c) > 63:
            out["return_3b_relatif_indeks"] = float((c.iloc[-1] / c.iloc[-64] - 1) - (b.iloc[-1] / b.iloc[-64] - 1))
    return out


def render(kode: str, a: dict) -> str:
    def pct(x): return "n/a" if x is None else f"{x:+.1%}"
    def rp(x): return "n/a" if x is None else f"{x:,.0f}".replace(",", ".")
    lines = [f"ANALISIS TEKNIKAL {kode} (data s.d. {a['tanggal']}, {a['baris']} baris)", f"Harga terakhir: {rp(a['harga'])}",
             f"Tren: {a['tren']}",
             f"SMA20/50/200: {rp(a['sma20'])} / {rp(a['sma50'])} / {rp(a['sma200'])}",
             f"RSI14: {'n/a' if a['rsi14'] is None else f'{a['rsi14']:.1f}'}" + (" (jenuh beli >70)" if a['rsi14'] and a['rsi14'] > 70 else " (jenuh jual <30)" if a['rsi14'] and a['rsi14'] < 30 else "")]
    if a.get("macd"):
        mm = a["macd"]
        lines.append(f"MACD: {mm['macd']:.2f}, sinyal {mm['sinyal']:.2f}, histogram {mm['histogram']:.2f}" if mm.get("sinyal") is not None else f"MACD: {mm['macd']:.2f}")
    if a.get("bollinger"):
        b = a["bollinger"]
        lines.append(f"Bollinger(20,2): bawah {rp(b['bawah'])} / tengah {rp(b['tengah'])} / atas {rp(b['atas'])}")
    if a.get("atr14") is not None:
        lines.append(f"ATR14: {a['atr14']:.1f} ({a['atr_persen']:.1f}% dari harga)")
    lines.append("Kinerja: " + ", ".join(f"{k.split('_')[1]} {pct(a[k])}" for k in ("return_1b", "return_3b", "return_6b", "return_12b") if k in a))
    if "return_3b_relatif_indeks" in a:
        lines.append(f"3 bulan relatif terhadap indeks pembanding: {pct(a['return_3b_relatif_indeks'])}")
    lines.append(f"52 minggu: {rp(a['terendah_52m'])} - {rp(a['tertinggi_52m'])} (jarak dari tertinggi {pct(a['jarak_dari_tertinggi_52m'])}); drawdown maks 1 tahun {pct(a['max_drawdown_1t'])}")
    if a.get("volatilitas_tahunan") is not None:
        lines.append(f"Volatilitas tahunan: {a['volatilitas_tahunan']:.0%}")
    if a.get("rata_nilai_transaksi_20") is not None:
        lines.append(f"Likuiditas: rata-rata nilai transaksi 20 hari ≈ Rp{a['rata_nilai_transaksi_20'] / 1e6:,.0f} juta/hari; volume hari ini {a['rasio_volume']:.1f}x rata-rata" if a.get('rasio_volume') else
                     f"Likuiditas: rata-rata nilai transaksi 20 hari ≈ Rp{a['rata_nilai_transaksi_20'] / 1e6:,.0f} juta/hari")
    if a["support"]:
        lines.append("Support terdekat: " + ", ".join(f"{rp(x['harga'])} ({x['sentuhan']}x)" for x in a["support"]))
    if a["resistance"]:
        lines.append("Resistance terdekat: " + ", ".join(f"{rp(x['harga'])} ({x['sentuhan']}x)" for x in a["resistance"]))
    lines.append("Catatan: indikator adalah gambaran kondisi harga, bukan ramalan.")
    return "\n".join(lines)


def trading_plan(df: pd.DataFrame, modal: float, risiko_persen: float, entry: float | None = None, stop: float | None = None,
                 atr_mult: float = 2.0, fee_beli: float = FEE_BELI, fee_jual: float = FEE_JUAL) -> dict:
    """Rencana posisi long: ukuran posisi dari batas risiko per transaksi. Entry/stop dibulatkan ke fraksi harga IDX."""
    if modal <= 0 or not 0 < risiko_persen <= 5:
        raise ValueError("modal harus > 0 dan risiko_persen antara 0 dan 5 (praktik umum 0,5-2% per transaksi).")
    last = float(df["close"].iloc[-1])
    entry = round_tick(entry or last, "nearest")
    notes = []
    if stop is None:
        a = atr(df).iloc[-1] if df[["high", "low"]].notna().all().all() else float("nan")
        if pd.isna(a):
            raise ValueError("ATR tidak tersedia (butuh high/low >= 15 baris). Berikan 'stop' manual.")
        stop = round_tick(entry - atr_mult * float(a), "down")
        notes.append(f"stop = entry - {atr_mult}xATR14 ({float(a):.1f}); bandingkan dengan support terdekat sebelum dipakai")
    else:
        stop = round_tick(stop, "down")
    if stop >= entry:
        raise ValueError("stop harus di bawah entry untuk posisi beli.")
    risk_per_share = entry - stop
    budget = modal * risiko_persen / 100
    shares_by_risk = math.floor(budget / risk_per_share)
    max_by_cash = math.floor(modal / (entry * (1 + fee_beli)))
    shares = min(shares_by_risk, max_by_cash)
    lots = shares // LOT
    shares = lots * LOT
    if lots < 1:
        notes.append("modal/batas risiko terlalu kecil untuk 1 lot pada stop sejauh ini; perlebar batas risiko atau pilih stop lebih dekat")
    if shares_by_risk > max_by_cash:
        notes.append("ukuran posisi dibatasi oleh modal tunai, bukan oleh batas risiko")
    cost = shares * entry * (1 + fee_beli)
    loss_at_stop = shares * (entry - stop) + shares * entry * fee_beli + shares * stop * fee_jual
    targets = []
    for r in (1.0, 2.0, 3.0):
        tgt = round_tick(entry + r * risk_per_share, "nearest")
        gross = shares * (tgt - entry)
        net = gross - shares * entry * fee_beli - shares * tgt * fee_jual
        targets.append({"R": r, "target": tgt, "laba_bersih": float(net), "rr_bersih": float(net / loss_at_stop) if loss_at_stop else None})
    plan = {"entry": entry, "stop": stop, "risiko_per_lembar": risk_per_share, "lot": int(lots), "lembar": int(shares), "nilai_beli": float(cost),
            "persen_modal": float(cost / modal) if modal else None, "rugi_di_stop": float(loss_at_stop),
            "rugi_di_stop_persen_modal": float(loss_at_stop / modal), "target": targets, "catatan": notes}
    if df["volume"].notna().any():
        adv = float((df["volume"].iloc[-20:] * df["close"].iloc[-20:]).mean())
        plan["nilai_transaksi_harian"] = adv
        if adv > 0 and cost / adv > 0.01:
            notes.append(f"posisi {cost / adv:.1%} dari nilai transaksi harian: berisiko sulit keluar cepat (likuiditas)")
        if adv < 1e9:
            notes.append("likuiditas rendah (nilai transaksi harian < Rp1 miliar)")
    return plan


def render_plan(kode: str, p: dict, modal: float, risiko_persen: float) -> str:
    def rp(x): return f"{x:,.0f}".replace(",", ".")
    lines = [f"RENCANA TRADING {kode} (posisi beli; modal Rp{rp(modal)}, batas risiko {risiko_persen}%/transaksi)",
             f"Entry {rp(p['entry'])} | Stop {rp(p['stop'])} (risiko {rp(p['risiko_per_lembar'])}/lembar)",
             f"Ukuran: {p['lot']} lot ({rp(p['lembar'])} lembar), nilai beli ≈ Rp{rp(p['nilai_beli'])} ({p['persen_modal']:.1%} modal)",
             f"Rugi bila stop kena (termasuk estimasi biaya): Rp{rp(p['rugi_di_stop'])} ({p['rugi_di_stop_persen_modal']:.2%} modal)"]
    for t in p["target"]:
        lines.append(f"Target {t['R']:.0f}R: {rp(t['target'])} -> laba bersih ≈ Rp{rp(t['laba_bersih'])} (rasio risiko-imbalan bersih {t['rr_bersih']:.2f})")
    lines += [f"Catatan: {n}" for n in p["catatan"]]
    lines.append("Biaya diasumsikan beli 0,15% dan jual 0,25% (sesuaikan broker). Ini simulasi perhitungan, bukan perintah/rekomendasi transaksi; pasar dapat gap melewati stop.")
    return "\n".join(lines)
