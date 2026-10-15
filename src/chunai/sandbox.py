"""Eksekutor Python berbatas untuk analisis data.

Lapisan: (1) namespace jaringan kosong (unshare -rn) -> tanpa internet di tingkat kernel;
(2) audit hook: tulis hanya di workspace, baca hanya workspace + pustaka sistem, tanpa subprocess/exec/socket;
(3) batas memori/CPU/ukuran file/proses + timeout; (4) environment bersih (tanpa API key/token).
Ini mitigasi berlapis, bukan jaminan mutlak; bila isolasi jaringan tidak tersedia, eksekusi DITOLAK."""
from __future__ import annotations

import json
import os
import resource
import shutil
import subprocess
import sys
import sysconfig
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

RUNNER = r'''
import sys, os, json, builtins
cfg = json.loads(os.environ.pop("CHUNAI_SANDBOX_CFG"))
WRITE = [os.path.realpath(p) for p in cfg["write"]]
READ = [os.path.realpath(p) for p in cfg["read"]] + WRITE
SECRET = tuple(cfg["secret"])
BLOCK = {"subprocess.Popen", "os.system", "os.exec", "os.posix_spawn", "os.spawn", "os.fork", "os.forkpty",
         "socket.connect", "socket.bind", "socket.sendto", "socket.sendmsg", "socket.getaddrinfo",
         "ctypes.dlopen", "pty.spawn"}
WRITE_EVENTS = {"os.remove", "os.rmdir", "os.mkdir", "os.chmod", "os.chown", "os.truncate", "os.utime",
                "os.setxattr", "os.mkfifo", "os.mknod"}
def under(p, roots):
    p = os.path.realpath(p)
    return any(p == r or p.startswith(r.rstrip("/") + "/") for r in roots)
def hook(event, args):
    if event in BLOCK or event.startswith("ctypes.dlopen"):
        raise PermissionError(f"Diblokir sandbox: {event}")
    if event == "open":
        path, mode, flags = args
        if isinstance(path, int) or path is None:
            return
        path = os.fsdecode(path)
        if any(s in path for s in SECRET):
            raise PermissionError(f"Akses ke berkas sensitif diblokir: {os.path.basename(path)}")
        writing = bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC)) if isinstance(flags, int) else False
        if not writing and isinstance(mode, str):
            writing = any(c in mode for c in "wax+")
        if writing:
            if not under(path, WRITE):
                raise PermissionError("Tulis di luar workspace diblokir.")
        elif not under(path, READ):
            raise PermissionError("Baca di luar workspace/pustaka sistem diblokir.")
    elif event in WRITE_EVENTS:
        if not under(os.fsdecode(args[0]), WRITE):
            raise PermissionError("Ubah berkas di luar workspace diblokir.")
    elif event in ("os.rename", "os.replace", "os.link", "os.symlink"):
        if not (under(os.fsdecode(args[0]), WRITE) and under(os.fsdecode(args[1]), WRITE)):
            raise PermissionError("Pindah/tautan di luar workspace diblokir.")
sys.addaudithook(hook)
code = sys.stdin.read()
g = {"__name__": "__main__", "__builtins__": builtins}
exec(compile(code, "<analisis>", "exec"), g)
'''

_SECRET = (".ssh", ".aws", ".gnupg", ".claude", "browser_profile", ".env", "credentials", "id_rsa",
           ".config/anthropic", "audit.jsonl", ".netrc", ".git-credentials")


@dataclass
class RunResult:
    ok: bool
    stdout: str = ""
    stderr: str = ""
    returncode: int = 0
    timed_out: bool = False
    new_files: list[str] = field(default_factory=list)


def isolation_available() -> bool:
    if not shutil.which("unshare"):
        return False
    try:
        r = subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _limits(mem_mb: int, cpu_s: int):
    def apply():
        resource.setrlimit(resource.RLIMIT_AS, (mem_mb * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_s, cpu_s + 5))
        resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
        os.setsid()
    return apply


def _system_read_roots() -> list[str]:
    roots = {sys.prefix, sys.base_prefix, sys.exec_prefix, "/usr", "/lib", "/lib64", "/etc/localtime", "/etc/ld.so.cache",
             "/etc/timezone", "/proc/self", "/proc/cpuinfo", "/proc/meminfo", "/sys/devices/system/cpu", "/dev/null",
             "/dev/urandom", "/dev/random", "/etc/ssl", "/etc/mime.types", "/usr/share"}
    for k in ("stdlib", "platstdlib", "purelib", "platlib"):
        roots.add(sysconfig.get_paths()[k])
    return sorted(roots)


def snapshot(root: Path) -> dict[str, float]:
    return {str(p): p.stat().st_mtime for p in root.rglob("*") if p.is_file() and ".mpl" not in p.parts and ".tmp" not in p.parts}


def run_python(code: str, workdir: Path, timeout: int = 60, mem_mb: int = 1536) -> RunResult:
    if not isolation_available():
        return RunResult(False, stderr="Isolasi jaringan (unshare -rn) tidak tersedia di mesin ini; "
                                        "eksekusi otomatis ditolak. Gunakan Bash (dengan izin) sebagai gantinya.", returncode=-1)
    workdir = workdir.resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    mpl = workdir / ".mpl"
    mpl.mkdir(exist_ok=True)
    tmp = workdir / ".tmp"                       # temp pribadi; /tmp sistem TIDAK dibuka
    tmp.mkdir(exist_ok=True)
    cfg = {"write": [str(workdir)], "read": _system_read_roots(), "secret": list(_SECRET)}
    env = {"PATH": "/usr/bin:/bin", "HOME": str(workdir), "LANG": "C.UTF-8", "MPLBACKEND": "Agg",
           "MPLCONFIGDIR": str(mpl), "PYTHONHASHSEED": "0", "CHUNAI_SANDBOX_CFG": json.dumps(cfg), "TMPDIR": str(tmp)}
    before = snapshot(workdir)
    try:
        p = subprocess.run(["unshare", "-rn", "--", sys.executable, "-I", "-c", RUNNER], input=code, text=True,
                           capture_output=True, cwd=workdir, env=env, timeout=timeout,
                           preexec_fn=_limits(mem_mb, timeout))
        out, err, rc, to = p.stdout, p.stderr, p.returncode, False
    except subprocess.TimeoutExpired as e:
        out, err, rc, to = (e.stdout or b"").decode() if isinstance(e.stdout, bytes) else (e.stdout or ""), \
            f"Waktu habis ({timeout}s); proses dihentikan.", -9, True
    after = snapshot(workdir)
    new = sorted(str(Path(p).relative_to(workdir)) for p, m in after.items() if before.get(p) != m)
    return RunResult(rc == 0 and not to, out[-8000:], err[-4000:], rc, to, new)
