"""Pemakaian harian (dari audit.jsonl) untuk batas biaya harian dan tampilan audit yang mudah dibaca."""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path


def daily_limit() -> float:
    """Batas biaya harian (USD). Untuk langganan angka ini 'setara biaya' sebagai pengaman, bukan tagihan. 0 = tanpa batas."""
    try:
        return float(os.environ.get("CHUNAI_DAILY_BUDGET_USD", "20"))
    except ValueError:
        return 20.0


def _events(base: Path):
    """Semua kejadian audit. Biaya `turn_done` dinormalkan jadi biaya PER GILIRAN di `cost_usd`.
    Catatan lama menyimpan total berjalan sesi dari SDK (tanpa `session_total`); selisihnya dihitung di sini."""
    for f in sorted(base.glob("*/audit.jsonl")):
        prev = 0.0
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    e = json.loads(line)
                except ValueError:
                    continue
                if e.get("event") == "turn_done" and e.get("cost_usd") is not None:
                    c = float(e["cost_usd"])
                    if "session_total" in e:
                        prev = float(e["session_total"])
                    else:
                        e["cost_usd"], prev = (c - prev if c >= prev else c), c
                yield e
        except OSError:
            continue


def day_cost(base: Path, day: date) -> float:
    key = day.isoformat()
    return round(sum(float(e.get("cost_usd") or 0) for e in _events(base)
                     if e.get("event") == "turn_done" and str(e.get("ts", "")).startswith(key)), 4)


def render_audit(base: Path, n: int = 30) -> str:
    rows = []
    for e in _events(base):
        ev = e.get("event")
        if ev == "auto_allowed":
            continue                                           # ringkas: izin otomatis tidak ditampilkan
        t = str(e.get("ts", ""))[:19].replace("T", " ")
        if ev == "user_prompt":
            txt = f"PERINTAH   {str(e.get('prompt', ''))[:70]!r}"
        elif ev == "approval_requested":
            txt = f"IZIN?      {e.get('tool', '')}"
        elif ev == "approval_decision":
            txt = f"KEPUTUSAN  {'DISETUJUI' if e.get('approved') else 'DITOLAK'} {e.get('tool', '')} {e.get('note', '') or ''}".rstrip()
        elif ev == "denied_by_policy":
            txt = f"DIBLOKIR   {e.get('tool', '')}"
        elif ev == "turn_done":
            txt = f"SELESAI    biaya setara ${float(e.get('cost_usd') or 0):.3f}"
        elif ev == "tool_use" and e.get("tool", "").endswith("kirim_file"):
            txt = f"KIRIM FILE {e.get('path', '')}"
        else:
            continue
        rows.append(f"{t}  {txt}")
    return "\n".join(rows[-n:]) or "(belum ada catatan)"
