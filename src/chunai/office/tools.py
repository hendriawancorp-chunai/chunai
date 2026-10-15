"""Tool MCP untuk dokumen & presentasi."""
from __future__ import annotations

import itertools
import json
import re
from pathlib import Path

from claude_agent_sdk import tool

from .. import data as D
from .deckbuild import build_pptx
from .docbuild import build_docx
from .doccheck import lint_doc_spec
from .render import to_pdf, to_pngs
from .theme import load_theme


def contact_sheet(pngs: list[Path], out: Path, cols: int = 2) -> Path:
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in pngs]
    w, h = max(i.width for i in ims), max(i.height for i in ims)
    rows = -(-len(ims) // cols)
    sheet = Image.new("RGB", (w * cols + 10 * (cols - 1), h * rows + 10 * (rows - 1)), "#888888")
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % cols) * (w + 10), (k // cols) * (h + 10)))
    if sheet.width > 2400:
        sheet = sheet.resize((2400, int(sheet.height * 2400 / sheet.width)))
    sheet.save(out)
    return out


def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    for i in itertools.count(2):
        p = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not p.exists():
            return p


def _name(n: str, default: str) -> str:
    return re.sub(r"[^\w-]", "_", n or default)[:50] or default


def office_tools(workdir: Path, themes_dir: str = "data/themes"):
    workdir = workdir.resolve()
    out = workdir / "output"

    def ok(t): return {"content": [{"type": "text", "text": t}]}
    def err(t): return {"content": [{"type": "text", "text": t}], "is_error": True}

    @tool("buat_dokumen",
          "Susun DOCX bergaya artikel/kajian dari spesifikasi JSON: cover, title/author/affiliation, footer, "
          "blocks [{h:0|1|2|3,text}|{p}|{bullets}|{numbered}|{table:{caption,header,rows,widths}}|{figure:{path,caption}}], "
          "references[] (APA). Sitasi dalam teks '(Penulis, 2026)'. Tema opsional. Hasil di folder output/; juga PDF bila pdf=true.",
          {"spec": dict, "name": str, "theme": str, "pdf": bool})
    async def buat_dokumen(args):
        try:
            spec = args["spec"]
            theme = load_theme(args.get("theme") or None, themes_dir)
            path = _unique(out / f"{_name(args.get('name'), 'kajian')}.docx")
            build_docx(spec, path, theme, workdir)
            path.with_suffix(".spec.json").write_text(json.dumps(spec, ensure_ascii=False, indent=1), encoding="utf-8")
            msgs = [f"Dokumen tersimpan: {path.relative_to(workdir)}"]
            if args.get("pdf"):
                msgs.append(f"PDF: {to_pdf(path, out).relative_to(workdir)}")
            issues = lint_doc_spec(spec)
            msgs.append("Pemeriksaan sitasi: LOLOS" if not issues else "Pemeriksaan sitasi PERLU PERBAIKAN:\n- " + "\n- ".join(issues))
            return ok("\n".join(msgs))
        except Exception as e:
            return err(f"Gagal membuat dokumen: {type(e).__name__}: {e}")

    @tool("buat_presentasi",
          "Susun PPTX 16:9 dari spesifikasi JSON {slides:[...]}. kind: cover|ringkasan|kolom|tabel|grafik|proses|teks|penutup. "
          "Judul slide = topik; 'subtitle' = KALIMAT PESAN. Chart native dapat diedit. Hasil di output/.",
          {"spec": dict, "name": str, "theme": str})
    async def buat_presentasi(args):
        try:
            theme = load_theme(args.get("theme") or None, themes_dir)
            path = _unique(out / f"{_name(args.get('name'), 'presentasi')}.pptx")
            _, warns = build_pptx(args["spec"], path, theme, workdir)
            path.with_suffix(".spec.json").write_text(json.dumps(args["spec"], ensure_ascii=False, indent=1), encoding="utf-8")
            msg = f"Presentasi tersimpan: {path.relative_to(workdir)} ({len(args['spec'].get('slides', []))} slide)"
            if warns:
                msg += "\nPeringatan layout:\n- " + "\n- ".join(warns)
            return ok(msg)
        except Exception as e:
            return err(f"Gagal membuat presentasi: {type(e).__name__}: {e}")

    @tool("periksa_dokumen", "Periksa spesifikasi dokumen (JSON) untuk sitasi/daftar pustaka/caption sebelum dibuat.",
          {"spec": dict})
    async def periksa_dokumen(args):
        issues = lint_doc_spec(args["spec"])
        return ok("LOLOS" if not issues else "PERLU PERBAIKAN:\n- " + "\n- ".join(issues))

    @tool("pratinjau_file",
          "Render DOCX/PPTX/PDF di workspace menjadi gambar PNG (folder pratinjau/) agar bisa diperiksa secara visual. "
          "Lihat gambarnya dengan Read, perbaiki bila ada teks terpotong/tumpang tindih.",
          {"path": str, "dpi": int})
    async def pratinjau_file(args):
        try:
            src = D.resolve_in(workdir, args["path"])
            if not src.is_file():
                return err(f"File tidak ditemukan: {args['path']}")
            pdf = src if src.suffix.lower() == ".pdf" else to_pdf(src, workdir / "pratinjau")
            pngs = to_pngs(pdf, workdir / "pratinjau", dpi=int(args.get("dpi") or 60))
            msg = "Gambar pratinjau:\n" + "\n".join(str(p.relative_to(workdir)) for p in pngs)
            if len(pngs) > 1:
                sheet = contact_sheet(pngs, workdir / "pratinjau" / f"{src.stem}_semua.png")
                msg = f"LIHAT INI DULU (semua halaman/slide dalam satu gambar): {sheet.relative_to(workdir)}\n" + msg
            return ok(msg)
        except Exception as e:
            return err(f"Gagal pratinjau: {type(e).__name__}: {e}")

    return [buat_dokumen, buat_presentasi, periksa_dokumen, pratinjau_file]
