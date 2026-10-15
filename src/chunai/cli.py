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


USAGE = """ChunAI
  chunai                       chat di terminal
  chunai web [host] [port]     antarmuka Web (default 127.0.0.1:8787; token dari CHUNAI_WEB_TOKEN)
  chunai telegram              bot Telegram (CHUNAI_TELEGRAM_TOKEN, CHUNAI_TELEGRAM_USERS)
  chunai serve                 Web + Telegram sekaligus
  chunai login <url>           login manual untuk Web Agent (komputer lokal)"""


async def run_telegram() -> None:
    import os

    from .interfaces.core import SessionManager, default_agent_factory
    from .interfaces.telegram import TelegramBot, allowed_ids_from_env
    token = os.environ.get("CHUNAI_TELEGRAM_TOKEN")
    if not token:
        sys.exit("CHUNAI_TELEGRAM_TOKEN belum diatur (buat bot lewat @BotFather).")
    ids = allowed_ids_from_env()
    if not ids:
        sys.exit("CHUNAI_TELEGRAM_USERS belum diatur. Kirim /id ke bot untuk mengetahui ID Anda, lalu isi variabel ini.")
    mgr = SessionManager(default_agent_factory())
    bot = TelegramBot(token, ids, mgr)
    try:
        await bot.run()
    finally:
        await mgr.close_all()


async def run_serve() -> None:
    import os
    import secrets

    import uvicorn

    from .interfaces.core import SessionManager, default_agent_factory
    from .interfaces.telegram import TelegramBot, allowed_ids_from_env
    from .interfaces.web import create_app
    mgr = SessionManager(default_agent_factory())
    token = os.environ.get("CHUNAI_WEB_TOKEN") or secrets.token_urlsafe(24)
    app = create_app(mgr, token)
    host, port = os.environ.get("CHUNAI_HOST", "127.0.0.1"), int(os.environ.get("CHUNAI_PORT", "8787"))
    print(f"ChunAI Web: http://{host}:{port}  | token: {token}")
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    tasks = [asyncio.create_task(server.serve())]
    tg, ids = os.environ.get("CHUNAI_TELEGRAM_TOKEN"), allowed_ids_from_env()
    if tg and ids:
        tasks.append(asyncio.create_task(TelegramBot(tg, ids, mgr).run()))
        print("Telegram aktif.")
    await asyncio.gather(*tasks)


def main() -> None:
    try:
        arg = sys.argv[1] if len(sys.argv) > 1 else ""
        if arg == "login" and len(sys.argv) >= 3:
            asyncio.run(login(sys.argv[2]))
            return
        if arg == "web":
            from .interfaces.web import serve
            serve(*(([sys.argv[2]] + ([int(sys.argv[3])] if len(sys.argv) > 3 else [])) if len(sys.argv) > 2 else []))
            return
        if arg == "telegram":
            asyncio.run(run_telegram())
            return
        if arg == "serve":
            asyncio.run(run_serve())
            return
        if arg in ("-h", "--help", "help"):
            print(USAGE)
            return
        asyncio.run(run())
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
