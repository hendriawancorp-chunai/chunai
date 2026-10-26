"""Ukur beban awal (token masukan sebelum pengguna mengetik apa pun): `chunai ukur`. Memakai satu pesan "halo" pada Haiku per varian."""
from __future__ import annotations

import dataclasses
import tempfile
from pathlib import Path

VARIANTS = [
    ("penuh (seperti dipakai ChunAI)", {}),
    ("tanpa pengaturan pengguna (setting_sources=[])", {"setting_sources": []}),
    ("prompt ChunAI diganti pendek", {"system_prompt": "Jawab singkat."}),
]


def format_report(rows: list[tuple[str, int]]) -> str:
    base = rows[0][1] if rows else 0
    out = ["Beban awal = token masukan untuk pesan 'halo' (sebelum Anda mengetik apa pun):"]
    for name, tot in rows:
        diff = "" if tot == base else f"  ({tot - base:+d} dari penuh)"
        out.append(f"  {tot:7d}  {name}{diff}")
    if len(rows) >= 3:
        out.append(f"\nBagian prompt ChunAI sendiri: sekitar {rows[0][1] - rows[2][1]} token. "
                   f"Pengaturan/skill pengguna di komputer ini: sekitar {rows[0][1] - rows[1][1]} token.")
    return "\n".join(out)


async def measure_variant(over: dict) -> int:
    from claude_agent_sdk import ClaudeSDKClient, ResultMessage

    from .agent import ChunAI
    from .approval import ApprovalResult

    async def deny(_req):
        return ApprovalResult(False, "pengukuran")

    with tempfile.TemporaryDirectory() as d:
        a = ChunAI(deny, workdir=Path(d) / "ws", audit_path=Path(d) / "audit.jsonl", model="claude-haiku-5-5", max_budget_usd=None)
        opts = dataclasses.replace(a._options(), **over)
        async with ClaudeSDKClient(opts) as c:
            await c.query("halo")
            async for m in c.receive_response():
                if isinstance(m, ResultMessage):
                    u = m.usage or {}
                    return sum(int(u.get(k) or 0) for k in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens"))
    return 0


async def run_measure() -> str:
    rows = [(name, await measure_variant(over)) for name, over in VARIANTS]
    return format_report(rows)
