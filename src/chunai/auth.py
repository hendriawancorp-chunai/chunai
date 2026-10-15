"""chunai auth: jalankan `claude setup-token`, tangkap tokennya, simpan ke .env (tanpa salin-tempel manual)."""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][A-Za-z0-9]")
_TOKEN_CHARS = re.compile(r"^[A-Za-z0-9_\-]+$")


WIDE_COLS = 500            # lebar terminal anak: token tidak pernah dipatahkan oleh CLI


def extract_token(raw: str, widths: tuple[int, ...] = (80, WIDE_COLS)) -> str | None:
    """Cari token 'sk-ant-...' di keluaran terminal (membuang kode warna). Baris lanjutan hanya disambung bila baris
    sebelumnya PERSIS selebar terminal (tanda dipatahkan), sehingga kata biasa setelah token tidak ikut tersambung."""
    text = _ANSI.sub("", raw).replace("\r", "")
    phys = [ln.rstrip() for ln in text.split("\n")]
    best = ""
    for i, ln in enumerate(phys):
        pos = ln.find("sk-ant-")
        if pos < 0:
            continue
        m = re.match(r"[A-Za-z0-9_\-]+", ln[pos:])
        if not m:
            continue
        tok, cur, j = m.group(0), ln, i + 1
        while m.end() == len(ln[pos:]) if cur is ln else True:
            wrapped = any(abs(len(cur) - w) <= 1 for w in widths)
            nxt = phys[j].strip() if j < len(phys) else ""
            if not (wrapped and nxt and _TOKEN_CHARS.match(nxt)):
                break
            tok += nxt; cur = phys[j]; j += 1
        if len(tok) > len(best):
            best = tok
    return best if len(best) >= 60 else None


def run_setup_token(cli: Path) -> tuple[int, str]:
    """Jalankan setup-token interaktif; kembalikan (kode_keluar, keluaran_mentah). pty di Linux/WSL, lebar 500 kolom."""
    argv = [str(cli), "setup-token"]
    try:
        import fcntl
        import pty
        import select
        import struct
        import termios
        import tty
    except ImportError:                                           # Windows asli: tanpa penangkapan
        return subprocess.call(argv), ""
    pid, fd = pty.fork()
    if pid == 0:
        os.execv(argv[0], argv)
    try:
        rows = os.get_terminal_size().lines
    except OSError:
        rows = 40
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", rows, WIDE_COLS, 0, 0))
    buf = bytearray()
    restore = None
    try:
        stdin_fd = sys.stdin.fileno()
        restore = termios.tcgetattr(stdin_fd)
        tty.setraw(stdin_fd)
    except (termios.error, OSError, ValueError, AttributeError):   # stdin bukan terminal (mis. dijalankan dari tes)
        stdin_fd, restore = -1, None
    watch = [fd] + ([stdin_fd] if restore is not None else [])
    try:
        while True:
            r, _, _ = select.select(watch, [], [], 0.2)
            if fd in r:
                try:
                    data = os.read(fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                buf.extend(data)
                os.write(1, data)
            if stdin_fd in r:
                os.write(fd, os.read(stdin_fd, 1024))
    finally:
        if restore is not None:
            termios.tcsetattr(stdin_fd, termios.TCSAFLUSH, restore)
    _, status = os.waitpid(pid, 0)
    return os.waitstatus_to_exitcode(status), buf.decode("utf-8", "replace")


def clear_screen() -> None:
    sys.stdout.write("\033[3J\033[H\033[2J")                       # hapus layar + riwayat gulir agar token tidak tertinggal
    sys.stdout.flush()
