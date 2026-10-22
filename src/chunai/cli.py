"""Antarmuka terminal ChunAI dengan alur persetujuan."""
from __future__ import annotations

import asyncio
import os
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
        from pathlib import Path
        Path(cfg.state_file).parent.mkdir(parents=True, exist_ok=True)
        state = await ctx.storage_state(path=cfg.state_file)          # termasuk cookie SESI yang akan hilang saat browser ditutup
        if os.name == "posix":
            os.chmod(cfg.state_file, 0o600)
        await ctx.close()
    print(f"Sesi login tersimpan ({len(state.get('cookies', []))} cookie) di {cfg.state_file} dan profil {cfg.profile_dir}.\n"
          "Berkas itu setara kata sandi: jangan dibagikan. Jalankan: CHUNAI_BROWSER=profile chunai")


USAGE = """ChunAI
  chunai                       chat di terminal
  chunai web [host] [port]     antarmuka Web (default 127.0.0.1:8787; token dari CHUNAI_WEB_TOKEN)
  chunai telegram              bot Telegram (CHUNAI_TELEGRAM_TOKEN, CHUNAI_TELEGRAM_USERS)
  chunai audit [n]             tampilkan n catatan terakhir (perintah, izin, keputusan, biaya)\n  chunai doctor                periksa semua prasyarat (Python, Claude, Chromium, LibreOffice, ...)
  chunai auth                  login Claude; token disimpan otomatis ke .env
  chunai setup-telegram        hubungkan bot Telegram (token divalidasi, ID pemilik terdeteksi otomatis)\n  chunai telegram-check        periksa token/ID/webhook Telegram (tanpa menjalankan bot)
  chunai serve                 Web + Telegram sekaligus
  chunai login <url>           login manual untuk Web Agent (komputer lokal)\n  chunai cdp-help              panduan + pemeriksaan memakai Chrome sendiri (CDP)"""


async def run_telegram() -> None:
    import logging
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)      # httpx mencetak URL berisi token pada level INFO

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
    sched = asyncio.create_task(_make_scheduler(mgr, bot, ids).run())
    try:
        await bot.run()
    finally:
        sched.cancel()
        await mgr.close_all()


async def run_telegram_check() -> None:
    import os

    import httpx

    from .interfaces.core import SessionManager
    from .interfaces.telegram import TelegramBot, allowed_ids_from_env
    token = os.environ.get("CHUNAI_TELEGRAM_TOKEN")
    ids = allowed_ids_from_env()
    print(f"CHUNAI_TELEGRAM_TOKEN : {'terpasang' if token else 'BELUM diatur'}")
    print(f"CHUNAI_TELEGRAM_USERS : {sorted(ids) if ids else 'BELUM diatur'}")
    if not token or not ids:
        sys.exit(1)
    bot = TelegramBot(token, ids, SessionManager(lambda r, w: None))
    try:
        info = await bot.check()
    except httpx.HTTPError as e:
        sys.exit(f"Tidak bisa menjangkau Telegram: {type(e).__name__}. Periksa jaringan/allowlist domain api.telegram.org.")
    except Exception as e:
        sys.exit(f"Gagal: {str(e).replace(token, '***')}")
    print(f"Bot                   : @{info['username']} (id {info['id']})")
    print(f"Webhook               : {info['webhook_url'] or 'tidak ada (baik)'}")
    print(f"Update tertunda       : {info['pending_updates']}")
    print("OK. Jalankan: chunai telegram")


def _make_scheduler(mgr, bot, ids):
    from .interfaces.scheduler import Scheduler
    from .interfaces.telegram import TelegramChannel
    return Scheduler(mgr, channels=lambda: [TelegramChannel(bot, i) for i in sorted(ids)])


async def run_serve() -> None:
    import logging
    import os
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    import uvicorn

    from .interfaces.core import SessionManager, default_agent_factory
    from .interfaces.telegram import TelegramBot, allowed_ids_from_env
    from .interfaces.web import LOOPBACK, auth_off_requested, create_app, resolve_token
    mgr = SessionManager(default_agent_factory())
    host, port = os.environ.get("CHUNAI_HOST", "127.0.0.1"), int(os.environ.get("CHUNAI_PORT", "8787"))
    off = auth_off_requested()
    if off and host not in LOOPBACK:
        sys.exit("CHUNAI_WEB_AUTH=off hanya boleh dengan alamat 127.0.0.1/localhost. Hapus pengaturan itu atau kembalikan CHUNAI_HOST.")
    token, generated = resolve_token()
    app = create_app(mgr, token, auth_off=off)
    print(f"ChunAI Web: http://{host}:{port}  | " + ("tanpa token (hanya komputer ini)" if off else
          f"token: {token if generated else '(dari CHUNAI_WEB_TOKEN di .env)'}"), flush=True)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level="warning"))
    tasks = [asyncio.create_task(server.serve())]
    tg, ids = os.environ.get("CHUNAI_TELEGRAM_TOKEN"), allowed_ids_from_env()
    if tg and ids:
        bot = TelegramBot(tg, ids, mgr)
        tasks.append(asyncio.create_task(bot.run()))
        print("Telegram aktif.")
        tasks.append(asyncio.create_task(_make_scheduler(mgr, bot, ids).run()))
    await asyncio.gather(*tasks)


def run_auth() -> None:
    from .auth import clear_screen, extract_token, run_setup_token
    from .doctor import claude_cli_path, token_shape
    from .envfile import env_path, save_env_var
    cli = claude_cli_path()
    if not cli:
        sys.exit("Claude CLI bawaan tidak ditemukan. Jalankan: pip install -e .")
    print("Login Claude (butuh langganan Pro/Max).\n"
          "1) Buka tautan yang muncul di browser Anda dan setujui.\n"
          "2) Tempel kode dari browser ke sini lalu Enter.\n"
          "Token akan DISIMPAN OTOMATIS ke .env; Anda tidak perlu menyalinnya.\n")
    code, raw = run_setup_token(cli)
    token = extract_token(raw)
    if token:
        f = save_env_var("CLAUDE_CODE_OAUTH_TOKEN", token, env_path())
        clear_screen()
        print(f"✅ Token tersimpan di {f} ({token_shape(token)}).")
        print("Layar dibersihkan agar token tidak tertinggal. Langkah berikut: chunai doctor --live")
        sys.exit(0)
    if code == 0:
        print("\n⚠ Login selesai tetapi token tidak terbaca otomatis. Cara manual (SATU baris, lalu tempel token dan Enter):\n"
              '  read -rsp "Token: " T; echo; chunai savetoken "$T"; unset T')
    sys.exit(code or 1)


def run_setup_telegram() -> None:
    import getpass

    import httpx

    from .envfile import env_path, save_env_var
    from .setup_telegram import run_setup

    def yes(prompt: str) -> bool:
        return input(prompt).strip().lower() in ("y", "ya", "yes")

    with httpx.Client() as client:
        ok = run_setup(getpass.getpass, yes, print, client, lambda k, v: save_env_var(k, v, env_path()))
    sys.exit(0 if ok else 1)


def run_audit() -> None:
    from pathlib import Path

    from .usage import render_audit
    n = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 30
    print(render_audit(Path("data/sessions"), n))


def run_savetoken() -> None:
    from .doctor import token_shape
    from .envfile import env_path, save_env_var
    tok = (sys.argv[2] if len(sys.argv) > 2 else "").strip().strip("\"'")
    if not tok.startswith("sk-ant-"):
        sys.exit("Token tidak dikenali (harus diawali sk-ant-).")
    f = save_env_var("CLAUDE_CODE_OAUTH_TOKEN", tok, env_path())
    print(f"✅ Tersimpan di {f} ({token_shape(tok)})")


def run_doctor() -> None:
    from .doctor import live_auth_check, render, run_checks
    checks = run_checks()
    if "--live" in sys.argv:
        live = asyncio.run(live_auth_check())
        static_auth = next((c for c in checks if c.name == "Otentikasi Claude"), None)
        if live.ok and static_auth and not static_auth.ok:                       # hasil nyata mengalahkan dugaan statis
            checks = [c for c in checks if c is not static_auth]
        checks = checks + [live]
    text, ok = render(checks)
    print(text)
    sys.exit(0 if ok else 1)


def main() -> None:
    from .envfile import load_env
    load_env()
    try:
        arg = sys.argv[1] if len(sys.argv) > 1 else ""
        if arg == "doctor":
            run_doctor()
        if arg == "auth":
            run_auth()
        if arg == "savetoken":
            run_savetoken()
        if arg == "cdp-help":
            from .cdp import help_text
            print(help_text())
            sys.exit(0)
        if arg == "audit":
            run_audit()
            return
        if arg == "setup-telegram":
            run_setup_telegram()
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
        if arg == "telegram-check":
            asyncio.run(run_telegram_check())
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
