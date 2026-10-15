"""Konfigurasi: allowlist domain dan mode browser (env / data/allowlist.txt)."""
from __future__ import annotations

import os
from pathlib import Path

from .browser import WebConfig


def load_web_config(allowlist_file: str | Path = "data/allowlist.txt") -> WebConfig:
    domains: set[str] = set()
    f = Path(allowlist_file)
    if f.exists():
        domains |= {l.strip().lower() for l in f.read_text(encoding="utf-8").splitlines()
                    if l.strip() and not l.startswith("#")}
    domains |= {d.strip().lower() for d in os.environ.get("CHUNAI_ALLOWED_DOMAINS", "").split(",") if d.strip()}
    mode = os.environ.get("CHUNAI_BROWSER", "headless")   # headless | profile | cdp
    return WebConfig(
        allowed_domains=domains, mode=mode,
        profile_dir=os.environ.get("CHUNAI_PROFILE_DIR", "data/browser_profile"),
        cdp_url=os.environ.get("CHUNAI_CDP_URL", "http://localhost:9222"),
        headless=os.environ.get("CHUNAI_HEADLESS", "1") != "0",
    )
