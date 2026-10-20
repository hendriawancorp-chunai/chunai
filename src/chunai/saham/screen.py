"""Penyaringan dan skor saham yang transparan (faktor kualitas, valuasi, momentum, risiko) dari data tersimpan. Alat penyaring, bukan rekomendasi."""
from __future__ import annotations

from . import fundamental as F
from . import store, teknikal, validasi


def interp(x: float | None, pts: list[tuple[float, float]]) -> float | None:
    """Skor 0-100 linear per bagian dari titik (nilai, skor) yang naik menurut nilai."""
    if x is None:
        return None
    pts = sorted(pts)
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    return None


def _mean(vals):
    v = [x for x in vals if x is not None]
    return sum(v) / len(v) if v else None


def metrics(kode: str) -> dict | None:
    df = store.load_prices(kode)
    v = validasi.validate_prices(df)
    if v["status"] == "ditolak":
        return None
    a = teknikal.analyze(df)
    m = {"kode": kode, "tanggal": a["tanggal"], "harga": a["harga"], "r3": a.get("return_3b"), "r6": a.get("return_6b"), "r12": a.get("return_12b"), "vol": a.get("volatilitas_tahunan"),
         "mdd": a.get("max_drawdown_1t"), "rsi": a.get("rsi14"), "tren": a["tren"], "liq": a.get("rata_nilai_transaksi_20"), "catatan_data": v["catatan"]}
    if F.load(kode):
        try:
            fa = F.analyze(kode, a["harga"], a["tanggal"])
            fy = fa["tahunan"][-1] if fa["tahunan"] else {}
            m.update({"per": fa.get("per"), "pbv": fa.get("pbv"), "dy": fa.get("dividen_yield"), "roe": fy.get("roe"), "der": fy.get("der"), "mb": fy.get("margin_bersih"),
                      "cfo_ni": fy.get("cfo_per_laba"), "fcf_y": fa.get("fcf_yield"), "periode_f": fa["periode_terbaru"], "g_laba": fy.get("laba_bersih_yoy"), "rekon": fa["rekonsiliasi"]})
        except Exception:
            pass
    return m


def factor_scores(m: dict, pref_dividen: bool = False) -> dict:
    k = _mean([interp(m.get("roe"), [(0, 5), (0.05, 40), (0.10, 70), (0.15, 100)]), interp(m.get("mb"), [(0, 5), (0.05, 40), (0.10, 70), (0.20, 100)]),
               interp(None if m.get("der") is None else -m["der"], [(-4, 0), (-3, 20), (-2, 60), (-1, 100)]), interp(m.get("cfo_ni"), [(0, 0), (0.5, 20), (0.7, 60), (1.0, 100)])])
    per_s = 0 if (m.get("per") is None and m.get("pbv") is not None and m.get("roe") is not None and m["roe"] <= 0) else interp(None if m.get("per") is None else -m["per"], [(-35, 0), (-25, 25), (-18, 50), (-12, 75), (-8, 100)])
    dy_s = interp(m.get("dy"), [(0, 10), (0.02, 40), (0.04, 70), (0.06, 100)])
    val_parts = [per_s, interp(None if m.get("pbv") is None else -m["pbv"], [(-4, 10), (-2.5, 40), (-1.5, 70), (-1, 100)]), dy_s]
    if pref_dividen and dy_s is not None:
        val_parts.append(dy_s)                                      # preferensi dividen: bobot yield dilipatgandakan dalam faktor valuasi
    v = _mean(val_parts)
    mom = _mean([interp(m.get("r6"), [(-0.2, 0), (-0.1, 20), (0.0, 45), (0.1, 75), (0.2, 100)]), interp(m.get("r12"), [(-0.3, 0), (-0.1, 25), (0.0, 45), (0.15, 75), (0.3, 100)]),
                 100.0 if str(m.get("tren", "")).startswith("naik") else 20.0 if str(m.get("tren", "")).startswith("turun") else 50.0])
    if mom is not None and m.get("rsi") is not None and m["rsi"] > 75:
        mom = max(0.0, mom - 15)                                    # jenuh beli: kurangi skor momentum
    risk = _mean([interp(None if m.get("vol") is None else -m["vol"], [(-0.7, 10), (-0.5, 40), (-0.35, 70), (-0.25, 100)]), interp(m.get("mdd"), [(-0.6, 0), (-0.4, 30), (-0.25, 70), (-0.15, 100)]),
                  interp(m.get("liq"), [(0.5e9, 0), (1e9, 40), (3e9, 70), (10e9, 100)])])
    return {"kualitas": k, "valuasi": v, "momentum": mom, "risiko": risk}


def weights(horizon: str, toleransi: str) -> dict:
    w = {"panjang": {"kualitas": .35, "valuasi": .30, "momentum": .10, "risiko": .25}, "menengah": {"kualitas": .25, "valuasi": .25, "momentum": .25, "risiko": .25},
         "pendek": {"kualitas": .05, "valuasi": .05, "momentum": .55, "risiko": .35}}[horizon if horizon in ("panjang", "menengah", "pendek") else "menengah"].copy()
    w["risiko"] += {"konservatif": .10, "agresif": -.05}.get(toleransi, 0)
    s = sum(w.values())
    return {k: v / s for k, v in w.items()}


def screen(codes: list[str], horizon: str = "menengah", toleransi: str = "moderat", pref_dividen: bool = False, filt: dict | None = None) -> dict:
    filt = filt or {}
    w = weights(horizon, toleransi)
    rows, excluded = [], []
    for k in codes:
        try:
            m = metrics(k)
        except Exception as e:
            excluded.append(f"{k}: {type(e).__name__}")
            continue
        if m is None:
            excluded.append(f"{k}: data ditolak validasi")
            continue
        why = []
        checks = [("liq", "min_nilai_transaksi", lambda a, b: a >= b), ("per", "per_maks", lambda a, b: 0 < a <= b), ("pbv", "pbv_maks", lambda a, b: a <= b), ("roe", "roe_min", lambda a, b: a >= b),
                  ("der", "der_maks", lambda a, b: a <= b), ("dy", "dividen_yield_min", lambda a, b: a >= b), ("rsi", "rsi_maks", lambda a, b: a <= b), ("rsi", "rsi_min", lambda a, b: a >= b), ("r3", "return_3b_min", lambda a, b: a >= b)]
        for key, fk, fn in checks:
            if fk in filt and filt[fk] is not None:
                if m.get(key) is None:
                    why.append(f"{fk}: data tidak ada")
                elif not fn(m[key], float(filt[fk])):
                    why.append(f"{fk} tidak terpenuhi ({m[key]:.3g} vs {filt[fk]})")
        if filt.get("tren_naik") and not str(m["tren"]).startswith("naik"):
            why.append("tren bukan naik")
        if why:
            excluded.append(f"{k}: " + "; ".join(why))
            continue
        fs = factor_scores(m, pref_dividen)
        avail = {f: s for f, s in fs.items() if s is not None}
        tw = sum(w[f] for f in avail)
        total = sum(s * w[f] for f, s in avail.items()) / tw if tw else None
        rows.append({**m, "faktor": fs, "skor": total, "kelengkapan": f"{len(avail)}/4 faktor"})
    rows.sort(key=lambda r: -(r["skor"] if r["skor"] is not None else -1))
    return {"bobot": w, "baris": rows, "dikeluarkan": excluded}


def render(res: dict, horizon: str, toleransi: str) -> str:
    w = res["bobot"]
    lines = [f"PENYARINGAN (horizon {horizon}, toleransi {toleransi}); bobot faktor: " + ", ".join(f"{k} {v:.0%}" for k, v in w.items()),
             "| Peringkat | Kode | Skor | Kualitas | Valuasi | Momentum | Risiko | Kelengkapan | Tgl data | Catatan |", "|---|---|---|---|---|---|---|---|---|---|"]
    f = lambda x: "n/a" if x is None else f"{x:.0f}"
    for i, r in enumerate(res["baris"], 1):
        note = []
        if r["kelengkapan"] != "4/4 faktor":
            note.append("data tidak lengkap")
        if r.get("catatan_data"):
            note.append("catatan data")
        if r.get("rekon"):
            note.append("rekonsiliasi janggal")
        fa = r["faktor"]
        lines.append(f"| {i} | {r['kode']} | {f(r['skor'])} | {f(fa['kualitas'])} | {f(fa['valuasi'])} | {f(fa['momentum'])} | {f(fa['risiko'])} | {r['kelengkapan']} | {r['tanggal']} | {', '.join(note) or '-'} |")
    if res["dikeluarkan"]:
        lines.append("Dikeluarkan: " + "; ".join(res["dikeluarkan"]))
    dates = {r["tanggal"] for r in res["baris"]}
    if len(dates) > 1:
        lines.append(f"⚠ Tanggal data berbeda ({', '.join(sorted(dates))}): perbarui agar sejajar.")
    lines.append("Skor 0-100 berbasis ambang tetap (bukan peringkat relatif); faktor tanpa data tidak dihitung dan bobotnya dinormalkan ulang. Ini PENYARING kandidat untuk ditelaah, bukan rekomendasi beli/jual; "
                 "periksa tiap kandidat dengan analisis teknikal, fundamental, valuasi, dan berita.")
    return "\n".join(lines)
