"""Pemeriksa laporan riset: memastikan klaim bersitasi dan daftar sumber valid."""
from __future__ import annotations

import re

_URL = re.compile(r"https?://[^\s)>\]]+")
_CITE = re.compile(r"\[(\d+)\]")
_HAS_NUMBER = re.compile(r"\d")


def _sections(md: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {"": []}
    cur = ""
    for line in md.splitlines():
        if line.startswith("#"):
            cur = line.lstrip("#").strip().lower()
            out.setdefault(cur, [])
        else:
            out[cur].append(line)
    return out


def lint_report(md: str) -> list[str]:
    """Kembalikan daftar masalah. Daftar kosong = lolos."""
    issues: list[str] = []
    secs = _sections(md)
    src_key = next((k for k in secs if k.startswith("sumber")), None)
    note_key = next((k for k in secs if k.startswith("catatan")), None)

    if src_key is None:
        return ["Tidak ada bagian '## Sumber'."]
    src_lines = [l for l in secs[src_key] if l.strip()]
    listed: dict[int, str] = {}
    for l in src_lines:
        m = re.match(r"\s*(?:[-*]\s*)?\[?(\d+)[\].)]\s*(.+)", l)
        if not m:
            continue
        n, rest = int(m.group(1)), m.group(2)
        if not _URL.search(rest):
            issues.append(f"Sumber [{n}] tidak punya URL.")
        listed[n] = rest
    if not listed:
        issues.append("Daftar sumber kosong atau tidak bernomor (format: '1. Judul — URL (diakses YYYY-MM-DD)').")
    if note_key is None:
        issues.append("Tidak ada bagian '## Catatan keterbatasan'.")

    for key, lines in secs.items():
        if key == src_key or (note_key and key == note_key) or key == "":
            continue
        for l in lines:
            text = l.strip()
            if not text or text.startswith(("|---", "---")):
                continue
            cites = [int(c) for c in _CITE.findall(text)]
            if _HAS_NUMBER.search(re.sub(r"\[\d+\]", "", text)) and not cites and not _URL.search(text):
                issues.append(f"Klaim berangka tanpa sitasi: {text[:80]}")
            for c in cites:
                if c not in listed:
                    issues.append(f"Sitasi [{c}] tidak ada di daftar sumber.")
    return issues
