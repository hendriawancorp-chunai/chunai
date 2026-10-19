"""Chrome milik pengguna lewat CDP: panduan, pemeriksaan koneksi."""
from __future__ import annotations

import os
from pathlib import Path

CHROME_CMD = r'Start-Process "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "--remote-debugging-port=9222","--user-data-dir=C:\chunai-chrome"'


def in_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def check_cdp(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """(ok, detail) untuk http://host:port; membaca /json/version (aman: hanya info versi)."""
    import httpx
    base = url.rstrip("/")
    try:
        r = httpx.get(base + "/json/version", timeout=timeout)
        r.raise_for_status()
        js = r.json()
        return True, f"terhubung ke {js.get('Browser', 'Chrome')}"
    except httpx.HTTPError as e:
        why = type(e).__name__
    except ValueError:
        why = "respons bukan JSON"
    hint = ("Chrome belum dijalankan dengan port debug, atau WSL belum bisa menjangkau Windows (lihat langkah A dan B di panduan).")
    return False, f"tidak terhubung ke {base} ({why}). {hint}"


def help_text(url: str | None = None) -> str:
    url = url or os.environ.get("CHUNAI_CDP_URL", "http://127.0.0.1:9222")
    ok, detail = check_cdp(url)
    status = f"{'✅' if ok else '❌'} Sekarang: {detail}"
    return f"""PANDUAN CHROME SENDIRI (CDP) untuk Windows 11 + WSL2   [{status}]

Tujuan: agen memakai Chrome Anda yang sudah login (LinkedIn, Instagram, dll.), di tab baru miliknya sendiri. Tab Anda tidak disentuh.

A. Sekali saja: agar WSL2 bisa menjangkau Windows
   1) Di Windows, buka Notepad, simpan sebagai  %UserProfile%\\.wslconfig  (isi dua baris):
        [wsl2]
        networkingMode=mirrored
   2) Di PowerShell: wsl --shutdown     lalu buka Ubuntu lagi.
   (Windows 11 22H2 atau lebih baru. Bila .wslconfig sudah ada, tambahkan dua baris itu tanpa menghapus isi lama.)

B. Setiap kali ingin memakai (di Windows):
   1) Tutup SEMUA jendela Chrome (cek ikon baki sistem).
   2) Jalankan di PowerShell (satu baris) atau klik kanan scripts\\start-chrome-cdp.ps1 > Run with PowerShell:
        {CHROME_CMD}
   3) Di jendela Chrome itu, login manual ke LinkedIn/Instagram (cukup sekali; sesi tersimpan di C:\\chunai-chrome).

C. Di Ubuntu (sekali), isi .env:
        CHUNAI_BROWSER=cdp
        CHUNAI_CDP_URL=http://127.0.0.1:9222
   lalu jalankan ulang ./scripts/run.sh dan  chunai doctor .

Keamanan: port 9222 memberi kendali penuh atas Chrome profil khusus itu. Pakai HANYA profil C:\\chunai-chrome (bukan profil harian),
hanya di komputer pribadi, dan tutup Chrome itu bila tidak dipakai. Jangan membuka port ini ke jaringan.
Chrome 136+ mewajibkan --user-data-dir sendiri agar port debug aktif; itu sebabnya profil khusus dipakai.
"""
