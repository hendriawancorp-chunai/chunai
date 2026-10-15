"""Antarmuka terminal ChunAI dengan alur persetujuan."""
from __future__ import annotations

import asyncio
import sys

from .agent import ChunAI
from .approval import ApprovalRequest, ApprovalResult
from .config import load_web_config


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
    async with ChunAI(reviewer=cli_reviewer, web=load_web_config()) as bot:
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


async def login(url: str) -> None:
    """Login MANUAL: buka browser berlayar, Anda login sendiri, sesi tersimpan di profil lokal."""
    from playwright.async_api import async_playwright

    from .browser import find_chromium
    cfg = load_web_config()
    async with async_playwright() as pw:
        ctx = await pw.chromium.launch_persistent_context(cfg.profile_dir, headless=False,
                                                          executable_path=find_chromium())
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        await page.goto(url)
        print("Silakan login di jendela browser. Setelah selesai, tekan Enter di sini.")
        await asyncio.get_running_loop().run_in_executor(None, input)
        await ctx.close()
    print(f"Sesi tersimpan di {cfg.profile_dir}. Jalankan: CHUNAI_BROWSER=profile chunai")


def main() -> None:
    try:
        if len(sys.argv) >= 3 and sys.argv[1] == "login":
            asyncio.run(login(sys.argv[2]))
            return
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
