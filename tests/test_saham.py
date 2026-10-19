import math

import numpy as np
import pandas as pd
import pytest

from chunai.saham import impor, profil, store, teknikal, validasi
from chunai.saham.store import SahamError
from chunai.saham.tools import saham_tools


@pytest.fixture(autouse=True)
def sdir(tmp_path, monkeypatch):
    monkeypatch.setenv("CHUNAI_SAHAM_DIR", str(tmp_path / "saham"))
    return tmp_path


def make_df(n=300, seed=1, start=5000.0, end="2026-10-16"):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(end=end, periods=n)
    close = start * np.exp(np.cumsum(rng.normal(0.0004, 0.015, n)))
    close = np.round(close / 5) * 5
    high = np.maximum(close, np.roll(close, 1)) * (1 + rng.uniform(0, 0.01, n))
    low = np.minimum(close, np.roll(close, 1)) * (1 - rng.uniform(0, 0.01, n))
    open_ = np.roll(close, 1)
    high, low = np.maximum(high, np.maximum(open_, close)), np.minimum(low, np.minimum(open_, close))
    return pd.DataFrame({"open": open_, "high": high, "low": low, "close": close, "volume": rng.integers(2_000_000, 9_000_000, n).astype(float)}, index=idx).rename_axis("date")


# ---------- indikator vs hitungan acuan independen ----------
def test_rsi_known_values_and_independent_loop():
    c = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64])
    r = teknikal.rsi(c)
    assert r.iloc[:14].isna().all()
    # 14 selisih pertama: gain 3.34, loss 1.40 -> RSI = 100-100/(1+3.34/1.40) = 70.4545
    assert r.iloc[14] == pytest.approx(100 - 100 / (1 + 3.34 / 1.40), abs=1e-6)
    ag, al = 3.34 / 14, 1.40 / 14                                    # implementasi acuan sederhana (loop Python murni)
    ref = [100 - 100 / (1 + ag / al)]
    for i in range(15, len(c)):
        d = c[i] - c[i - 1]
        ag, al = (ag * 13 + max(d, 0)) / 14, (al * 13 + max(-d, 0)) / 14
        ref.append(100 - 100 / (1 + ag / al))
    assert r.iloc[14:].tolist() == pytest.approx(ref, abs=1e-9)


def test_sma_ema_atr_macd_against_manual():
    df = make_df(120)
    c = df["close"]
    assert teknikal.sma(c, 20).iloc[-1] == pytest.approx(c.iloc[-20:].mean())
    alpha = 2 / (12 + 1)                                              # EMA acuan: benih SMA? pandas adjust=False mulai dari nilai pertama
    e = c.iloc[0]
    for v in c.iloc[1:]:
        e = alpha * v + (1 - alpha) * e
    assert teknikal.ema(c, 12).iloc[-1] == pytest.approx(e, rel=1e-12)
    tr = [max(df["high"].iloc[i] - df["low"].iloc[i], abs(df["high"].iloc[i] - c.iloc[i - 1]), abs(df["low"].iloc[i] - c.iloc[i - 1])) for i in range(1, len(df))]
    a = sum(tr[:14]) / 14
    for t in tr[14:]:
        a = (a * 13 + t) / 14
    assert teknikal.atr(df).iloc[-1] == pytest.approx(a, rel=1e-12)
    m, s, h = teknikal.macd(c)
    assert h.iloc[-1] == pytest.approx(m.iloc[-1] - s.iloc[-1])


def test_tick_and_rounding():
    assert [teknikal.tick_size(p) for p in (150, 199, 200, 499, 500, 1999, 2000, 4999, 5000, 9000)] == [1, 1, 2, 2, 5, 5, 10, 10, 25, 25]
    assert teknikal.round_tick(4987, "down") == 4980 and teknikal.round_tick(4987, "up") == 4990 and teknikal.round_tick(4988) == 4990
    assert teknikal.round_tick(5012, "down") == 5000 and teknikal.round_tick(5013, "nearest") == 5025


def test_trading_plan_math():
    df = make_df(100)
    p = teknikal.trading_plan(df, modal=100_000_000, risiko_persen=1.0, entry=5000, stop=4800)
    assert p["risiko_per_lembar"] == 200 and p["lot"] == 50 and p["lembar"] == 5000          # 1jt / 200 = 5000 lembar = 50 lot
    assert p["nilai_beli"] == pytest.approx(5000 * 5000 * 1.0015)
    assert p["rugi_di_stop"] == pytest.approx(5000 * 200 + 5000 * 5000 * 0.0015 + 5000 * 4800 * 0.0025)
    t1 = p["target"][0]
    assert t1["target"] == 5200 and t1["laba_bersih"] == pytest.approx(5000 * 200 - 5000 * 5000 * 0.0015 - 5000 * 5200 * 0.0025)
    assert p["rugi_di_stop_persen_modal"] > 0.01                                                # biaya membuat rugi sedikit > 1%
    capped = teknikal.trading_plan(df, modal=10_000_000, risiko_persen=5.0, entry=5000, stop=4950)
    assert capped["nilai_beli"] <= 10_000_000 and any("modal tunai" in n for n in capped["catatan"])
    tiny = teknikal.trading_plan(df, modal=1_000_000, risiko_persen=0.5, entry=5000, stop=4500)
    assert tiny["lot"] == 0 and any("terlalu kecil" in n for n in tiny["catatan"])
    for bad in (dict(entry=5000, stop=5100), dict(modal=0), dict(risiko_persen=9)):
        kw = dict(modal=1e8, risiko_persen=1.0) | bad
        with pytest.raises(ValueError):
            teknikal.trading_plan(df, **kw)


def test_analyze_fields_and_trend():
    df = make_df(300)
    a = teknikal.analyze(df)
    assert a["tanggal"] == "2026-10-16" and a["sma200"] == pytest.approx(df["close"].iloc[-200:].mean())
    assert a["return_12b"] == pytest.approx(df["close"].iloc[-1] / df["close"].iloc[-253] - 1)
    assert a["tertinggi_52m"] == df["close"].iloc[-252:].max() and a["max_drawdown_1t"] <= 0
    up = df.copy()
    up["close"] = np.linspace(1000, 3000, len(up))
    up[["open", "high", "low"]] = up[["close"]].values * np.array([[0.99, 1.01, 0.98]])
    assert teknikal.analyze(up)["tren"].startswith("naik")
    dn = up.copy()
    dn["close"] = np.linspace(3000, 1000, len(dn))
    dn[["open", "high", "low"]] = dn[["close"]].values * np.array([[1.01, 1.02, 0.99]])
    assert teknikal.analyze(dn)["tren"].startswith("turun")
    short = teknikal.analyze(df.iloc[-30:])
    assert short["sma200"] is None and "belum dapat" in short["tren"]
    assert "ANALISIS TEKNIKAL XYZ" in teknikal.render("XYZ", a)


# ---------- impor ----------
def test_import_indonesian_csv_with_preamble(tmp_path):
    f = tmp_path / "bbca.csv"
    f.write_text("Riwayat Harga BBCA;;;;;\nDiunduh 16 Okt 2026;;;;;\nTanggal;Pembukaan;Tertinggi;Terendah;Penutupan;Volume\n"
                 "15 Okt 2026;9.200;9.350;9.150;9.300;12.345.678\n14 Okt 2026;9.100;9.250;9.050;9.200;10.000.000\n13 Okt 2026;9.000;9.150;8.950;9.100;9.500.000\n")
    df, rep = impor.parse_file(f)
    assert list(df.index.strftime("%Y-%m-%d")) == ["2026-10-13", "2026-10-14", "2026-10-15"]
    assert df["close"].tolist() == [9100, 9200, 9300] and df["volume"].iloc[-1] == 12345678
    assert rep["format_angka"] == {"open": "id", "high": "id", "low": "id", "close": "id", "volume": "id"} and any("disimpulkan" in c for c in rep["catatan"])


def test_import_english_csv_and_decimals(tmp_path):
    f = tmp_path / "x.csv"
    f.write_text("Date,Open,High,Low,Close,Adj Close,Volume\n2026-10-13,9000.5,9150.25,8950,9100.75,9100.75,\"9,500,000\"\n2026-10-14,9100,9250,9050,9200,9200,\"10,000,000\"\n")
    df, rep = impor.parse_file(f)
    assert df["close"].tolist() == [9100.75, 9200] and df["volume"].tolist() == [9500000, 10000000] and rep["format_tanggal"] == "YYYY-MM-DD"


def test_import_ambiguous_number_format_asks(tmp_path):
    f = tmp_path / "a.csv"
    f.write_text("Tanggal,Close\n2026-10-13,9.100\n2026-10-14,9.200\n")
    with pytest.raises(SahamError, match="format_angka"):
        impor.parse_file(f)
    df, _ = impor.parse_file(f, format_angka="id")
    assert df["close"].tolist() == [9100, 9200]
    df, _ = impor.parse_file(f, format_angka="en")
    assert df["close"].tolist() == [9.1, 9.2]


def test_import_date_formats_duplicates_and_missing_columns(tmp_path):
    f = tmp_path / "d.csv"
    f.write_text("Tanggal,Close\n25/10/2026,100\n24/10/2026,99\n24/10/2026,98\n")
    df, rep = impor.parse_file(f)
    assert df.index[-1].day == 25 and df.loc["2026-10-24", "close"] == 98 and any("tanggal ganda" in c for c in rep["catatan"])
    amb = tmp_path / "amb.csv"
    amb.write_text("Tanggal,Close\n03/04/2026,100\n04/04/2026,101\n")
    _, rep = impor.parse_file(amb)
    assert "diasumsikan" in rep["format_tanggal"] and rep["catatan"]
    bad = tmp_path / "bad.csv"
    bad.write_text("nama,umur\nbudi,3\n")
    with pytest.raises(SahamError, match="tidak terdeteksi"):
        impor.parse_file(bad)
    m = tmp_path / "m.csv"
    m.write_text("Hari,Harga Akhir\n2026-10-13,100\n2026-10-14,101\n")
    df, _ = impor.parse_file(m, kolom={"date": "Hari", "close": "Harga Akhir"})
    assert df["close"].tolist() == [100, 101]


def test_import_xlsx(tmp_path):
    f = tmp_path / "h.xlsx"
    pd.DataFrame({"Tanggal": ["2026-10-13", "2026-10-14"], "Open": [1, 2], "High": [2, 3], "Low": [1, 1], "Close": [2, 3], "Volume": [10, 20]}).to_excel(f, index=False)
    df, _ = impor.parse_file(f)
    assert df["close"].tolist() == [2, 3]


# ---------- validasi ----------
def test_validation_cases():
    df = make_df(200)
    v = validasi.validate_prices(df, today="2026-10-17")
    assert v["status"] == "lolos", v
    stale = validasi.validate_prices(df, today="2026-12-01")
    assert stale["status"] == "lolos_dengan_catatan" and any("TIDAK SEGAR" in c for c in stale["catatan"])
    j = df.copy()
    j.iloc[100, j.columns.get_loc("close")] *= 2
    assert any("lonjakan" in c and "aksi korporasi" in c for c in validasi.validate_prices(j, today="2026-10-17")["catatan"])
    neg = df.copy()
    neg.iloc[5, neg.columns.get_loc("close")] = -1
    assert validasi.validate_prices(neg, today="2026-10-17")["status"] == "ditolak"
    gap = pd.concat([df.iloc[:100], df.iloc[130:]])
    assert any("bolong" in c for c in validasi.validate_prices(gap, today="2026-10-17")["catatan"])
    ohlc = df.copy()
    ohlc.iloc[:, ohlc.columns.get_loc("high")] = ohlc["low"] - 1
    assert validasi.validate_prices(ohlc, today="2026-10-17")["status"] == "ditolak"
    assert validasi.validate_prices(df.iloc[:1])["status"] == "ditolak"
    short = validasi.validate_prices(df.iloc[-30:], today="2026-10-17")
    assert any("< 60" in c for c in short["catatan"])


# ---------- penyimpanan dan jejak sumber ----------
def test_store_merge_and_provenance(tmp_path):
    a, b = make_df(100), make_df(100, seed=2)
    store.save_prices("bbca.jk", a.iloc[:60], "Stockbit", "diunggah", "a.csv", "abc")
    e = store.save_prices("BBCA", b.iloc[40:], "idx.co.id", "dicari", "b.csv", "def")
    got = store.load_prices("BBCA")
    assert len(got) == 100 and e["menimpa"] == 20 and got.loc[b.index[50], "close"] == b.loc[b.index[50], "close"]
    meta = store.load_meta("BBCA")
    assert [m["sumber"] for m in meta] == ["Stockbit", "idx.co.id"] and meta[0]["sha256"] == "abc" and meta[0]["metode"] == "diunggah"
    assert store.list_codes() == ["BBCA"]
    for bad in ("", "a b", "../x", "X" * 20):
        with pytest.raises(SahamError):
            store.norm_kode(bad)
    assert store.norm_kode("^jkse") == "^JKSE"
    with pytest.raises(SahamError, match="Belum ada data"):
        store.load_prices("TLKM")


# ---------- profil ----------
def test_profile_validation_and_roundtrip():
    p = profil.validate("Panjang", "moderat", 250_000_000, 1.5, ["dividen", " syariah "], "BBCA 100 lot @9000")
    profil.save(p)
    assert profil.load()["horizon"] == "panjang" and profil.load()["preferensi"] == ["dividen", "syariah"]
    assert "Modal: Rp250.000.000" in profil.render(profil.load())
    for args in (("sebentar", "moderat", 1, 1, []), ("pendek", "gila", 1, 1, []), ("pendek", "moderat", 0, 1, []), ("pendek", "moderat", 1, 9, []), ("pendek", "moderat", "x", 1, [])):
        with pytest.raises(SahamError):
            profil.validate(*args)
    assert "belum diisi" in profil.render({})


# ---------- tool end-to-end ----------
async def test_tools_end_to_end(tmp_path):
    ws = tmp_path / "ws"
    (ws / "masukan").mkdir(parents=True)
    df = make_df(300)
    out = df.reset_index().rename(columns={"date": "Tanggal", "open": "Open", "high": "High", "low": "Low", "close": "Close", "volume": "Volume"})
    out["Tanggal"] = out["Tanggal"].dt.strftime("%Y-%m-%d")
    out.to_csv(ws / "masukan" / "tlkm.csv", index=False)
    out.assign(Close=out["Close"] * 0.5, Open=out["Open"] * 0.5, High=out["High"] * 0.5, Low=out["Low"] * 0.5).to_csv(ws / "masukan" / "bbri.csv", index=False)
    T = {t.name: t for t in saham_tools(ws)}
    txt = lambda r: r["content"][0]["text"]
    r = await T["impor_data_saham"].handler({"path": "masukan/tlkm.csv", "kode": "TLKM", "sumber": "Stockbit"})
    assert not r.get("is_error") and "Tersimpan TLKM: 300 baris" in txt(r)
    assert (await T["impor_data_saham"].handler({"path": "masukan/tlkm.csv", "kode": "TLKM", "sumber": ""})).get("is_error")
    assert not (await T["impor_data_saham"].handler({"path": "masukan/bbri.csv", "kode": "BBRI", "sumber": "idx.co.id"})).get("is_error")
    assert "TLKM" in txt(await T["daftar_data_saham"].handler({})) and "Stockbit" in txt(await T["daftar_data_saham"].handler({}))
    assert "Jejak sumber" in txt(await T["periksa_data_saham"].handler({"kode": "tlkm"}))
    a = txt(await T["analisis_teknikal"].handler({"kode": "TLKM"}))
    assert "ANALISIS TEKNIKAL TLKM" in a and "bukan ramalan" in a
    r = await T["rencana_trading"].handler({"kode": "TLKM"})
    assert r.get("is_error") and "profil investor" in txt(r)
    r = await T["simpan_profil_investor"].handler({"horizon": "menengah", "toleransi_risiko": "moderat", "modal": 100000000, "risiko_persen": 1.0, "preferensi": ["dividen"]})
    assert not r.get("is_error")
    r = await T["rencana_trading"].handler({"kode": "TLKM"})
    assert "RENCANA TRADING TLKM" in txt(r) and "bukan perintah" in txt(r)
    c = txt(await T["bandingkan_saham"].handler({"kodes": ["TLKM", "BBRI"]}))
    assert "| TLKM |" in c and "| BBRI |" in c and "bukan" not in c.split("\n")[0]
    assert (await T["bandingkan_saham"].handler({"kodes": ["TLKM"]})).get("is_error")
    g = txt(await T["grafik_saham"].handler({"kode": "TLKM", "hari": 120}))
    assert (ws / g.split(": ")[1]).is_file()
    assert (await T["analisis_teknikal"].handler({"kode": "XXXX"})).get("is_error")
