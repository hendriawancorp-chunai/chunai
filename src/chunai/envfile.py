"""Pemuat berkas .env sederhana (tanpa dependensi). Variabel yang sudah ada di lingkungan TIDAK ditimpa."""
from __future__ import annotations

import os
import stat
import sys
from pathlib import Path


def parse_env(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        if "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip()
        if not key.replace("_", "").isalnum():
            continue
        if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
            val = val[1:-1]
        else:                                   # komentar di akhir baris: KEY=nilai  # catatan
            val = val.split(" #", 1)[0].rstrip()
        out[key] = val
    return out


def load_env(path: str | Path | None = None) -> Path | None:
    """Muat .env dari CHUNAI_ENV_FILE, atau ./.env, atau ~/.chunai/.env. Kembalikan path yang dipakai."""
    candidates = [Path(path)] if path else [Path(os.environ["CHUNAI_ENV_FILE"])] if os.environ.get("CHUNAI_ENV_FILE") \
        else [Path.cwd() / ".env", Path.home() / ".chunai" / ".env"]
    for f in candidates:
        if f.is_file():
            if os.name == "posix" and f.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                print(f"⚠ {f} bisa dibaca pengguna lain. Jalankan: chmod 600 {f}", file=sys.stderr)
            for k, v in parse_env(f.read_text(encoding="utf-8")).items():
                os.environ.setdefault(k, v)
            return f
    return None


def env_path() -> Path:
    """Berkas .env yang dipakai: CHUNAI_ENV_FILE, atau ./.env."""
    return Path(os.environ["CHUNAI_ENV_FILE"]) if os.environ.get("CHUNAI_ENV_FILE") else Path.cwd() / ".env"


def save_env_var(key: str, value: str, path: str | Path | None = None) -> Path:
    """Ubah/tambah KEY=value di .env tanpa mengusik baris lain. Atomik, izin 600."""
    f = Path(path) if path else env_path()
    lines = f.read_text(encoding="utf-8").splitlines() if f.exists() else []
    new, done = [], False
    for line in lines:
        bare = line.strip().removeprefix("export ").lstrip()
        if not done and bare.startswith(f"{key}=") and not line.lstrip().startswith("#"):
            new.append(f"{key}={value}"); done = True
        else:
            new.append(line)
    if not done:
        new.append(f"{key}={value}")
    tmp = f.with_name(f.name + ".tmp")
    tmp.write_text("\n".join(new) + "\n", encoding="utf-8")
    if os.name == "posix":
        tmp.chmod(0o600)
    tmp.replace(f)
    return f


def apply_auth_mode(environ=None) -> str:
    """Pilih jalur otentikasi Claude secara deterministik (dipanggil setelah load_env).
    CHUNAI_AUTH=langganan (bawaan): pakai token langganan; ANTHROPIC_API_KEY diabaikan agar tidak tertagih tanpa sengaja.
    CHUNAI_AUTH=api: pakai kunci API (CHUNAI_API_KEY atau ANTHROPIC_API_KEY, berbayar per token); token langganan diabaikan.
    Mengembalikan 'langganan', 'api', atau 'api-tanpa-kunci' (mode api tetapi kunci belum ada)."""
    env = os.environ if environ is None else environ
    mode = env.get("CHUNAI_AUTH", "langganan").strip().lower()
    if mode in ("api", "kunci", "apikey"):
        key = env.get("CHUNAI_API_KEY") or env.get("ANTHROPIC_API_KEY") or ""
        if not key:
            return "api-tanpa-kunci"
        env["ANTHROPIC_API_KEY"] = key
        env.pop("CLAUDE_CODE_OAUTH_TOKEN", None)
        return "api"
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        env.pop("ANTHROPIC_API_KEY", None)
    return "langganan"
