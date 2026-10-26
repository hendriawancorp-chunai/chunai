"""chunai doctor: periksa semua prasyarat dan beri tahu cara memperbaiki. Tidak pernah mencetak rahasia."""
from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Check:
    name: str
    ok: bool
    detail: str = ""
    critical: bool = True


def claude_cli_path() -> Path | None:
    try:
        import claude_agent_sdk
        base = Path(claude_agent_sdk.__file__).parent / "_bundled"
        for n in ("claude", "claude.exe"):
            if (base / n).exists():
                return base / n
    except Exception:
        pass
    return None


def _playwright_chromium() -> str | None:
    from .browser import find_chromium
    if find_chromium():
        return find_chromium()
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            return path if Path(path).exists() else None
    except Exception:
        return None


def token_shape(tok: str) -> str:
    """Deskripsi aman bentuk token: panjang dan awalan jenis publik ('sk-ant-oat'), TIDAK pernah isi rahasianya."""
    head = tok[:10] if tok.startswith("sk-ant-") else "?"
    warn = ""
    if tok != tok.strip() or any(c.isspace() for c in tok):
        warn = "; mengandung spasi/baris baru (salah tempel)"
    elif tok.startswith(("\"", "'")) or tok.endswith(("\"", "'")):
        warn = "; diapit tanda kutip (hapus kutip)"
    elif not tok.startswith("sk-ant-"):
        warn = "; awalan tidak dikenal (seharusnya diawali sk-ant-)"
    elif len(tok) < 60:
        warn = "; terlalu pendek (kemungkinan terpotong saat ditempel)"
    return f"panjang {len(tok)}, awalan {head}{warn}"


def security_checks() -> list[Check]:
    c: list[Check] = []
    import stat
    envf = Path(os.environ.get("CHUNAI_ENV_FILE") or ".env")
    if envf.exists() and os.name == "posix":
        mode = stat.S_IMODE(envf.stat().st_mode)
        c.append(Check("Keamanan: izin .env", mode & 0o077 == 0, "600 (hanya Anda)" if mode & 0o077 == 0 else
                       f"{oct(mode)} terlalu terbuka. Jalankan: chmod 600 {envf}", critical=False))
    wt = os.environ.get("CHUNAI_WEB_TOKEN", "")
    from .interfaces.web import auth_off_requested
    if auth_off_requested():
        h = os.environ.get("CHUNAI_HOST", "127.0.0.1")
        c.append(Check("Keamanan: Web tanpa token", h in ("127.0.0.1", "localhost", "::1"),
                       "aktif, hanya komputer ini (CHUNAI_WEB_AUTH=off)" if h in ("127.0.0.1", "localhost", "::1") else
                       "CHUNAI_WEB_AUTH=off tetapi CHUNAI_HOST bukan localhost; server menolak start", critical=False))
    elif wt:
        c.append(Check("Keamanan: kekuatan token Web", len(wt) >= 24, f"panjang {len(wt)}" if len(wt) >= 24 else
                       "terlalu pendek (min. 24 karakter). Hapus nilainya di .env lalu jalankan ulang install_wsl.sh atau isi token acak panjang", critical=False))
    host = os.environ.get("CHUNAI_HOST", "127.0.0.1")
    c.append(Check("Keamanan: alamat Web", host in ("127.0.0.1", "localhost", "::1"),
                   f"{host} (hanya komputer ini)" if host in ("127.0.0.1", "localhost", "::1") else
                   f"{host} terbuka ke jaringan. Gunakan HTTPS/tunnel dan token kuat; jangan buka langsung ke internet", critical=False))
    if os.environ.get("CHUNAI_TELEGRAM_TOKEN") and not os.environ.get("CHUNAI_TELEGRAM_USERS", "").strip():
        c.append(Check("Keamanan: daftar pengguna Telegram", False, "token bot ada tetapi CHUNAI_TELEGRAM_USERS kosong (bot menolak start). "
                       "Jalankan: chunai setup-telegram", critical=False))
    from .usage import daily_limit
    lim = daily_limit()
    from .usage import session_limit
    sl = session_limit()
    c.append(Check("Batas biaya per sesi", True, f"setara ${sl:.0f}/sesi (CHUNAI_SESSION_BUDGET_USD)" if sl else "tanpa batas", critical=False))
    c.append(Check("Batas pemakaian harian", True, f"setara ${lim:.0f}/hari" if lim else "tanpa batas (disarankan mengisi CHUNAI_DAILY_BUDGET_USD)", critical=False))
    return c


def run_checks() -> list[Check]:
    c: list[Check] = []
    v = sys.version_info
    c.append(Check("Python 3.11+", v >= (3, 11), f"{v.major}.{v.minor}.{v.micro}" if v >= (3, 11) else
                   f"terdeteksi {v.major}.{v.minor}; pasang Python 3.11 atau lebih baru"))
    if os.name == "nt":
        c.append(Check("Lingkungan", False, "Windows asli terdeteksi: sandbox analisis TIDAK tersedia. "
                       "Disarankan menjalankan ChunAI di WSL2 (lihat docs/PANDUAN_WINDOWS.md).", critical=False))
    else:
        c.append(Check("Lingkungan", True, "Linux/WSL" + (" (WSL)" if "microsoft" in Path("/proc/version").read_text().lower() else "")
                       if Path("/proc/version").exists() else "POSIX", critical=False))

    cli = claude_cli_path()
    c.append(Check("Claude CLI bawaan SDK", cli is not None, str(cli) if cli else "tidak ditemukan; jalankan: pip install -e ."))
    has_oauth, has_key = bool(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")), bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_login = (Path.home() / ".claude" / ".credentials.json").exists()
    how = f"token langganan ({token_shape(os.environ['CLAUDE_CODE_OAUTH_TOKEN'])})" if has_oauth else \
        "ANTHROPIC_API_KEY" if has_key else "login Claude di ~/.claude" if has_login else ""
    c.append(Check("Otentikasi Claude", bool(how), how or "tidak terdeteksi. Jalankan: chunai auth (lalu simpan token di .env). Yakin sudah login? Uji nyata: chunai doctor --live"))
    mode = os.environ.get("CHUNAI_AUTH", "langganan").strip().lower()
    spare = bool(os.environ.get("CHUNAI_API_KEY"))
    if mode in ("api", "kunci", "apikey"):
        c.append(Check("Jalur Claude", has_key, "kunci API (berbayar per token; batasi lewat CHUNAI_DAILY_BUDGET_USD)" if has_key else
                       "CHUNAI_AUTH=api tetapi kunci belum ada. Jalankan: chunai auth-key", critical=False))
    elif spare:
        c.append(Check("Jalur Claude", True, "langganan; kunci API cadangan tersimpan (beralih: chunai mode api)", critical=False))
    if has_oauth and has_key:
        c.append(Check("Otentikasi ganda", False, "ANTHROPIC_API_KEY dan CLAUDE_CODE_OAUTH_TOKEN sama-sama ada; "
                       "kunci API akan dipakai (berbayar). Hapus salah satunya di .env.", critical=False))

    chrome = _playwright_chromium()
    c.append(Check("Chromium (Web Agent, gambar)", bool(chrome), chrome or "belum ada. Jalankan: python -m playwright install chromium"))
    for exe, why in (("soffice", "pratinjau/PDF dokumen"), ("ffmpeg", "video"), ("pdftoppm", "gambar pratinjau")):
        p = shutil.which(exe)
        c.append(Check(f"{exe} ({why})", bool(p), p or f"belum ada. Linux/WSL: sudo apt install -y {'libreoffice-writer libreoffice-impress' if exe == 'soffice' else 'poppler-utils' if exe == 'pdftoppm' else exe}",
                       critical=False))
    if os.environ.get("CHUNAI_BROWSER", "").lower() == "cdp":
        from .cdp import check_cdp
        okc, det = check_cdp(os.environ.get("CHUNAI_CDP_URL", "http://127.0.0.1:9222"))
        c.append(Check("Chrome sendiri (CDP)", okc, det, critical=False))
    from .sandbox import isolation_available
    iso = isolation_available()
    c.append(Check("Sandbox analisis (tanpa internet)", iso, "aktif" if iso else
                   "tidak tersedia: analisis otomatis dinonaktifkan (agen memakai Bash dengan izin). Di Linux/WSL2 biasanya aktif.", critical=False))

    tg_t, tg_u = bool(os.environ.get("CHUNAI_TELEGRAM_TOKEN")), os.environ.get("CHUNAI_TELEGRAM_USERS", "").strip()
    c.append(Check("Telegram", tg_t and bool(tg_u), "token dan ID terpasang" if tg_t and tg_u else
                   "isi CHUNAI_TELEGRAM_TOKEN dan CHUNAI_TELEGRAM_USERS di .env (opsional bila hanya memakai Web)", critical=False))
    c.append(Check("Token Web", bool(os.environ.get("CHUNAI_WEB_TOKEN")), "terpasang" if os.environ.get("CHUNAI_WEB_TOKEN") else
                   "isi CHUNAI_WEB_TOKEN di .env (jika kosong, token acak dibuat setiap kali jalan)", critical=False))
    c.extend(security_checks())
    from .timeutil import describe, tz_name
    c.append(Check("Zona waktu", True, f"{tz_name()} - sekarang {describe()}", critical=False))
    return c


def render(checks: list[Check]) -> tuple[str, bool]:
    lines, ok = [], True
    for k in checks:
        mark = "✅" if k.ok else ("❌" if k.critical else "⚠️")
        lines.append(f"{mark} {k.name}" + (f" - {k.detail}" if k.detail else ""))
        if k.critical and not k.ok:
            ok = False
    lines.append("")
    lines.append("SIAP dipakai." if ok else "Ada yang harus diperbaiki (tanda ❌) sebelum ChunAI bisa berjalan.")
    return "\n".join(lines), ok


def explain_error(text: str, status: int | None = None, kind: str | None = None) -> str:
    """Terjemahkan galat Claude ke saran perbaikan dalam bahasa Indonesia."""
    t = f"{text} {kind or ''}".lower()
    if status == 401 or any(k in t for k in ("invalid api key", "authentication", "oauth", "unauthorized", "/login", "invalid x-api-key", "token")):
        return ("login/token ditolak (langganan berakhir atau token salah). Langganan: chunai auth. Kunci API: chunai auth-key. "
                "Uji: chunai doctor --live")
    if status == 402 or "credit" in t or "billing" in t:
        return "saldo/kredit API tidak cukup. Isi saldo di console.anthropic.com, atau kembali ke langganan: chunai mode langganan"
    if status == 429 or "rate" in t or "usage limit" in t or "limit reached" in t:
        return ("batas pemakaian Claude tercapai. Langganan: tunggu kuota pulih (atau beralih ke kunci API: chunai mode api). "
                "API: batas laju/saldo; coba lagi sebentar atau periksa console.anthropic.com")
    if status == 403 or "forbidden" in t or "permission" in t:
        return "akses ditolak untuk akun ini (periksa paket Pro/Max aktif)"
    if "overloaded" in t or (status or 0) >= 500:
        return "layanan Claude sedang sibuk; coba lagi beberapa menit lagi"
    return "alasan tidak dikenali; lihat pesan asli di atas"


async def live_auth_check(timeout: float = 90.0) -> Check:
    """Uji nyata: satu pertanyaan kecil ke Claude (memakai sedikit kuota). Menampilkan alasan kegagalan yang sebenarnya."""
    import asyncio
    from contextlib import aclosing

    from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ResultMessage, TextBlock, query

    async def run() -> Check:
        result = None
        said, a_err = "", None
        async with aclosing(query(prompt="Balas satu kata: siap", options=ClaudeAgentOptions(max_turns=1, allowed_tools=[]))) as gen:
            async for m in gen:                      # habiskan aliran sampai selesai (tanpa return di tengah)
                if isinstance(m, AssistantMessage):
                    a_err = a_err or getattr(m, "error", None)
                    said += "".join(b.text for b in m.content if isinstance(b, TextBlock))
                elif isinstance(m, ResultMessage):
                    result = m
        if result is None:
            return Check("Uji nyata Claude", False, "tidak ada hasil dari Claude CLI")
        if not result.is_error and not a_err:
            return Check("Uji nyata Claude", True, "berhasil menjawab")
        raw = " | ".join(x for x in [(result.result or said or "").strip()[:200], "; ".join(result.errors or [])[:200],
                                       f"HTTP {result.api_error_status}" if result.api_error_status else "", str(a_err or "")] if x)
        return Check("Uji nyata Claude", False, f"{raw or 'ditolak tanpa pesan'}. Saran: {explain_error(raw, result.api_error_status, str(a_err or ''))}")

    try:
        return await asyncio.wait_for(run(), timeout)
    except asyncio.TimeoutError:
        return Check("Uji nyata Claude", False, f"tidak ada respons dalam {int(timeout)} detik. Saran: periksa internet/firewall ke api.anthropic.com "
                     "dan apakah token valid (buat ulang: chunai auth)")
    except Exception as e:
        return Check("Uji nyata Claude", False, f"{type(e).__name__}: {str(e)[:150]}. Saran: periksa 'chunai doctor' dan koneksi internet")
