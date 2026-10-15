"""Tool kustom ChunAI (MCP in-process)."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import data as D
from .report import lint_report


def build_server(workdir: Path):
    workdir = workdir.resolve()

    @tool("periksa_laporan",
          "Periksa laporan riset (file markdown di workspace): sitasi, daftar sumber, catatan keterbatasan. "
          "Wajib dipanggil sebelum menyerahkan laporan riset.",
          {"path": str})
    async def periksa_laporan(args):
        p = (workdir / args["path"]).resolve()
        if workdir not in p.parents and p != workdir:
            return {"content": [{"type": "text", "text": "Path di luar workspace ditolak."}], "is_error": True}
        if not p.is_file():
            return {"content": [{"type": "text", "text": f"File tidak ditemukan: {args['path']}"}], "is_error": True}
        issues = lint_report(p.read_text(encoding="utf-8"))
        text = "LOLOS: laporan memenuhi standar sitasi." if not issues else \
            "PERLU PERBAIKAN:\n- " + "\n- ".join(issues)
        return {"content": [{"type": "text", "text": text}]}

    def _ok(text):
        return {"content": [{"type": "text", "text": text}]}

    def _err(text):
        return {"content": [{"type": "text", "text": text}], "is_error": True}

    @tool("profil_data",
          "Baca tabel (csv/tsv/xlsx) di workspace dan tampilkan profilnya: ukuran, tipe, nilai kosong, "
          "ringkasan numerik, duplikat. Jalankan SEBELUM menganalisis.",
          {"path": str})
    async def profil_data(args):
        try:
            return _ok(D.profile(D.load_table(D.resolve_in(workdir, args["path"]))))
        except (ValueError, FileNotFoundError) as e:
            return _err(str(e))

    @tool("buat_grafik",
          "Buat grafik PNG dari tabel di workspace. kind: bar|line|scatter|hist. Disimpan di folder 'grafik/'. "
          "Judul harus menyatakan temuan (bukan sekadar nama kolom).",
          {"path": str, "kind": str, "x": str, "y": str, "title": str, "name": str})
    async def buat_grafik(args):
        try:
            df = D.load_table(D.resolve_in(workdir, args["path"]))
            out = D.make_chart(df, workdir / "grafik", args["kind"], args.get("x") or None,
                               args.get("y") or None, args.get("title", ""), args.get("name", "grafik"))
            return _ok(f"Grafik tersimpan: {out.relative_to(workdir)}")
        except (ValueError, FileNotFoundError) as e:
            return _err(str(e))

    return create_sdk_mcp_server("chunai", tools=[periksa_laporan, profil_data, buat_grafik])
