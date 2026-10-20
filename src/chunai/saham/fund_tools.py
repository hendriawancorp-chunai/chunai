"""Tool MCP fundamental dan valuasi: catat (dengan verifikasi angka terhadap halaman sumber), impor tabel, analisis, valuasi."""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
from claude_agent_sdk import tool

from .. import data as D
from .. import docread as R
from ..resources import run_heavy
from . import fundamental as F
from . import store
from .store import SahamError


def parse_printed(s: str) -> float:
    """Angka sebagaimana tercetak di laporan: '1.234.567', '(1,234)', '12,5', '-3.5' -> float (kurung = negatif)."""
    t = str(s).strip().replace(" ", "")
    neg = t.startswith("(") and t.endswith(")") or t.startswith("-")
    t = re.sub(r"[()\-+]", "", t)
    if not re.fullmatch(r"\d[\d.,]*", t):
        raise SahamError(f"teks_angka '{s}' tidak berbentuk angka.")
    if re.fullmatch(r"\d{1,3}([.,]\d{3})+", t):
        v = float(re.sub(r"[.,]", "", t))
    elif "." in t and "," in t:
        v = float(t.replace(".", "").replace(",", ".")) if t.rfind(",") > t.rfind(".") else float(t.replace(",", ""))
    elif "," in t:
        v = float(t.replace(",", "."))
    else:
        v = float(t)
    return -v if neg else v


def printed_on_page(doc: R.Doc, page: int, teks: str) -> bool:
    if not 1 <= page <= doc.n:
        return False
    body = re.sub(r"\s+", "", doc.pages[page - 1])
    t = re.sub(r"\s+", "", str(teks))
    return t in body or t.strip("()") in body


def fundamental_tools(workdir: Path, reg: list[str] | None = None):
    workdir = workdir.resolve()
    cache = workdir / ".cache"

    def ok(t):
        if reg is not None:
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

    @tool("catat_fundamental",
          "Catat angka laporan keuangan dari dokumen sumber (PDF di workspace) DENGAN BUKTI. kode; periode ('2025-FY', '2026-6M', ... kumulatif); satuan angka di laporan ('rupiah'|'ribu'|'juta'|'miliar'|'triliun'; "
          "jumlah_saham dalam lembar, dividen_per_saham dalam Rp/lembar tidak dikalikan satuan); butir = [{field, nilai, teks_angka, berkas, halaman}] dengan field salah satu dari: pendapatan, laba_kotor, laba_usaha, "
          "laba_bersih (atribusi pemilik induk), total_aset, total_liabilitas, ekuitas (atribusi pemilik induk), utang_berbunga, kas, arus_kas_operasi, capex, beban_bunga, ebitda, jumlah_saham, dividen_per_saham. "
          "nilai = angka seperti tercetak (tanpa satuan, negatif bila kurung), teks_angka = teks persis di halaman (mis. '4.961.000'). Tool MEMVERIFIKASI teks_angka ada di halaman itu dan cocok dengan nilai; "
          "yang gagal ditolak.", {"kode": str, "periode": str, "satuan": str, "butir": list})
    @guard
    async def catat_fundamental(args):
        kode, periode, satuan = store.norm_kode(args["kode"]), F.check_periode(args.get("periode", "")), str(args.get("satuan", "")).strip().lower()
        if satuan not in F.SATUAN:
            raise SahamError(f"satuan harus salah satu dari {', '.join(F.SATUAN)} (sesuai keterangan di laporan, mis. 'Dalam jutaan Rupiah').")
        items = args.get("butir")
        if not isinstance(items, list) or not items:
            raise SahamError("'butir' harus daftar [{field, nilai, teks_angka, berkas, halaman}].")
        accepted, rejected, per_src = {}, [], {}
        for it in items[:60]:
            try:
                f = str(it["field"]).strip()
                if f not in F.FIELDS:
                    raise SahamError(f"field '{f}' tidak dikenal")
                doc = await run_heavy(R.load, D.resolve_in(workdir, str(it["berkas"])), cache)
                page = int(it["halaman"])
                if not printed_on_page(doc, page, it["teks_angka"]):
                    raise SahamError(f"teks '{it['teks_angka']}' TIDAK ditemukan di {doc.unit} {page} {doc.name}")
                printed = parse_printed(it["teks_angka"])
                val = float(it["nilai"])
                if abs(abs(printed) - abs(val)) > 1e-6 * max(1.0, abs(val)):
                    raise SahamError(f"nilai {val:g} tidak cocok dengan teks_angka '{it['teks_angka']}' ({printed:g})")
                if f == "capex":
                    val = abs(val)
                accepted[f] = F.to_rupiah(f, val, satuan)
                per_src[f] = {"sumber": f"{doc.name} hlm {page}", "halaman": page, "teks": str(it["teks_angka"])[:30]}
            except (SahamError, R.DocReadError, ValueError, KeyError, OSError) as e:
                rejected.append(f"- {it.get('field') if isinstance(it, dict) else '?'}: {e}")
        for f, rec in per_src.items():
            F.set_fields(kode, periode, {f: accepted[f]}, rec["sumber"], rec["halaman"], {f: {"teks": rec["teks"], "satuan_asli": satuan}})
        rec_issues = F.reconcile({periode: F.load(kode)[periode]}) if accepted else []
        msg = f"{len(accepted)} butir TERVERIFIKASI dan tersimpan untuk {kode} {periode}: {', '.join(accepted)}."
        if rejected:
            msg += f"\n{len(rejected)} butir DITOLAK (tidak terbukti di halaman/angka tidak cocok):\n" + "\n".join(rejected)
        if rec_issues:
            msg += "\n⚠ rekonsiliasi: " + "; ".join(rec_issues)
        return ok(msg)

    @tool("impor_fundamental",
          "Impor laporan keuangan dari tabel (XLSX/CSV) di workspace: baris dengan label (Pendapatan, Laba Bersih, Jumlah Aset, Jumlah Liabilitas, Ekuitas, ...) dipetakan otomatis. kode; periode; satuan; "
          "sumber (WAJIB, mis. 'idx.co.id laporan keuangan 2025'); kolom (opsional) = teks header kolom periode yang dipakai (mis. '2025'); default kolom angka pertama. Melaporkan baris terpetakan dan tidak terpetakan.",
          {"path": str, "kode": str, "periode": str, "satuan": str, "sumber": str, "kolom": str})
    @guard
    async def impor_fundamental(args):
        sumber = str(args.get("sumber", "")).strip()
        if not sumber:
            raise SahamError("'sumber' wajib.")
        kode, periode, satuan = store.norm_kode(args["kode"]), F.check_periode(args.get("periode", "")), str(args.get("satuan", "")).strip().lower()
        if satuan not in F.SATUAN:
            raise SahamError(f"satuan harus salah satu dari {', '.join(F.SATUAN)}.")
        src = D.resolve_in(workdir, args["path"])
        if not src.is_file():
            raise SahamError(f"File tidak ditemukan: {args['path']}")
        raw = pd.read_excel(src, header=None, dtype=str) if src.suffix.lower() in (".xlsx", ".xls", ".xlsm") else pd.read_csv(src, header=None, dtype=str, sep=None, engine="python")
        want = str(args.get("kolom") or "").strip().lower()
        col_idx = None
        if want:
            for i in range(min(15, len(raw))):
                for c, v in raw.iloc[i].items():
                    if want in str(v).lower():
                        col_idx = c
                        break
                if col_idx is not None:
                    break
            if col_idx is None:
                raise SahamError(f"kolom '{want}' tidak ditemukan di 15 baris pertama.")
        found, unmapped = {}, 0
        for _, row in raw.iterrows():
            label = next((str(v) for v in row if isinstance(v, str) and re.search(r"[A-Za-z]", v)), "")
            f = F.alias_field(label) if label else None
            if not f:
                unmapped += bool(label)
                continue
            cells = [row[col_idx]] if col_idx is not None else [v for v in row if isinstance(v, str) and re.fullmatch(r"[\s(\-]*\d[\d.,]*\)?\s*", v)]
            if not cells or not isinstance(cells[0], str):
                continue
            try:
                found.setdefault(f, (label, parse_printed(cells[0]), cells[0]))
            except SahamError:
                continue
        if not found:
            raise SahamError("Tidak ada baris yang dikenali (label seperti Pendapatan, Laba Bersih, Jumlah Aset, Jumlah Liabilitas, Ekuitas).")
        vals = {f: F.to_rupiah(f, abs(v) if f == "capex" else v, satuan) for f, (_, v, _) in found.items()}
        F.set_fields(kode, periode, vals, f"{sumber} ({src.name}, diunggah)", None, {f: {"teks": t, "satuan_asli": satuan, "label": lab} for f, (lab, _, t) in found.items()})
        issues = F.reconcile({periode: F.load(kode)[periode]})
        return ok(f"Tersimpan {kode} {periode} dari {src.name}: " + "; ".join(f"{lab} → {f} = {t}" for f, (lab, _, t) in found.items()) + f"\n{unmapped} baris lain tidak terpetakan (diabaikan)." +
                  ("\n⚠ rekonsiliasi: " + "; ".join(issues) if issues else ""))

    def _price(kode):
        try:
            df = store.load_prices(kode)
            return float(df["close"].iloc[-1]), str(df.index[-1].date())
        except SahamError:
            return None, None

    @tool("analisis_fundamental",
          "Analisis fundamental dari data tercatat: tren tahunan (pendapatan, laba, margin, ROE, DER, FCF, CFO/laba), TTM, utang bersih, cakupan bunga, EPS/BVPS dan rasio valuasi (PER, PBV, dividen yield, payout, FCF yield) "
          "pada harga terakhir data harga tersimpan. Menandai rekonsiliasi yang janggal dan laporan yang sudah lama.", {"kode": str})
    @guard
    async def analisis_fundamental(args):
        kode = store.norm_kode(args["kode"])
        h, tgl = _price(kode)
        return ok(F.render(kode, F.analyze(kode, h, tgl)))

    @tool("valuasi_saham",
          "Hitung nilai wajar per saham dengan asumsi EKSPLISIT (tidak ada asumsi tersembunyi). metode: 'dcf' (butuh pertumbuhan_tahap1, tahun_tahap1, pertumbuhan_terminal, diskonto; fcf_dasar default FCF TTM/FY terakhir), "
          "'ddm' (dps_dasar default DPS TTM; param sama) atau 'relatif' (per_pembanding dan/atau pbv_pembanding + sumber_pembanding WAJIB). Angka rasio dalam desimal (12% = 0,12). Menghasilkan nilai dasar, rentang sensitivitas, "
          "margin of safety terhadap harga data tersimpan, dan peringatan. Asumsi harus bisa dipertanggungjawabkan; jelaskan dasarnya ke pengguna.",
          {"kode": str, "metode": str, "pertumbuhan_tahap1": float, "tahun_tahap1": int, "pertumbuhan_terminal": float, "diskonto": float, "fcf_dasar": float, "dps_dasar": float,
           "per_pembanding": float, "pbv_pembanding": float, "sumber_pembanding": str})
    @guard
    async def valuasi_saham(args):
        kode = store.norm_kode(args["kode"])
        h, _ = _price(kode)
        a = F.analyze(kode, h)
        metode = str(args.get("metode", "")).strip().lower()
        if metode in ("dcf", "ddm"):
            for k in ("pertumbuhan_tahap1", "tahun_tahap1", "pertumbuhan_terminal", "diskonto"):
                if args.get(k) in (None, ""):
                    raise SahamError(f"Asumsi '{k}' wajib diberikan (tidak ada nilai bawaan).")
            g1, n, gt, r = float(args["pertumbuhan_tahap1"]), int(args["tahun_tahap1"]), float(args["pertumbuhan_terminal"]), float(args["diskonto"])
        if metode == "dcf":
            fcf0 = args.get("fcf_dasar") or a.get("fcf_ttm")
            if fcf0 is None:
                fy = a["tahunan"][-1] if a["tahunan"] else {}
                fcf0 = fy.get("fcf")
            if fcf0 is None:
                raise SahamError("FCF dasar tidak tersedia (butuh arus_kas_operasi dan capex) atau berikan fcf_dasar.")
            if not a.get("jumlah_saham"):
                raise SahamError("jumlah_saham belum tercatat.")
            v = F.valuasi_dcf(float(fcf0), g1, n, gt, r, a["jumlah_saham"], h)
        elif metode == "ddm":
            dps0 = args.get("dps_dasar") or a["ttm"].get("dividen_per_saham")
            if not dps0:
                raise SahamError("DPS dasar tidak tersedia: catat dividen_per_saham atau berikan dps_dasar.")
            v = F.valuasi_ddm(float(dps0), g1, n, gt, r, h)
        elif metode == "relatif":
            if not str(args.get("sumber_pembanding", "")).strip():
                raise SahamError("'sumber_pembanding' wajib (dari mana PER/PBV pembanding, tanggalnya).")
            v = F.valuasi_relatif(a.get("eps_ttm"), a.get("bvps"), args.get("per_pembanding"), args.get("pbv_pembanding"), h)
            v["sumber_pembanding"] = args["sumber_pembanding"]
        else:
            raise SahamError("metode harus 'dcf', 'ddm', atau 'relatif'.")
        return ok(F.render_valuasi(kode, v) + (f"\nSumber pembanding: {v['sumber_pembanding']}" if v.get("sumber_pembanding") else ""))

    return [catat_fundamental, impor_fundamental, analisis_fundamental, valuasi_saham]
