"""Profil investor: horizon, toleransi risiko, modal, batas risiko per transaksi, preferensi. Disimpan lokal (data/saham/profil.json)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from .store import SahamError, root

HORIZON = {"pendek": "kurang dari 3 bulan (trading)", "menengah": "3-12 bulan", "panjang": "lebih dari 1 tahun (investasi)"}
TOLERANSI = ("konservatif", "moderat", "agresif")
MAX_PREF = 12


def path() -> Path:
    return root() / "profil.json"


def load() -> dict:
    try:
        d = json.loads(path().read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def validate(horizon: str, toleransi: str, modal: float, risiko_persen: float, preferensi: list[str], posisi: str = "") -> dict:
    h, t = str(horizon).strip().lower(), str(toleransi).strip().lower()
    if h not in HORIZON:
        raise SahamError(f"horizon harus salah satu dari: {', '.join(HORIZON)}.")
    if t not in TOLERANSI:
        raise SahamError(f"toleransi_risiko harus salah satu dari: {', '.join(TOLERANSI)}.")
    try:
        modal, risiko_persen = float(modal), float(risiko_persen)
    except (TypeError, ValueError):
        raise SahamError("modal dan risiko_persen harus angka.") from None
    if modal <= 0:
        raise SahamError("modal harus > 0 (Rupiah).")
    if not 0 < risiko_persen <= 5:
        raise SahamError("risiko_persen (rugi maksimum per transaksi, % dari modal) harus > 0 dan <= 5; praktik umum 0,5-2%.")
    prefs = [str(p).strip()[:40] for p in (preferensi or []) if str(p).strip()][:MAX_PREF]
    return {"horizon": h, "toleransi_risiko": t, "modal": modal, "risiko_persen": risiko_persen, "preferensi": prefs, "posisi": str(posisi)[:600]}


def save(p: dict) -> None:
    f = path()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
    if os.name == "posix":
        os.chmod(tmp, 0o600)
    tmp.replace(f)


def render(p: dict) -> str:
    if not p:
        return "(profil investor belum diisi; tanyakan: horizon, toleransi risiko, modal, batas risiko per transaksi, preferensi)"
    return (f"Horizon: {p['horizon']} ({HORIZON[p['horizon']]})\nToleransi risiko: {p['toleransi_risiko']}\nModal: Rp{p['modal']:,.0f}".replace(",", ".") +
            f"\nBatas rugi per transaksi: {p['risiko_persen']}% modal\nPreferensi: {', '.join(p['preferensi']) or '-'}" + (f"\nPosisi saat ini: {p['posisi']}" if p.get("posisi") else ""))
