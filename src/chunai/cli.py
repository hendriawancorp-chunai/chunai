"""Antarmuka terminal ChunAI dengan alur persetujuan."""
from __future__ import annotations

import asyncio
import sys

from .agent import ChunAI
from .approval import ApprovalRequest, ApprovalResult


async def cli_reviewer(req: ApprovalRequest) -> ApprovalResult:
    print("\n" + "=" * 60)
    print(f"🔒 PERMINTAAN IZIN  →  {req.tool}")
    print(req.summary)
    print("=" * 60)
    loop = asyncio.get_running_loop()
    ans = await loop.run_in_executor(None, input, "Izinkan? [y]a / [t]olak / [s]elalu (sesi ini): ")
    ans = ans.strip().lower()
    if ans in ("y", "ya"):
        return ApprovalResult(True)
    if ans in ("s", "selalu"):
        return ApprovalResult(True, note="always")
    reason = await loop.run_in_executor(None, input, "Alasan/arahan (opsional): ")
    return ApprovalResult(False, reason.strip() or "Ditolak oleh pengguna.")


async def run() -> None:
    async with ChunAI(reviewer=cli_reviewer) as bot:
        print("ChunAI siap. Ketik 'keluar' untuk berhenti.\n")
        while True:
            try:
                text = await asyncio.get_running_loop().run_in_executor(None, input, "Anda › ")
            except EOFError:
                break
            if text.strip().lower() in ("keluar", "exit", "quit"):
                break
            if not text.strip():
                continue
            async for chunk in bot.ask(text):
                print(chunk, end="", flush=True)
            print()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
