"""Data fundamental per periode (dengan jejak sumber+halaman), analisis rasio, dan valuasi (DCF/DDM/relatif dengan sensitivitas).
Semua nilai disimpan dalam Rupiah penuh (lembar untuk saham). Periode: 'YYYY-FY' | 'YYYY-9M' | 'YYYY-6M' | 'YYYY-3M' (kumulatif tahun berjalan, seperti laporan keuangan emiten IDX)."""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pandas as pd

from ..timeutil import now
from .store import SahamError, dir_of, norm_kode

PERIODE = re.compile(r"^(\d{4})-(FY|9M|6M|3M)$")
SATUAN = {"rupiah": 1, "ribu": 1e3, "juta": 1e6, "miliar": 1e9, "triliun": 1e12}
FLOW = {"pendapatan", "laba_kotor", "laba_usaha", "laba_bersih", "arus_kas_operasi", "capex", "beban_bunga", "ebitda", "dividen_per_saham"}
STOCK = {"total_aset", "total_liabilitas", "ekuitas", "utang_berbunga", "kas", "jumlah_saham"}
FIELDS = FLOW | STOCK
NON_RP = {"jumlah_saham": 1.0, "dividen_per_saham": 1.0}        # tidak dikalikan satuan (lembar; Rp per lembar)
ALIAS = {
    "pendapatan": {"pendapatan", "pendapatanusaha", "penjualan", "penjualanbersih", "pendapatanbersih", "pendapatanneto", "revenue", "sales", "totalrevenue"},
    "laba_kotor": {"labakotor", "grossprofit"},
    "laba_usaha": {"labausaha", "labaoperasi", "labaoperasional", "operatingincome", "operatingprofit"},
    "laba_bersih": {"lababersih", "labatahunberjalan", "labaperiodeberjalan", "lababersihperiodeberjalan", "netincome", "profitfortheyear",
                    "labayangdiatribusikankepadapemilikentitasinduk", "labadiatribusikankepadapemilikentitasinduk", "labayangdapatdiatribusikankepadapemilikentitasinduk"},
    "total_aset": {"totalaset", "jumlahaset", "totalassets"},
    "total_liabilitas": {"totalliabilitas", "jumlahliabilitas", "totalkewajiban", "jumlahkewajiban", "totalliabilities"},
    "ekuitas": {"ekuitas", "totalekuitas", "jumlahekuitas", "ekuitasyangdapatdiatribusikankepadapemilikentitasinduk", "totalequity", "shareholdersequity"},
    "utang_berbunga": {"utangberbunga", "pinjaman", "utangbank", "interestbearingdebt", "totaldebt"},
    "kas": {"kasdansetarakas", "kas", "cashandcashequivalents"},
    "arus_kas_operasi": {"aruskasdarioperasi", "aruskasbersihdarikegiatanoperasi", "kasbersihdiperolehdarikegiatanoperasi", "netcashfromoperatingactivities", "operatingcashflow"},
    "capex": {"capex", "pembelianasettetap", "perolehanasettetap", "capitalexpenditure"},
    "jumlah_saham": {"jumlahsaham", "sahamberedar", "lembarsaham", "sharesoutstanding"},
    "dividen_per_saham": {"dividenpersaham", "dps", "dividendpershare"},
    "beban_bunga": {"bebanbunga", "bebankeuangan", "interestexpense"},
    "ebitda": {"ebitda"},
}


def _key(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def alias_field(label: str) -> str | None:
    k = _key(label)
    for f, names in ALIAS.items():
        if k in names:
            return f
    return None


def path_of(kode: str) -> Path:
    return dir_of(kode) / "fundamental.json"


def load(kode: str) -> dict:
    try:
        return json.loads(path_of(kode).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def check_periode(p: str) -> str:
    p = str(p).strip().upper()
    if not PERIODE.match(p):
        raise SahamError("periode harus 'YYYY-FY', 'YYYY-9M', 'YYYY-6M', atau 'YYYY-3M' (kumulatif tahun berjalan).")
    return p


def set_fields(kode: str, periode: str, fields: dict[str, float], sumber: str, halaman: int | None = None, detail: dict | None = None) -> None:
    kode, periode = norm_kode(kode), check_periode(periode)
    d = load(kode)
    rec = d.setdefault(periode, {"nilai": {}, "jejak": {}})
    for f, v in fields.items():
        if f not in FIELDS:
            raise SahamError(f"butir '{f}' tidak dikenal. Dikenal: {', '.join(sorted(FIELDS))}")
        rec["nilai"][f] = float(v)
        rec["jejak"][f] = {"sumber": str(sumber)[:200], "halaman": halaman, "diambil": now().isoformat(timespec="seconds"), **(detail or {}).get(f, {})}
    p = path_of(kode)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def to_rupiah(field: str, nilai: float, satuan: str) -> float:
    if satuan not in SATUAN:
        raise SahamError(f"satuan harus salah satu dari {', '.join(SATUAN)}.")
    return float(nilai) * (NON_RP.get(field) or SATUAN[satuan])


# ---------- rekonsiliasi ----------
def reconcile(d: dict) -> list[str]:
    issues = []
    for p, rec in sorted(d.items()):
        v = rec["nilai"]
        if all(k in v for k in ("total_aset", "total_liabilitas", "ekuitas")):
            gap = v["total_aset"] - v["total_liabilitas"] - v["ekuitas"]
            if abs(gap) / v["total_aset"] > 0.12:                  # ekuitas induk tidak termasuk kepentingan nonpengendali: toleransi longgar
                issues.append(f"{p}: aset ≠ liabilitas + ekuitas (selisih {gap / v['total_aset']:+.1%} dari aset; bisa kepentingan nonpengendali atau salah ketik)")
        if "laba_bersih" in v and "pendapatan" in v and v["pendapatan"] and abs(v["laba_bersih"]) > abs(v["pendapatan"]):
            issues.append(f"{p}: |laba bersih| > pendapatan: periksa satuan/tanda")
        if "laba_kotor" in v and "pendapatan" in v and v["laba_kotor"] > v["pendapatan"]:
            issues.append(f"{p}: laba kotor > pendapatan")
        for f in ("total_aset", "ekuitas", "jumlah_saham"):
            if f in v and v[f] <= 0:
                issues.append(f"{p}: {f} <= 0")
    fy = sorted(p for p in d if p.endswith("FY"))
    for a, b in zip(fy, fy[1:]):
        for f in ("pendapatan", "total_aset"):
            if f in d[a]["nilai"] and f in d[b]["nilai"] and d[a]["nilai"][f] > 0 and not 0.2 < d[b]["nilai"][f] / d[a]["nilai"][f] < 5:
                issues.append(f"{a}→{b}: {f} berubah > 5x/<0,2x: periksa satuan (ribu/juta/miliar) antar periode")
    return issues


# ---------- analisis rasio ----------
def _val(d, p, f):
    return d.get(p, {}).get("nilai", {}).get(f)


def _ttm(d: dict, latest: str, f: str):
    y, kind = int(latest[:4]), latest[5:]
    if kind == "FY":
        return _val(d, latest, f)
    fy_prev, ytd_prev = _val(d, f"{y - 1}-FY", f), _val(d, f"{y - 1}-{kind}", f)
    ytd = _val(d, latest, f)
    if None in (fy_prev, ytd_prev, ytd):
        return None
    return fy_prev + ytd - ytd_prev


def latest_period(d: dict) -> str | None:
    order = {"3M": 1, "6M": 2, "9M": 3, "FY": 4}
    return max(d, key=lambda p: (int(p[:4]), order[p[5:]]), default=None)


def analyze(kode: str, harga: float | None = None, tanggal_harga: str | None = None) -> dict:
    d = load(kode)
    if not d:
        raise SahamError(f"Belum ada data fundamental {norm_kode(kode)}. Catat dari laporan keuangan (catat_fundamental) atau impor (impor_fundamental).")
    latest = latest_period(d)
    out: dict = {"periode_terbaru": latest, "periode": sorted(d), "rekonsiliasi": reconcile(d)}
    fy = sorted(p for p in d if p.endswith("FY"))
    rows = []
    for p in fy[-5:]:
        v = d[p]["nilai"]
        r = {"periode": p}
        for f in ("pendapatan", "laba_bersih", "arus_kas_operasi"):
            r[f] = v.get(f)
        if v.get("pendapatan"):
            for f, nm in (("laba_kotor", "margin_kotor"), ("laba_usaha", "margin_usaha"), ("laba_bersih", "margin_bersih")):
                if f in v:
                    r[nm] = v[f] / v["pendapatan"]
        if "total_liabilitas" in v and v.get("ekuitas"):
            r["der"] = v["total_liabilitas"] / v["ekuitas"]
        if "laba_bersih" in v and v.get("ekuitas"):
            prev = _val(d, f"{int(p[:4]) - 1}-FY", "ekuitas")
            avg = (v["ekuitas"] + prev) / 2 if prev else v["ekuitas"]
            r["roe"] = v["laba_bersih"] / avg
            r["roe_dasar"] = "rata-rata ekuitas awal-akhir" if prev else "ekuitas akhir"
        if "laba_bersih" in v and v.get("total_aset"):
            r["roa"] = v["laba_bersih"] / v["total_aset"]
        if "arus_kas_operasi" in v and "capex" in v:
            r["fcf"] = v["arus_kas_operasi"] - abs(v["capex"])
        if "arus_kas_operasi" in v and v.get("laba_bersih"):
            r["cfo_per_laba"] = v["arus_kas_operasi"] / v["laba_bersih"]
        rows.append(r)
    for a, b in zip(rows, rows[1:]):
        for f in ("pendapatan", "laba_bersih"):
            if a.get(f) and b.get(f) is not None and a[f] > 0:
                b[f"{f}_yoy"] = b[f] / a[f] - 1
    out["tahunan"] = rows
    ttm = {f: _ttm(d, latest, f) for f in ("pendapatan", "laba_bersih", "arus_kas_operasi", "capex", "dividen_per_saham")}
    out["ttm"] = {k: v for k, v in ttm.items() if v is not None}
    lv = d[latest]["nilai"]
    out["neraca_terbaru"] = {k: lv.get(k) for k in ("total_aset", "total_liabilitas", "ekuitas", "utang_berbunga", "kas", "jumlah_saham") if lv.get(k) is not None}
    if "utang_berbunga" in lv and "kas" in lv:
        out["utang_bersih"] = lv["utang_berbunga"] - lv["kas"]
    if "beban_bunga" in lv and lv.get("laba_usaha"):
        out["cakupan_bunga"] = lv["laba_usaha"] / lv["beban_bunga"] if lv["beban_bunga"] else None
    shares = lv.get("jumlah_saham") or _val(d, fy[-1], "jumlah_saham") if fy else lv.get("jumlah_saham")
    out["jumlah_saham"] = shares
    base_ni = ttm.get("laba_bersih")
    if shares and base_ni is not None:
        out["eps_ttm"] = base_ni / shares
    if shares and lv.get("ekuitas"):
        out["bvps"] = lv["ekuitas"] / shares
    dps = ttm.get("dividen_per_saham")
    if harga and shares:
        out["harga"], out["tanggal_harga"] = harga, tanggal_harga
        out["kapitalisasi"] = harga * shares
        if out.get("eps_ttm"):
            out["per"] = harga / out["eps_ttm"] if out["eps_ttm"] > 0 else None
            out["earnings_yield"] = out["eps_ttm"] / harga
        if out.get("bvps"):
            out["pbv"] = harga / out["bvps"]
        if dps is not None:
            out["dividen_yield"] = dps / harga
            if base_ni and base_ni > 0:
                out["payout"] = dps * shares / base_ni
        fcf = (ttm.get("arus_kas_operasi") - abs(ttm["capex"])) if ttm.get("arus_kas_operasi") is not None and ttm.get("capex") is not None else None
        if fcf is not None:
            out["fcf_ttm"], out["fcf_yield"] = fcf, fcf / (harga * shares)
    ttm_note = []
    if latest[5:] != "FY":
        ttm_note.append(f"TTM dihitung = FY{int(latest[:4]) - 1} + {latest[5:]} {latest[:4]} − {latest[5:]} {int(latest[:4]) - 1}" if all(f"{k}" in out["ttm"] for k in ("laba_bersih",)) else
                        f"periode terbaru {latest} (YTD) tanpa pembanding tahun lalu: TTM tidak dapat dihitung, memakai data FY")
    out["catatan"] = ttm_note
    age = (now().year - int(latest[:4])) * 12 + now().month - {"FY": 12, "9M": 9, "6M": 6, "3M": 3}[latest[5:]]
    if age > 15:
        out["catatan"].append(f"laporan terbaru ({latest}) sudah ±{age} bulan lalu: kemungkinan ada laporan yang lebih baru; perbarui")
    return out


def render(kode: str, a: dict) -> str:
    def rp(x, scale=1e9, unit="miliar"):
        return "n/a" if x is None else f"Rp{x / scale:,.1f} {unit}".replace(",", "X").replace(".", ",").replace("X", ".")
    def pc(x): return "n/a" if x is None else f"{x:.1%}"
    def nm(x, d=2): return "n/a" if x is None else f"{x:,.{d}f}"
    lines = [f"ANALISIS FUNDAMENTAL {kode} (periode terbaru {a['periode_terbaru']}; periode tersimpan: {', '.join(a['periode'])})"]
    lines.append("Tahunan (FY): | periode | pendapatan | laba bersih | margin bersih | ROE | DER | FCF | CFO/laba |")
    for r in a["tahunan"]:
        lines.append(f"  {r['periode']}: pendapatan {rp(r.get('pendapatan'))}" + (f" ({r['pendapatan_yoy']:+.1%} YoY)" if "pendapatan_yoy" in r else "") +
                     f"; laba bersih {rp(r.get('laba_bersih'))}" + (f" ({r['laba_bersih_yoy']:+.1%} YoY)" if "laba_bersih_yoy" in r else "") +
                     f"; margin bersih {pc(r.get('margin_bersih'))}; ROE {pc(r.get('roe'))}; DER {nm(r.get('der'))}x; FCF {rp(r.get('fcf'))}; CFO/laba {nm(r.get('cfo_per_laba'))}x")
    if a.get("ttm"):
        lines.append("TTM: " + ", ".join(f"{k} {rp(v)}" if k != "dividen_per_saham" else f"DPS Rp{v:,.0f}" for k, v in a["ttm"].items()))
    if "utang_bersih" in a:
        lines.append(f"Utang bersih (utang berbunga − kas): {rp(a['utang_bersih'])}")
    if a.get("cakupan_bunga") is not None:
        lines.append(f"Cakupan bunga (laba usaha / beban bunga): {nm(a['cakupan_bunga'], 1)}x")
    if "harga" in a:
        lines.append(f"Valuasi pada harga {a['harga']:,.0f} ({a.get('tanggal_harga') or 'tanggal?'}): PER {nm(a.get('per'), 1)}x; PBV {nm(a.get('pbv'), 2)}x; dividen yield {pc(a.get('dividen_yield'))}; payout {pc(a.get('payout'))}; "
                     f"FCF yield {pc(a.get('fcf_yield'))}; EPS TTM Rp{nm(a.get('eps_ttm'), 1)}; BVPS Rp{nm(a.get('bvps'), 1)}; kapitalisasi {rp(a.get('kapitalisasi'), 1e12, 'triliun')}".replace(",", "."))
    else:
        lines.append("Rasio valuasi (PER/PBV/yield) membutuhkan harga: impor data harga dulu.")
    lines += [f"⚠ rekonsiliasi: {x}" for x in a["rekonsiliasi"]] + [f"catatan: {x}" for x in a["catatan"]]
    return "\n".join(lines)


# ---------- valuasi ----------
def sensitivity_dcf(fcf0: float, g1: float, n: int, g_term: float, r: float, shares: float, kas: float = 0.0, utang: float = 0.0) -> float:
    """Nilai per saham = PV(FCF tahap 1) + PV(nilai terminal) (+ kas - utang bila diberikan), FCF dianggap arus ke pemegang saham (proksi)."""
    pv, cf = 0.0, fcf0
    for t in range(1, n + 1):
        cf *= 1 + g1
        pv += cf / (1 + r) ** t
    tv = cf * (1 + g_term) / (r - g_term)
    pv += tv / (1 + r) ** n
    return (pv + kas - utang) / shares


def _check_rates(r: float, g_term: float, g1: float | None = None):
    if not 0.05 <= r <= 0.30:
        raise SahamError("tingkat diskonto (biaya ekuitas) harus 5%-30% (desimal, mis. 0,12).")
    if g_term > 0.07 or g_term < -0.02:
        raise SahamError("pertumbuhan terminal harus antara -2% dan 7% (tidak boleh melebihi pertumbuhan ekonomi nominal jangka panjang).")
    if r - g_term < 0.01:
        raise SahamError("diskonto harus lebih besar dari pertumbuhan terminal minimal 1 poin persen.")
    if g1 is not None and not -0.30 <= g1 <= 0.30:
        raise SahamError("pertumbuhan tahap 1 harus antara -30% dan 30%.")


def valuasi_dcf(fcf0: float, g1: float, n: int, g_term: float, r: float, shares: float, harga: float | None = None, kas: float = 0.0, utang: float = 0.0) -> dict:
    _check_rates(r, g_term, g1)
    if fcf0 <= 0:
        raise SahamError("FCF dasar <= 0: DCF tidak bermakna. Pakai metode lain (DDM/relatif) atau normalisasi FCF dengan asumsi tertulis.")
    if not 1 <= n <= 15 or shares <= 0:
        raise SahamError("tahun tahap 1 harus 1-15 dan jumlah saham > 0.")
    grid = {}
    for dr in (-0.01, 0.0, 0.01):
        for dg in (-0.01, 0.0, 0.01):
            rr, gg = r + dr, g_term + dg
            if rr - gg >= 0.01 and rr >= 0.05:
                grid[(round(rr, 4), round(gg, 4))] = sensitivity_dcf(fcf0, g1, n, gg, rr, shares, kas, utang)
    base = grid[(round(r, 4), round(g_term, 4))]
    vals = sorted(grid.values())
    out = {"metode": "DCF (FCF sebagai proksi arus ke pemegang saham)", "dasar": base, "rendah": vals[0], "tinggi": vals[-1], "grid": grid,
           "asumsi": {"fcf_dasar": fcf0, "pertumbuhan_tahap1": g1, "tahun_tahap1": n, "pertumbuhan_terminal": g_term, "diskonto": r, "saham": shares, "kas": kas, "utang": utang}}
    tv_share = (fcf0 * (1 + g1) ** n * (1 + g_term) / (r - g_term) / (1 + r) ** n) / (shares * base) if base else None
    out["porsi_terminal"] = tv_share
    if harga:
        out["harga"], out["margin_of_safety"] = harga, base / harga - 1 if harga else None
    return out


def valuasi_ddm(dps0: float, g1: float, n: int, g_term: float, r: float, harga: float | None = None) -> dict:
    _check_rates(r, g_term, g1)
    if dps0 <= 0:
        raise SahamError("DPS dasar <= 0: DDM tidak berlaku (emiten tidak membayar dividen).")
    def f(rr, gg):
        pv, d = 0.0, dps0
        for t in range(1, n + 1):
            d *= 1 + g1
            pv += d / (1 + rr) ** t
        return pv + d * (1 + gg) / (rr - gg) / (1 + rr) ** n
    grid = {(round(r + dr, 4), round(g_term + dg, 4)): f(r + dr, g_term + dg) for dr in (-0.01, 0, 0.01) for dg in (-0.01, 0, 0.01) if (r + dr) - (g_term + dg) >= 0.01}
    base = grid[(round(r, 4), round(g_term, 4))]
    vals = sorted(grid.values())
    out = {"metode": "DDM (dua tahap)", "dasar": base, "rendah": vals[0], "tinggi": vals[-1], "grid": grid,
           "asumsi": {"dps_dasar": dps0, "pertumbuhan_tahap1": g1, "tahun_tahap1": n, "pertumbuhan_terminal": g_term, "diskonto": r}}
    if harga:
        out["harga"], out["margin_of_safety"] = harga, base / harga - 1
    return out


def valuasi_relatif(eps: float | None, bvps: float | None, per_pembanding: float | None, pbv_pembanding: float | None, harga: float | None) -> dict:
    out = {"metode": "Relatif (multipel pembanding)", "implied": {}}
    if eps and eps > 0 and per_pembanding and per_pembanding > 0:
        out["implied"]["PER"] = eps * per_pembanding
    if bvps and bvps > 0 and pbv_pembanding and pbv_pembanding > 0:
        out["implied"]["PBV"] = bvps * pbv_pembanding
    if not out["implied"]:
        raise SahamError("Butuh EPS>0 dan PER pembanding, dan/atau BVPS>0 dan PBV pembanding (dengan sumbernya).")
    vals = sorted(out["implied"].values())
    out["rendah"], out["tinggi"], out["dasar"] = vals[0], vals[-1], sum(vals) / len(vals)
    if harga:
        out["harga"], out["margin_of_safety"] = harga, out["dasar"] / harga - 1
    return out


def render_valuasi(kode: str, v: dict) -> str:
    lines = [f"VALUASI {kode}: {v['metode']}", f"Nilai wajar per saham: dasar Rp{v['dasar']:,.0f}; rentang sensitivitas Rp{v['rendah']:,.0f} - Rp{v['tinggi']:,.0f}".replace(",", ".")]
    if "asumsi" in v:
        lines.append("Asumsi: " + ", ".join(f"{k}={val:,.4g}" for k, val in v["asumsi"].items()))
    if "implied" in v:
        lines.append("Nilai tersirat: " + ", ".join(f"{k} Rp{val:,.0f}" for k, val in v["implied"].items()))
    if "harga" in v:
        lines.append(f"Harga pasar Rp{v['harga']:,.0f} -> margin of safety {v['margin_of_safety']:+.1%} (positif = harga di bawah nilai dasar)".replace(",", "."))
    if v.get("porsi_terminal") is not None:
        lines.append(f"Porsi nilai terminal terhadap nilai total: {v['porsi_terminal']:.0%}" + (" (TINGGI: hasil sangat bergantung asumsi jangka panjang)" if v["porsi_terminal"] > 0.7 else ""))
    if v.get("grid"):
        lines.append("Sensitivitas (diskonto, pertumbuhan terminal) -> nilai/saham: " + "; ".join(f"({r:.0%}, {g:.0%}) Rp{val:,.0f}" for (r, g), val in sorted(v["grid"].items())))
    lines.append("Peringatan: valuasi sangat sensitif terhadap asumsi; ini rentang perkiraan, bukan harga target pasti.")
    return "\n".join(lines).replace(",", ".") if False else "\n".join(lines)
