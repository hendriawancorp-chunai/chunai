"""Render dokumen ke PDF/PNG (LibreOffice + pdftoppm) untuk pemeriksaan visual."""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path


def to_pdf(src: Path, out_dir: Path, timeout: int = 180) -> Path:
    if not shutil.which("soffice"):
        raise RuntimeError("LibreOffice (soffice) tidak tersedia.")
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as home:      # profil sementara agar tidak bentrok
        subprocess.run(["soffice", f"-env:UserInstallation=file://{home}", "--headless", "--convert-to", "pdf",
                        "--outdir", str(out_dir), str(src)], check=True, capture_output=True, timeout=timeout)
    pdf = out_dir / (src.stem + ".pdf")
    if not pdf.exists():
        raise RuntimeError("Konversi PDF gagal.")
    return pdf


def to_pngs(pdf: Path, out_dir: Path, dpi: int = 60, first: int | None = None, last: int | None = None) -> list[Path]:
    if not shutil.which("pdftoppm"):
        raise RuntimeError("pdftoppm tidak tersedia.")
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = ["pdftoppm", "-png", "-r", str(dpi)]
    if first: cmd += ["-f", str(first)]
    if last: cmd += ["-l", str(last)]
    subprocess.run(cmd + [str(pdf), str(out_dir / pdf.stem)], check=True, capture_output=True, timeout=180)
    return sorted(out_dir.glob(f"{pdf.stem}-*.png"))
