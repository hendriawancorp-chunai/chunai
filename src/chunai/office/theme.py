"""Tema dokumen/presentasi. Default diturunkan dari gaya referensi pengguna (biru korporat);
tema khusus dapat ditaruh di data/themes/<nama>.json (warna, font, footer, logo)."""
from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from pathlib import Path


@dataclass
class Theme:
    name: str = "korporat-biru"
    navy: str = "14284B"          # judul gelap, header tabel
    primary: str = "0070C0"       # biru utama (subjudul, panel)
    cyan: str = "00A0E3"
    green: str = "8DC63F"         # aksen
    yellow: str = "F4B400"
    light: str = "EAF3FB"         # panel muda
    zebra: str = "EEF3FA"
    text: str = "1B1B1B"
    muted: str = "6B7A90"
    font_body: str = "Calibri"
    font_heading: str = "Calibri"
    font_slide: str = "Calibri"   # mis. "Poppins" bila terpasang di komputer pengguna
    footer_left: str = ""
    footer_right: str = ""
    logo_left: str = ""           # path gambar (opsional)
    logo_right: str = ""
    extra: dict = field(default_factory=dict)


def load_theme(name: str | None = None, themes_dir: str | Path = "data/themes") -> Theme:
    if not name or name == "korporat-biru":
        return Theme()
    f = Path(themes_dir) / f"{name}.json"
    if not f.exists():
        raise FileNotFoundError(f"Tema '{name}' tidak ditemukan di {themes_dir}")
    raw = json.loads(f.read_text(encoding="utf-8"))
    known = {x.name for x in fields(Theme)}
    return Theme(**{k: v for k, v in raw.items() if k in known}, name=name)


def rgb(hexstr: str):
    from docx.shared import RGBColor
    return RGBColor.from_string(hexstr.upper())
