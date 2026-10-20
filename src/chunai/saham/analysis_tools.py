"""Tool MCP skill saham tahap lanjut: pemeriksa kualitas analisis, penyaringan, rekam jejak, watchlist."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import tool

from .. import data as D
from .. import docread as R
from ..resources import run_heavy
from . import lint, profil, screen, store, track
from .store import SahamError


def analysis_tools(workdir: Path, reg: list[str]):
    workdir = workdir.resolve()
    cache = workdir / ".cache"

    def ok(t):
        reg.append(t)
        return {"content": [{"type": "text", "text": t}]}

    def err(t): return {"content": [{"type": "text", "text": t}], "is_error": True}

    def guard(fn):
        async def inner(args):
            try:
                return await fn(args)
            except (SahamError, R.DocReadError, ValueError, OSError, KeyError) as e:
                return err(str(e))
            except Exception as e:
                return err(f"Gagal: {type(e).__name__}: {str(e)[:200]}")
        return inner

    @tool("periksa_analisis",
          "Gerbang kualitas laporan analisis saham (WAJIB sebelum menyerahkan). path = laporan di workspace (.md/.txt/.docx/.pptx). Memeriksa: pernyataan bukan nasihat keuangan, tanggal data, sumber, risiko, keterbatasan, "
          "skenario pesimis dan syarat pembatalan bila ada rekomendasi, asumsi bila ada klaim valuasi, larangan kata kepastian, dan penelusuran angka ke keluaran tool sesi ini. Perbaiki sampai LOLOS.", {"path": str})
    @guard
    async def periksa_analisis(args):
        p = D.resolve_in(workdir, args["path"])
        if not p.is_file():
            raise SahamError(f"File tidak ditemukan: {args['path']}")
        if p.suffix.lower() in (".md", ".txt"):
            text = p.read_text(encoding="utf-8", errors="replace")
        else:
            doc = await run_heavy(R.load, p, cache)
            text = "\n".join(doc.pages)
        res = lint.lint_report(text, lint.registry_values(reg))
        return {"content": [{"type": "text", "text": lint.render(res)}]}

    @tool("saring_saham",
          "Saring dan beri skor saham yang datanya tersimpan (kualitas, valuasi, momentum, risiko; bobot mengikuti profil investor). kodes (opsional; default semua saham tersimpan). filter (opsional): min_nilai_transaksi (Rp/hari), "
          "per_maks, pbv_maks, roe_min, der_maks, dividen_yield_min, rsi_maks, rsi_min, return_3b_min (desimal), tren_naik (bool). Skor berbasis ambang tetap dan transparan; faktor tanpa data dilewati. Penyaring kandidat, bukan rekomendasi.",
          {"kodes": list, "filter": dict})
    @guard
    async def saring_saham(args):
        codes = [store.norm_kode(k) for k in (args.get("kodes") or [])] or [k for k in store.list_codes() if not k.startswith("^")]
        if not codes:
            raise SahamError("Belum ada data saham tersimpan.")
        p = profil.load()
        res = screen.screen(codes, p.get("horizon", "menengah"), p.get("toleransi_risiko", "moderat"), "dividen" in [x.lower() for x in p.get("preferensi", [])], args.get("filter") or {})
        head = "" if p else "Catatan: profil investor belum diisi; memakai bobot bawaan (horizon menengah, toleransi moderat).\n"
        return ok(head + screen.render(res, p.get("horizon", "menengah"), p.get("toleransi_risiko", "moderat")))

    @tool("catat_rekomendasi",
          "Catat rekomendasi/pandangan ke rekam jejak (untuk dievaluasi nanti). kode, aksi (beli|beli_bertahap|tahan|kurangi|jual|pantau|hindari), tesis (alasan singkat), keyakinan (tinggi|sedang|rendah), "
          "pembatalan (harga), target (harga), horizon. Harga referensi otomatis dari data tersimpan terakhir. Catat HANYA setelah pengguna menerima pandangan itu.",
          {"kode": str, "aksi": str, "tesis": str, "keyakinan": str, "pembatalan": float, "target": float, "horizon": str})
    @guard
    async def catat_rekomendasi(args):
        r = track.catat(args["kode"], args.get("aksi", ""), args.get("tesis", ""), args.get("keyakinan", ""), None, None, args.get("pembatalan") or None, args.get("target") or None, args.get("horizon", ""))
        return ok(f"Tercatat [{r['id']}]: {r['aksi']} {r['kode']} @ {r['harga_ref']:,.0f} ({r['tanggal_ref']}), keyakinan {r['keyakinan']}, pembatalan {r['pembatalan']}, target {r['target']}.".replace(",", "."))

    @tool("evaluasi_rekam_jejak", "Evaluasi semua rekomendasi tercatat terhadap data harga tersimpan (return, target/pembatalan, relatif indeks bila benchmark tersimpan, ketepatan per keyakinan). benchmark opsional (mis. '^JKSE').", {"benchmark": str})
    @guard
    async def evaluasi_rekam_jejak(args):
        recs = track.load_recs()
        if not recs:
            return ok("(belum ada rekomendasi tercatat)")
        bench = store.load_prices(args["benchmark"])["close"] if args.get("benchmark") else None
        evals = []
        for r in recs:
            try:
                evals.append(track.evaluate(r, bench))
            except SahamError as e:
                evals.append({"id": r["id"], "status": str(e)})
        return ok(track.summarize(evals))

    @tool("watchlist_atur", "Tambah/ubah/hapus saham di watchlist. kode; catatan; alert_atas dan alert_bawah (harga); hapus=true untuk menghapus.", {"kode": str, "catatan": str, "alert_atas": float, "alert_bawah": float, "hapus": bool})
    @guard
    async def watchlist_atur(args):
        kode = store.norm_kode(args["kode"])
        wl = track.load_wl()
        if args.get("hapus"):
            wl.pop(kode, None)
        else:
            it = wl.setdefault(kode, {})
            for k in ("catatan", "alert_atas", "alert_bawah"):
                if args.get(k) not in (None, "", 0):
                    it[k] = args[k]
            if len(wl) > 40:
                raise SahamError("Watchlist maksimal 40 saham.")
        track.save_wl(wl)
        return ok(f"Watchlist: {', '.join(sorted(wl)) or '(kosong)'}")

    @tool("periksa_watchlist", "Periksa watchlist dari data harga TERSIMPAN: harga, perubahan, tren, penembusan level alert, RSI ekstrem, lonjakan volume, dan data yang tidak segar. Tidak mengambil data baru "
          "(untuk pemantauan terjadwal, data harus diperbarui lebih dulu lewat unggahan/unduhan). Hanya membaca.", {})
    @guard
    async def periksa_watchlist(args):
        return ok(track.check_watchlist())

    return [periksa_analisis, saring_saham, catat_rekomendasi, evaluasi_rekam_jejak, watchlist_atur, periksa_watchlist]
