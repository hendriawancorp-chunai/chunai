"""Tool kustom ChunAI (MCP in-process)."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

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

    return create_sdk_mcp_server("chunai", tools=[periksa_laporan])
