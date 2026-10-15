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
    how = "token langganan (CLAUDE_CODE_OAUTH_TOKEN)" if has_oauth else "ANTHROPIC_API_KEY" if has_key else \
        "login Claude di ~/.claude" if has_login else ""
    c.append(Check("Otentikasi Claude", bool(how), how or "tidak terdeteksi. Jalankan: chunai auth (lalu simpan token di .env). Yakin sudah login? Uji nyata: chunai doctor --live"))
    if has_oauth and has_key:
        c.append(Check("Otentikasi ganda", False, "ANTHROPIC_API_KEY dan CLAUDE_CODE_OAUTH_TOKEN sama-sama ada; "
                       "kunci API akan dipakai (berbayar). Hapus salah satunya di .env.", critical=False))

    chrome = _playwright_chromium()
    c.append(Check("Chromium (Web Agent, gambar)", bool(chrome), chrome or "belum ada. Jalankan: python -m playwright install chromium"))
    for exe, why in (("soffice", "pratinjau/PDF dokumen"), ("ffmpeg", "video"), ("pdftoppm", "gambar pratinjau")):
        p = shutil.which(exe)
        c.append(Check(f"{exe} ({why})", bool(p), p or f"belum ada. Linux/WSL: sudo apt install -y {'libreoffice-writer libreoffice-impress' if exe == 'soffice' else 'poppler-utils' if exe == 'pdftoppm' else exe}",
                       critical=False))
    from .sandbox import isolation_available
    iso = isolation_available()
    c.append(Check("Sandbox analisis (tanpa internet)", iso, "aktif" if iso else
                   "tidak tersedia: analisis otomatis dinonaktifkan (agen memakai Bash dengan izin). Di Linux/WSL2 biasanya aktif.", critical=False))

    tg_t, tg_u = bool(os.environ.get("CHUNAI_TELEGRAM_TOKEN")), os.environ.get("CHUNAI_TELEGRAM_USERS", "").strip()
    c.append(Check("Telegram", tg_t and bool(tg_u), "token dan ID terpasang" if tg_t and tg_u else
                   "isi CHUNAI_TELEGRAM_TOKEN dan CHUNAI_TELEGRAM_USERS di .env (opsional bila hanya memakai Web)", critical=False))
    c.append(Check("Token Web", bool(os.environ.get("CHUNAI_WEB_TOKEN")), "terpasang" if os.environ.get("CHUNAI_WEB_TOKEN") else
                   "isi CHUNAI_WEB_TOKEN di .env (jika kosong, token acak dibuat setiap kali jalan)", critical=False))
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


async def live_auth_check() -> Check:
    """Uji nyata: satu pertanyaan kecil ke Claude (memakai sedikit kuota)."""
    try:
        from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
        async for m in query(prompt="Balas satu kata: siap", options=ClaudeAgentOptions(max_turns=1, allowed_tools=[])):
            if isinstance(m, ResultMessage):
                return Check("Uji nyata Claude", not m.is_error, "berhasil menjawab" if not m.is_error else "Claude menolak/gagal; periksa login & kuota")
        return Check("Uji nyata Claude", False, "tidak ada hasil")
    except Exception as e:
        return Check("Uji nyata Claude", False, f"{type(e).__name__}: {str(e)[:120]}")
