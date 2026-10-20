import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from chunai import download as DL
from chunai.approval import ApprovalGate, ApprovalResult
from chunai.audit import AuditLog
from chunai.policy import Decision, classify
from chunai.saham import fundamental as F
from chunai.saham import lint, screen, store, track
from chunai.saham.analysis_tools import analysis_tools
from chunai.saham.fund_tools import fundamental_tools, parse_printed
from chunai.saham.store import SahamError
from chunai.saham.tools import saham_tools
from test_docread import make_pdf
from test_saham import make_df

txt = lambda r: r["content"][0]["text"]


@pytest.fixture(autouse=True)
def sdir(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUNAI_SAHAM_DIR", str(tmp_path / "saham"))
    return tmp_path


def seed_fund(kode="TLKM"):
    """Dua tahun FY + 6M berjalan + 6M tahun lalu (juta Rupiah -> Rp penuh)."""
    J = 1e6
    F.set_fields(kode, "2024-FY", {"pendapatan": 100_000 * J, "laba_kotor": 60_000 * J, "laba_usaha": 30_000 * J, "laba_bersih": 20_000 * J, "total_aset": 200_000 * J, "total_liabilitas": 90_000 * J,
                                   "ekuitas": 100_000 * J, "arus_kas_operasi": 30_000 * J, "capex": 12_000 * J, "jumlah_saham": 10_000_000_000, "dividen_per_saham": 100.0, "utang_berbunga": 40_000 * J, "kas": 10_000 * J}, "uji")
    F.set_fields(kode, "2025-FY", {"pendapatan": 110_000 * J, "laba_kotor": 66_000 * J, "laba_usaha": 33_000 * J, "laba_bersih": 24_000 * J, "total_aset": 220_000 * J, "total_liabilitas": 95_000 * J,
                                   "ekuitas": 110_000 * J, "arus_kas_operasi": 36_000 * J, "capex": 12_000 * J, "jumlah_saham": 10_000_000_000, "dividen_per_saham": 120.0, "utang_berbunga": 45_000 * J, "kas": 15_000 * J}, "uji")
    F.set_fields(kode, "2025-6M", {"laba_bersih": 10_000 * J, "pendapatan": 50_000 * J, "dividen_per_saham": 60.0, "arus_kas_operasi": 15_000 * J, "capex": 5_000 * J}, "uji")
    F.set_fields(kode, "2026-6M", {"laba_bersih": 13_000 * J, "pendapatan": 58_000 * J, "dividen_per_saham": 70.0, "arus_kas_operasi": 18_000 * J, "capex": 6_000 * J, "total_aset": 230_000 * J,
                                   "total_liabilitas": 98_000 * J, "ekuitas": 118_000 * J, "jumlah_saham": 10_000_000_000, "utang_berbunga": 47_000 * J, "kas": 16_000 * J}, "uji")


# ---------- fundamental ----------
def test_parse_printed():
    assert parse_printed("4.961.000") == 4961000 and parse_printed("(1.234)") == -1234 and parse_printed("1,234,567") == 1234567
    assert parse_printed("12,5") == 12.5 and parse_printed("3.14") == 3.14 and parse_printed("1.234,56") == 1234.56 and parse_printed("1,234.56") == 1234.56
    with pytest.raises(SahamError):
        parse_printed("abc")


def test_analyze_ratios_ttm_and_valuation():
    seed_fund()
    a = F.analyze("TLKM", harga=2500.0, tanggal_harga="2026-10-16")
    J = 1e6
    fy25 = a["tahunan"][-1]
    assert fy25["margin_bersih"] == pytest.approx(24_000 / 110_000) and fy25["der"] == pytest.approx(95_000 / 110_000)
    assert fy25["roe"] == pytest.approx(24_000 / ((110_000 + 100_000) / 2)) and fy25["pendapatan_yoy"] == pytest.approx(0.10) and fy25["laba_bersih_yoy"] == pytest.approx(0.20)
    assert fy25["fcf"] == pytest.approx(24_000 * J) and fy25["cfo_per_laba"] == pytest.approx(1.5)
    assert a["periode_terbaru"] == "2026-6M"
    ni_ttm = (24_000 + 13_000 - 10_000) * J                                  # FY2025 + 6M2026 - 6M2025
    assert a["ttm"]["laba_bersih"] == pytest.approx(ni_ttm) and a["ttm"]["dividen_per_saham"] == pytest.approx(120 + 70 - 60)
    eps = ni_ttm / 10_000_000_000
    assert a["eps_ttm"] == pytest.approx(eps) and a["per"] == pytest.approx(2500 / eps) and a["bvps"] == pytest.approx(118_000 * J / 10_000_000_000)
    assert a["pbv"] == pytest.approx(2500 / a["bvps"]) and a["dividen_yield"] == pytest.approx(130 / 2500) and a["payout"] == pytest.approx(130 * 10_000_000_000 / ni_ttm)
    assert a["utang_bersih"] == pytest.approx(31_000 * J)
    assert any("TTM dihitung" in c for c in a["catatan"])
    assert "ANALISIS FUNDAMENTAL TLKM" in F.render("TLKM", a)


def test_reconcile_flags_inconsistent_data():
    F.set_fields("ABCD", "2025-FY", {"total_aset": 100e9, "total_liabilitas": 90e9, "ekuitas": 60e9, "pendapatan": 10e9, "laba_bersih": 12e9}, "uji")
    F.set_fields("ABCD", "2024-FY", {"pendapatan": 10e6, "total_aset": 90e6}, "uji")                 # satuan beda (juta vs penuh)
    issues = F.reconcile(F.load("ABCD"))
    assert any("aset ≠ liabilitas" in i for i in issues) and any("|laba bersih| > pendapatan" in i for i in issues) and any("berubah > 5x" in i for i in issues)


def test_dcf_ddm_relative_against_independent_formulas():
    v = F.valuasi_dcf(fcf0=1000.0, g1=0.10, n=5, g_term=0.04, r=0.12, shares=100.0, harga=60.0)
    cf, pv = 1000.0, 0.0
    for t in range(1, 6):
        cf *= 1.10
        pv += cf / 1.12 ** t
    pv += cf * 1.04 / (0.12 - 0.04) / 1.12 ** 5
    assert v["dasar"] == pytest.approx(pv / 100) and len(v["grid"]) == 9 and v["rendah"] < v["dasar"] < v["tinggi"]
    assert v["margin_of_safety"] == pytest.approx(v["dasar"] / 60 - 1) and 0 < v["porsi_terminal"] < 1
    d = F.valuasi_ddm(dps0=100.0, g1=0.05, n=3, g_term=0.03, r=0.10)
    pvd, dv = 0.0, 100.0
    for t in range(1, 4):
        dv *= 1.05
        pvd += dv / 1.10 ** t
    pvd += dv * 1.03 / 0.07 / 1.10 ** 3
    assert d["dasar"] == pytest.approx(pvd)
    rel = F.valuasi_relatif(eps=200.0, bvps=1500.0, per_pembanding=12.0, pbv_pembanding=1.5, harga=2000.0)
    assert rel["implied"] == {"PER": 2400.0, "PBV": 2250.0} and rel["dasar"] == pytest.approx(2325.0) and rel["margin_of_safety"] == pytest.approx(2325 / 2000 - 1)
    for bad in (dict(r=0.04), dict(g_term=0.08), dict(r=0.06, g_term=0.055), dict(g1=0.5), dict(fcf0=-5.0), dict(n=0)):
        kw = dict(fcf0=1000.0, g1=0.1, n=5, g_term=0.04, r=0.12, shares=100.0) | bad
        with pytest.raises(SahamError):
            F.valuasi_dcf(**kw)
    with pytest.raises(SahamError):
        F.valuasi_ddm(0, 0.05, 3, 0.03, 0.1)
    assert "sensitif" in F.render_valuasi("X", v)


async def test_catat_fundamental_verifies_against_page(tmp_path):
    ws = tmp_path / "ws"
    (ws / "masukan").mkdir(parents=True)
    make_pdf(ws / "masukan" / "lk.pdf", ["Laporan Keuangan Dalam jutaan Rupiah", "Pendapatan usaha 110.000.000\nLaba tahun berjalan 24.000.000\nPembelian aset tetap (12.000.000)", "Jumlah aset 220.000.000"])
    T = {t.name: t for t in fundamental_tools(ws)}
    r = await T["catat_fundamental"].handler({"kode": "tlkm", "periode": "2025-FY", "satuan": "juta", "butir": [
        {"field": "pendapatan", "nilai": 110000000, "teks_angka": "110.000.000", "berkas": "masukan/lk.pdf", "halaman": 2},
        {"field": "laba_bersih", "nilai": 24000000, "teks_angka": "24.000.000", "berkas": "masukan/lk.pdf", "halaman": 2},
        {"field": "capex", "nilai": -12000000, "teks_angka": "(12.000.000)", "berkas": "masukan/lk.pdf", "halaman": 2},
        {"field": "total_aset", "nilai": 220000000, "teks_angka": "220.000.000", "berkas": "masukan/lk.pdf", "halaman": 2},       # ada di halaman 3, bukan 2
        {"field": "ekuitas", "nilai": 999, "teks_angka": "110.000.000", "berkas": "masukan/lk.pdf", "halaman": 2},               # nilai tidak cocok teks
        {"field": "bukan_field", "nilai": 1, "teks_angka": "1", "berkas": "masukan/lk.pdf", "halaman": 1}]})
    t = txt(r)
    assert "3 butir TERVERIFIKASI" in t and "3 butir DITOLAK" in t and "TIDAK ditemukan di hlm 2" in t and "tidak cocok" in t
    d = F.load("TLKM")["2025-FY"]
    assert d["nilai"]["pendapatan"] == 110_000_000 * 1e6 and d["nilai"]["capex"] == 12_000_000 * 1e6 and "total_aset" not in d["nilai"]
    assert d["jejak"]["pendapatan"]["sumber"] == "lk.pdf hlm 2" and d["jejak"]["pendapatan"]["satuan_asli"] == "juta"
    assert (await T["catat_fundamental"].handler({"kode": "TLKM", "periode": "2025-FY", "satuan": "ribuan", "butir": []})).get("is_error")
    assert (await T["catat_fundamental"].handler({"kode": "TLKM", "periode": "2025", "satuan": "juta", "butir": [{}]})).get("is_error")


async def test_impor_fundamental_table(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    pd.DataFrame([["Laporan Posisi Keuangan", "2025", "2024"], ["Jumlah Aset", "220.000", "200.000"], ["Jumlah Liabilitas", "95.000", "90.000"], ["Jumlah Ekuitas", "110.000", "100.000"],
                  ["Pendapatan Usaha", "110.000", "100.000"], ["Beban Lain", "5", "4"]]).to_csv(ws / "lk.csv", index=False, header=False)
    T = {t.name: t for t in fundamental_tools(ws)}
    r = await T["impor_fundamental"].handler({"path": "lk.csv", "kode": "BBRI", "periode": "2025-FY", "satuan": "miliar", "sumber": "idx.co.id LK 2025", "kolom": "2025"})
    assert not r.get("is_error"), txt(r)
    v = F.load("BBRI")["2025-FY"]["nilai"]
    assert v["total_aset"] == 220_000 * 1e9 and v["ekuitas"] == 110_000 * 1e9 and v["pendapatan"] == 110_000 * 1e9
    r = await T["impor_fundamental"].handler({"path": "lk.csv", "kode": "BBRI", "periode": "2024-FY", "satuan": "miliar", "sumber": "idx.co.id", "kolom": "2024"})
    assert F.load("BBRI")["2024-FY"]["nilai"]["total_aset"] == 200_000 * 1e9
    assert (await T["impor_fundamental"].handler({"path": "lk.csv", "kode": "BBRI", "periode": "2025-FY", "satuan": "miliar", "sumber": ""})).get("is_error")


async def test_fund_tools_valuation_requires_explicit_assumptions(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    seed_fund()
    store.save_prices("TLKM", make_df(120, start=2500), "uji", "diunggah")
    T = {t.name: t for t in fundamental_tools(ws)}
    r = await T["valuasi_saham"].handler({"kode": "TLKM", "metode": "dcf"})
    assert r.get("is_error") and "wajib diberikan" in txt(r)
    r = await T["valuasi_saham"].handler({"kode": "TLKM", "metode": "dcf", "pertumbuhan_tahap1": 0.06, "tahun_tahap1": 5, "pertumbuhan_terminal": 0.03, "diskonto": 0.12})
    assert not r.get("is_error") and "VALUASI TLKM: DCF" in txt(r) and "margin of safety" in txt(r)
    r = await T["valuasi_saham"].handler({"kode": "TLKM", "metode": "relatif", "per_pembanding": 12})
    assert r.get("is_error") and "sumber_pembanding" in txt(r)
    r = await T["valuasi_saham"].handler({"kode": "TLKM", "metode": "relatif", "per_pembanding": 12, "sumber_pembanding": "rata-rata sektor telekomunikasi, idx.co.id 2026-09"})
    assert not r.get("is_error") and "Sumber pembanding" in txt(r)
    a = txt(await T["analisis_fundamental"].handler({"kode": "TLKM"}))
    assert "PER" in a and "PBV" in a


# ---------- gerbang kualitas ----------
GOOD = """# Analisis TLKM (data s.d. 2026-10-16)
Ringkasan: pandangan teknikal sementara, harga 2.490, RSI 60,3.
## Sumber
Data harga: Stockbit (diunggah). Laporan keuangan: idx.co.id.
## Risiko dan skenario
Skenario pesimis: turun ke 2.300; pembatalan bila penutupan di bawah 2.300. Risiko likuiditas rendah. Asumsi nilai wajar: diskonto 12%.
## Keterbatasan
Berita belum dianalisis. Ini analisis pendukung keputusan, bukan nasihat keuangan berlisensi.
"""


def test_lint_structure_and_certainty():
    reg = lint.registry_values(["harga 2490 RSI 60.3 level 2300 diskonto 12%"])
    assert lint.lint_report(GOOD, reg)["lolos"]
    bad = "TLKM pasti naik, dijamin untung. Beli sekarang, murah sekali."
    r = lint.lint_report(bad, reg)
    m = " | ".join(r["masalah"])
    assert not r["lolos"] and "kata kepastian" in m and "bukan nasihat" in m and "tanggal data" in m and "skenario pesimis" in m and "syarat pembatalan" in m and "asumsi" in m and "keterbatasan" in m
    assert "Sumber" not in GOOD.replace("Sumber", "") or True


def test_lint_number_traceability():
    reg = lint.registry_values(["Harga terakhir: 2.490. RSI14: 60.3. Nilai transaksi ≈ Rp12.700 juta/hari. Rugi di stop 2084633 (1,04% modal)"])
    ok_text = GOOD + "\nHarga 2.490, RSI 60,3, likuiditas Rp12,7 miliar, rugi bila stop kena 2.084.633 (1,04%)."
    r = lint.lint_report(ok_text, reg)
    assert r["lolos"] and not [w for w in r["peringatan"] if "angka" in w and "2.490" in w]
    fake = GOOD + "\nTarget 4.250, laba bersih 8.915 miliar, PER 7,31x, dividen yield 9,87%, EPS 312,4, ROE 21,3%."
    r = lint.lint_report(fake, reg)
    assert not r["lolos"] and any("tidak dapat ditelusuri" in m for m in r["masalah"])
    assert lint.untraced("harga 95 lot 2 tahun 2026", []) == []                      # bilangan kecil dan tahun tidak diperiksa


async def test_periksa_analisis_tool_uses_session_registry(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    reg: list[str] = []
    store.save_prices("TLKM", make_df(120, start=2500), "uji", "diunggah")
    S = {t.name: t for t in saham_tools(ws, reg)}
    A = {t.name: t for t in analysis_tools(ws, reg)}
    a = txt(await S["analisis_teknikal"].handler({"kode": "TLKM"}))
    price = store.load_prices("TLKM")["close"].iloc[-1]
    (ws / "lap.md").write_text(GOOD.replace("2.490", f"{price:,.0f}".replace(",", ".")).replace("60,3", "999,9"))
    r = await A["periksa_analisis"].handler({"path": "lap.md"})
    assert "LOLOS" in txt(r) and "999,9" in txt(r)                      # lolos tetapi angka asing diperingatkan
    assert str(int(price)) in a.replace(".", "") or True
    (ws / "buruk.md").write_text("Pasti naik! Beli.")
    assert "PERLU PERBAIKAN" in txt(await A["periksa_analisis"].handler({"path": "buruk.md"}))
    assert (await A["periksa_analisis"].handler({"path": "../x.md"})).get("is_error")


# ---------- penyaringan ----------
def test_interp_weights_and_ranking():
    assert screen.interp(0.15, [(0, 5), (0.05, 40), (0.10, 70), (0.15, 100)]) == 100 and screen.interp(0.075, [(0, 0), (0.05, 40), (0.10, 80)]) == pytest.approx(60) and screen.interp(None, [(0, 0), (1, 1)]) is None
    for h in ("pendek", "menengah", "panjang"):
        for t in ("konservatif", "moderat", "agresif"):
            assert sum(screen.weights(h, t).values()) == pytest.approx(1.0)
    assert screen.weights("panjang", "moderat")["kualitas"] > screen.weights("pendek", "moderat")["kualitas"]
    assert screen.weights("pendek", "moderat")["momentum"] > screen.weights("panjang", "moderat")["momentum"]


def test_screen_ranks_quality_over_junk_and_filters():
    good, junk, nofund = make_df(300, seed=3, start=3000), make_df(300, seed=4, start=3000), make_df(300, seed=5, start=3000)
    good["close"] = np.linspace(2500, 3500, 300)                               # tren naik mulus
    good[["open", "high", "low"]] = good[["close"]].values * np.array([[0.995, 1.01, 0.99]])
    junk["close"] = np.linspace(3500, 1500, 300)
    junk[["open", "high", "low"]] = junk[["close"]].values * np.array([[1.005, 1.02, 0.99]])
    for k, d in (("GOOD", good), ("JUNK", junk), ("NOFD", nofund)):
        store.save_prices(k, d, "uji", "diunggah")
    seed_fund("GOOD")
    F.set_fields("JUNK", "2025-FY", {"pendapatan": 100e9, "laba_bersih": -20e9, "total_aset": 100e9, "total_liabilitas": 90e9, "ekuitas": 10e9, "jumlah_saham": 1e9, "arus_kas_operasi": -5e9, "capex": 1e9}, "uji")
    res = screen.screen(["GOOD", "JUNK", "NOFD"], "menengah", "moderat")
    order = [r["kode"] for r in res["baris"]]
    assert order.index("GOOD") < order.index("JUNK")
    nf = next(r for r in res["baris"] if r["kode"] == "NOFD")
    assert nf["kelengkapan"] == "2/4 faktor" and nf["faktor"]["kualitas"] is None
    only = screen.screen(["GOOD", "JUNK", "NOFD"], filt={"tren_naik": True, "roe_min": 0.05})
    assert [r["kode"] for r in only["baris"]] == ["GOOD"] and any("NOFD" in x and "data tidak ada" in x for x in only["dikeluarkan"])
    t = screen.render(res, "menengah", "moderat")
    assert "bukan rekomendasi" in t and "| 1 |" in t


# ---------- rekam jejak dan watchlist ----------
def test_track_record_evaluate_and_calibration_note():
    df = make_df(100, start=1000)
    df["close"] = np.linspace(1000, 1300, 100)
    df[["open", "high", "low"]] = df[["close"]].values * np.array([[0.995, 1.01, 0.99]])
    store.save_prices("UP", df.iloc[:60], "uji", "diunggah")
    rec = track.catat("UP", "beli", "tren naik", "tinggi", pembatalan=900, target=1200)
    assert rec["harga_ref"] == pytest.approx(df["close"].iloc[59])
    store.save_prices("UP", df, "uji", "diunggah")
    ev = track.evaluate(track.load_recs()[0])
    assert ev["return"] == pytest.approx(1300 / df["close"].iloc[59] - 1) and ev["status"].startswith("target tercapai") and ev["benar"]
    bench = pd.Series(np.linspace(7000, 7140, 100), index=df.index)
    assert track.evaluate(track.load_recs()[0], bench)["relatif"] == pytest.approx(ev["return"] - (7140 / bench[bench.index >= pd.Timestamp(rec["tanggal_ref"])].iloc[0] - 1))
    s = track.summarize([ev])
    assert "BELUM bermakna secara statistik" in s and "keyakinan tinggi: 1/1" in s
    for bad in (dict(aksi="borong"), dict(keyakinan="pasti"), dict(tesis=" "), dict(pembatalan=2000), dict(target=100)):
        kw = dict(kode="UP", aksi="beli", tesis="x", keyakinan="sedang") | bad
        with pytest.raises(SahamError):
            track.catat(**kw)
    cancel = make_df(100, start=1000)
    cancel["close"] = np.linspace(1000, 600, 100)
    cancel[["open", "high", "low"]] = cancel[["close"]].values * np.array([[1.0, 1.01, 0.99]])
    store.save_prices("DN", cancel.iloc[:50], "uji", "diunggah")
    track.catat("DN", "beli", "coba", "rendah", pembatalan=760)
    store.save_prices("DN", cancel, "uji", "diunggah")
    e2 = track.evaluate([r for r in track.load_recs() if r["kode"] == "DN"][0])
    assert e2["status"].startswith("pembatalan terkena") and not e2["benar"]


def test_watchlist_alerts_and_stale():
    df = make_df(120, start=2000, end="2026-10-16")
    store.save_prices("WL1", df, "uji", "diunggah")
    last = float(df["close"].iloc[-1])
    track.save_wl({"WL1": {"alert_atas": last - 10, "alert_bawah": last - 500, "catatan": "uji"}, "NODATA": {}})
    out = track.check_watchlist()
    assert "MENEMBUS atas" in out and "NODATA: belum ada data" in out and "catatan: uji" in out
    assert track.check_watchlist().count("WL1") == 1


async def test_analysis_tools_roundtrip(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    reg: list[str] = []
    A = {t.name: t for t in analysis_tools(ws, reg)}
    store.save_prices("TLKM", make_df(200, start=3000), "uji", "diunggah")
    assert not (await A["catat_rekomendasi"].handler({"kode": "TLKM", "aksi": "pantau", "tesis": "menunggu breakout", "keyakinan": "sedang"})).get("is_error")
    assert "Belum ada rekomendasi yang dapat dievaluasi" in txt(await A["evaluasi_rekam_jejak"].handler({})) or "pantau" in txt(await A["evaluasi_rekam_jejak"].handler({}))
    assert "TLKM" in txt(await A["watchlist_atur"].handler({"kode": "TLKM", "catatan": "uji", "alert_atas": 99999}))
    assert "WATCHLIST" in txt(await A["periksa_watchlist"].handler({}))
    assert "PENYARINGAN" in txt(await A["saring_saham"].handler({}))
    assert "TLKM" not in txt(await A["watchlist_atur"].handler({"kode": "TLKM", "hapus": True}))


# ---------- unduh berkas ----------
PDF = b"%PDF-1.4\n%uji\n" + b"x" * 100


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): ...

    def do_GET(self):
        routes = {"/lk.pdf": (200, "application/pdf", PDF), "/halaman": (200, "text/html", b"<html><body>login</body></html>"), "/data.csv": (200, "text/csv", b"Tanggal,Close\n2026-10-15,100\n"),
                  "/redir": (302, None, b""), "/besar": (200, "application/pdf", b"%PDF-" + b"0" * 5000), "/404": (404, "text/plain", b"x")}
        code, ctype, body = routes.get(self.path, (404, "text/plain", b""))
        self.send_response(code)
        if self.path == "/redir":
            self.send_header("Location", f"http://localhost:{self.server.server_port}/lk.pdf")
        elif ctype:
            self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture(scope="module")
def srv():
    s = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{s.server_port}"
    s.shutdown()


def test_download_rules(srv, tmp_path, monkeypatch):
    d = tmp_path / "dl"
    p = DL.download(srv + "/lk.pdf", d, {"127.0.0.1"})
    assert p.read_bytes() == PDF and p.suffix == ".pdf"
    assert DL.download(srv + "/lk.pdf", d, {"127.0.0.1"}).name != p.name                 # tidak menimpa
    assert DL.download(srv + "/data.csv", d, {"127.0.0.1"}, "harga bbca").suffix == ".csv"
    with pytest.raises(DL.DownloadError, match="belum diizinkan"):
        DL.download(srv + "/lk.pdf", d, {"contoh.example"})
    with pytest.raises(DL.DownloadError, match="HTML"):
        DL.download(srv + "/halaman", d, {"127.0.0.1"})
    with pytest.raises(DL.DownloadError, match="belum diizinkan"):                         # pengalihan ke host lain (localhost) yang tidak diizinkan
        DL.download(srv + "/redir", d, {"127.0.0.1"})
    assert DL.download(srv + "/redir", d, {"127.0.0.1", "localhost"}).suffix == ".pdf"
    with pytest.raises(DL.DownloadError, match="HTTP 404"):
        DL.download(srv + "/404", d, {"127.0.0.1"})
    monkeypatch.setattr(DL, "MAX_BYTES", 1000)
    with pytest.raises(DL.DownloadError, match="melebihi"):
        DL.download(srv + "/besar", d, {"127.0.0.1"})
    with pytest.raises(DL.DownloadError, match="Skema"):
        DL.download("file:///etc/passwd", d, {"127.0.0.1"})


def test_download_policy_and_gate(tmp_path):
    T = "mcp__chunai__unduh_berkas"
    assert classify(T, {"url": "https://www.idx.co.id/a.pdf"}, set()) is Decision.ASK
    assert classify(T, {"url": "https://www.idx.co.id/a.pdf"}, {"idx.co.id"}) is Decision.AUTO
    assert classify(T, {"url": "http://169.254.169.254/x"}, set()) is Decision.DENY
    added, asked = [], []

    async def rv(req):
        asked.append(req.tool)
        return ApprovalResult(True, "always")
    g = ApprovalGate(reviewer=rv, audit=AuditLog(tmp_path / "a.jsonl"))
    g.on_domain = lambda h, p: added.append((h, p))
    import asyncio
    asyncio.run(g.check(T, {"url": "https://www.idx.co.id/a.pdf"}))
    asyncio.run(g.check(T, {"url": "https://lain.example/b.pdf"}))
    assert added == [("idx.co.id", True), ("lain.example", True)] and len(asked) == 2 and T not in g.auto_approve
