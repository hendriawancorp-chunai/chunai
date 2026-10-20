"""Tool MCP skill saham: impor data, validasi, analisis teknikal, rencana trading, perbandingan, grafik, profil investor."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from claude_agent_sdk import tool

from .. import data as D
from ..timeutil import now
from . import impor, profil, store, teknikal, validasi
from .store import SahamError


def saham_tools(workdir: Path, reg: list[str] | None = None):
    workdir = workdir.resolve()

    def ok(t):
        if reg is not None:
            reg.append(t)
        return {"content": [{"type": "text", "text": t}]}
    def err(t): return {"content": [{"type": "text", "text": t}], "is_error": True}

    def guard(fn):
        async def inner(args):
            try:
                return await fn(args)
            except (SahamError, ValueError, OSError, KeyError) as e:
                return err(str(e))
            except Exception as e:
                return err(f"Gagal: {type(e).__name__}: {str(e)[:200]}")
        return inner

    def _usable(kode: str) -> tuple[pd.DataFrame, dict]:
        df = store.load_prices(kode)
        v = validasi.validate_prices(df)
        if v["status"] == "ditolak":
            raise SahamError(validasi.render(store.norm_kode(kode), v) + "\nData ditolak: perbaiki/unggah ulang sebelum dianalisis.")
        return df, v

    @tool("impor_data_saham",
          "Impor berkas harga saham (CSV/TSV/XLSX ekspor platform) di workspace ke penyimpanan data saham dengan jejak sumber. kode mis. 'BBCA'. sumber = nama platform/situs asal data (WAJIB, mis. 'Stockbit', "
          "'idx.co.id'). Kolom terdeteksi otomatis (tanggal, open, high, low, close, volume; nama Indonesia/Inggris). Bila format angka/tanggal ambigu, tool meminta format_angka ('id'|'en') / format_tanggal ('dmy'|'mdy'). "
          "kolom (opsional) = pemetaan manual {date, open, high, low, close, volume} -> nama kolom di berkas. Mengembalikan laporan pemetaan dan validasi.",
          {"path": str, "kode": str, "sumber": str, "kolom": dict, "format_angka": str, "format_tanggal": str})
    @guard
    async def impor_data_saham(args):
        sumber = str(args.get("sumber", "")).strip()
        if not sumber:
            raise SahamError("'sumber' wajib (nama platform/situs asal data) agar jejak data dapat ditelusuri.")
        src = D.resolve_in(workdir, args["path"])
        if not src.is_file():
            raise SahamError(f"File tidak ditemukan: {args['path']}")
        df, rep = impor.parse_file(src, args.get("kolom") or None, str(args.get("format_angka") or "auto"), str(args.get("format_tanggal") or "auto"))
        v = validasi.validate_prices(df)
        if v["status"] == "ditolak":
            raise SahamError("Data tidak disimpan.\n" + validasi.render(store.norm_kode(args["kode"]), v))
        entry = store.save_prices(args["kode"], df, sumber, "diunggah", src.name, store.sha256(src), rep["catatan"])
        kode = store.norm_kode(args["kode"])
        return ok(f"Tersimpan {kode}: {rep['baris']} baris ({rep['periode']}), sumber '{sumber}', diunggah.\nKolom terbaca: {rep['kolom']}\n"
                  f"Format tanggal: {rep['format_tanggal']}; format angka: {rep['format_angka']}\n" + "\n".join(f"Catatan impor: {c}" for c in rep["catatan"]) +
                  ("\n" if rep["catatan"] else "") + validasi.render(kode, v) + ("\nData lama pada tanggal yang sama ditimpa: " + str(entry["menimpa"]) if entry["menimpa"] else ""))

    @tool("daftar_data_saham", "Daftar saham yang datanya tersimpan beserta periode, sumber, dan tanggal pengambilan data.", {})
    @guard
    async def daftar_data_saham(args):
        codes = store.list_codes()
        if not codes:
            return ok("(belum ada data saham tersimpan)")
        lines = []
        for k in codes:
            m = store.load_meta(k)
            last = m[-1] if m else {}
            lines.append(f"- {k}: {last.get('periode', '?')}; sumber terakhir '{last.get('sumber', '?')}' ({last.get('metode', '?')}), diambil {last.get('diambil', '?')}")
        return ok("\n".join(lines))

    @tool("periksa_data_saham", "Validasi data harga tersimpan: kesegaran, kelengkapan, konsistensi OHLC, lonjakan tak wajar (aksi korporasi?), volume. Wajib sebelum analisis.", {"kode": str})
    @guard
    async def periksa_data_saham(args):
        kode = store.norm_kode(args["kode"])
        v = validasi.validate_prices(store.load_prices(kode))
        meta = store.load_meta(kode)
        src = "\n".join(f"  sumber: {m['sumber']} ({m['metode']}, {m['periode']}, diambil {m['diambil']})" for m in meta[-3:])
        return ok(validasi.render(kode, v) + ("\nJejak sumber:\n" + src if src else ""))

    @tool("analisis_teknikal",
          "Analisis teknikal dari data tersimpan: tren, SMA20/50/200, RSI14, MACD, Bollinger, ATR, kinerja 1/3/6/12 bulan, 52 minggu, drawdown, volatilitas, likuiditas, support/resistance. "
          "benchmark (opsional) = kode indeks tersimpan (mis. '^JKSE') untuk kinerja relatif. Angka dihitung dari data; sebut tanggal datanya.", {"kode": str, "benchmark": str})
    @guard
    async def analisis_teknikal(args):
        df, v = _usable(args["kode"])
        bench = None
        if args.get("benchmark"):
            bench = store.load_prices(args["benchmark"])["close"]
        a = teknikal.analyze(df, bench)
        extra = ("\n" + validasi.render(store.norm_kode(args["kode"]), v)) if v["status"] != "lolos" else ""
        return ok(teknikal.render(store.norm_kode(args["kode"]), a) + extra)

    @tool("rencana_trading",
          "Hitung rencana posisi beli (long): entry, stop, ukuran lot dari batas rugi per transaksi, target 1R/2R/3R, estimasi biaya, peringatan likuiditas. Memakai profil investor (modal, risiko_persen) bila tidak diberikan. "
          "entry default harga terakhir; stop default entry - 2xATR14 (atau berikan stop manual, mis. di bawah support). Hanya perhitungan, bukan perintah transaksi.",
          {"kode": str, "modal": float, "risiko_persen": float, "entry": float, "stop": float, "atr_mult": float})
    @guard
    async def rencana_trading(args):
        df, v = _usable(args["kode"])
        p = profil.load()
        modal = float(args.get("modal") or p.get("modal") or 0)
        rp = float(args.get("risiko_persen") or p.get("risiko_persen") or 0)
        if modal <= 0 or rp <= 0:
            raise SahamError("Modal dan batas risiko belum ada. Isi profil investor (simpan_profil_investor) atau berikan modal dan risiko_persen.")
        plan = teknikal.trading_plan(df, modal, rp, args.get("entry") or None, args.get("stop") or None, float(args.get("atr_mult") or 2.0))
        return ok(teknikal.render_plan(store.norm_kode(args["kode"]), plan, modal, rp) + (("\n" + validasi.render(store.norm_kode(args["kode"]), v)) if v["status"] != "lolos" else ""))

    @tool("bandingkan_saham",
          "Studi komparatif beberapa saham (2-10 kode) dari data tersimpan: harga terakhir, kinerja 1/3/6/12 bulan, volatilitas, drawdown, RSI, tren, jarak ke SMA200, likuiditas. "
          "Dasar membandingkan kandidat beli/jual; fundamental dan valuasi dibahas terpisah. Memperingatkan bila tanggal data berbeda.", {"kodes": list})
    @guard
    async def bandingkan_saham(args):
        kodes = [store.norm_kode(k) for k in (args.get("kodes") or [])]
        if not 2 <= len(kodes) <= 10:
            raise SahamError("Berikan 2-10 kode saham.")
        rows, dates, warn = [], set(), []
        for k in kodes:
            df, v = _usable(k)
            a = teknikal.analyze(df)
            dates.add(a["tanggal"])
            if v["status"] != "lolos":
                warn.append(f"{k}: " + "; ".join(v["catatan"])[:200])
            s200 = a.get("sma200")
            rows.append({"kode": k, "tanggal": a["tanggal"], "harga": a["harga"], "1b": a.get("return_1b"), "3b": a.get("return_3b"), "6b": a.get("return_6b"), "12b": a.get("return_12b"),
                         "vol": a.get("volatilitas_tahunan"), "mdd": a.get("max_drawdown_1t"), "rsi": a.get("rsi14"), "tren": a["tren"].split(" (")[0],
                         "dari_sma200": (a["harga"] / s200 - 1) if s200 else None, "nilai_trx": a.get("rata_nilai_transaksi_20")})
        f = lambda x, p=True: "n/a" if x is None else (f"{x:+.1%}" if p else f"{x:.1f}")
        lines = ["| Kode | Tgl data | Harga | 1b | 3b | 6b | 12b | Volatilitas | MaxDD 1t | RSI | Tren | vs SMA200 | Nilai trx/hari (Rp juta) |", "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
        for r in rows:
            lines.append(f"| {r['kode']} | {r['tanggal']} | {r['harga']:,.0f} | {f(r['1b'])} | {f(r['3b'])} | {f(r['6b'])} | {f(r['12b'])} | "
                         f"{'n/a' if r['vol'] is None else format(r['vol'], '.0%')} | {f(r['mdd'])} | {f(r['rsi'], False)} | {r['tren']} | {f(r['dari_sma200'])} | "
                         f"{'n/a' if r['nilai_trx'] is None else format(r['nilai_trx'] / 1e6, ',.0f')} |".replace(",", "."))
        out = "\n".join(lines)
        if len(dates) > 1:
            out += f"\n⚠ Tanggal data berbeda antar saham ({', '.join(sorted(dates))}): perbandingan tidak sejajar; perbarui data."
        out += "".join(f"\n⚠ {w}" for w in warn) + "\nCatatan: ini perbandingan harga/teknikal; keputusan beli/jual juga butuh fundamental, valuasi, dan profil risiko Anda."
        return ok(out)

    @tool("grafik_saham", "Buat grafik harga saham (harga + SMA20/50 + volume + RSI) PNG di workspace/grafik/ dari data tersimpan. hari = jumlah hari terakhir (default 180).", {"kode": str, "hari": int})
    @guard
    async def grafik_saham(args):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        kode = store.norm_kode(args["kode"])
        df, _ = _usable(kode)
        n = max(30, min(int(args.get("hari") or 180), 1000))
        c = df["close"]
        view = df.iloc[-n:]
        fig, ax = plt.subplots(3, 1, figsize=(10, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1, 1]})
        ax[0].plot(view.index, view["close"], label="Close", color="#1f4e79", lw=1.4)
        for k, col in ((20, "#e07b00"), (50, "#2e8b57")):
            ax[0].plot(view.index, teknikal.sma(c, k).loc[view.index], label=f"SMA{k}", color=col, lw=1)
        ax[0].set_title(f"{kode}: harga s.d. {df.index[-1].date()} (sumber data tersimpan; bukan rekomendasi)")
        ax[0].legend(loc="upper left")
        ax[0].grid(alpha=.3)
        if df["volume"].notna().any():
            ax[1].bar(view.index, view["volume"], color="#888888", width=1.0)
        ax[1].set_ylabel("Volume")
        r = teknikal.rsi(c).loc[view.index]
        ax[2].plot(view.index, r, color="#7030a0", lw=1)
        for y in (30, 70):
            ax[2].axhline(y, color="#aa0000", ls="--", lw=.7)
        ax[2].set_ylabel("RSI14")
        ax[2].set_ylim(0, 100)
        fig.tight_layout()
        out = workdir / "grafik"
        out.mkdir(exist_ok=True)
        path = out / f"saham_{kode.replace('^', '')}_{now():%Y%m%d}.png"
        fig.savefig(path, dpi=110)
        plt.close(fig)
        return ok(f"Grafik tersimpan: {path.relative_to(workdir)}")

    @tool("profil_investor", "Tampilkan profil investor (horizon, toleransi risiko, modal, batas rugi per transaksi, preferensi, posisi). Bila kosong: tanyakan ke pengguna sebelum memberi rekomendasi.", {})
    @guard
    async def profil_investor(args):
        return ok(profil.render(profil.load()))

    @tool("simpan_profil_investor",
          "Simpan profil investor atas permintaan pengguna: horizon (pendek|menengah|panjang), toleransi_risiko (konservatif|moderat|agresif), modal (Rupiah), risiko_persen (rugi maks per transaksi, % modal, <=5), "
          "preferensi (daftar, mis. dividen, syariah, LQ45), posisi (teks: saham yang sedang dipegang dan harga beli). Minta izin pengguna.",
          {"horizon": str, "toleransi_risiko": str, "modal": float, "risiko_persen": float, "preferensi": list, "posisi": str})
    @guard
    async def simpan_profil_investor(args):
        p = profil.validate(args.get("horizon", ""), args.get("toleransi_risiko", ""), args.get("modal", 0), args.get("risiko_persen", 0), args.get("preferensi") or [], args.get("posisi", ""))
        profil.save(p)
        return ok("Profil investor tersimpan.\n" + profil.render(p))

    return [impor_data_saham, daftar_data_saham, periksa_data_saham, analisis_teknikal, rencana_trading, bandingkan_saham, grafik_saham, profil_investor, simpan_profil_investor]
