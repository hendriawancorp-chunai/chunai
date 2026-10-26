"""Pemilah model: perintah sederhana -> model murah, perintah rumit -> model kuat. Aturan kata kunci (tanpa panggilan LLM tambahan).

Tingkat: ringan (Haiku), sedang (Sonnet), berat (Opus). Tugas web/aksi (form, kuis, media sosial) TIDAK pernah ke Haiku:
pada pengujian Haiku gagal memakai lembar data diri di form. Pengaman (kartu izin, allowlist, sandbox) di luar model, jadi tak terpengaruh.
Pengaturan: CHUNAI_MODEL (model tetap, mematikan pemilahan), CHUNAI_MODEL_AUTO=off, CHUNAI_MODEL_RINGAN/SEDANG/BERAT (ganti id model).
"""
from __future__ import annotations

import os
import re
import time

TIERS = ("ringan", "sedang", "berat")
DEFAULTS = {"ringan": "claude-haiku-5-5", "sedang": "claude-sonnet-5-5", "berat": "claude-opus-5-5"}
ALIASES = {"ringan": "ringan", "cepat": "ringan", "haiku": "ringan", "sedang": "sedang", "sonnet": "sedang",
           "berat": "berat", "teliti": "berat", "kuat": "berat", "opus": "berat"}
PREFIX = re.compile(r"^!(cepat|ringan|sedang|teliti|berat)\b[:,]?\s*", re.I)
MODEL_ID = re.compile(r"^claude-[a-z0-9][a-z0-9.\-]{2,60}$")
FOLLOWUP_TTL = 20 * 60          # balasan singkat ("lanjutkan", "ya") mewarisi tingkat tugas sebelumnya selama 20 menit

HEAVY = re.compile(
    r"https?://|www\.|\b(form|formulir|survei|survey|kuis|quiz|soal|ujian|linkedin|instagram|lamar\w*|lowongan|posting\w*|"
    r"situs|website|web|klik|login|daftarkan|mendaftar|isikan|mengisi|pengisian|isi\s+(?:form|data|survei|kuis)|koneksi|komentar|"
    r"unggah\s+ke|kirim\s+(?:form|lamaran|email|pesan))\b", re.I)
MEDIUM = re.compile(
    r"\b(riset|analis\w*|bandingkan|perbandingan|kajian|laporan|ringkas\w*|rangkum\w*|dokumen|docx|pptx|xlsx|presentasi|slide|"
    r"excel|csv|pdf|grafik|chart|data|saham|teknikal|fundamental|revisi|revisikan|gambar|video|infografis|jadwal\w*|ingatkan|"
    r"watchlist|sitasi|referensi|jurnal|strategi|rencana|buatkan|susun\w*)\b", re.I)


def fixed_model() -> str | None:
    m = os.environ.get("CHUNAI_MODEL", "").strip()
    return m or None


def auto_enabled() -> bool:
    return not fixed_model() and os.environ.get("CHUNAI_MODEL_AUTO", "on").strip().lower() not in ("off", "0", "false", "none")


def model_for(tier: str) -> str:
    return os.environ.get(f"CHUNAI_MODEL_{tier.upper()}", "").strip() or DEFAULTS[tier]


def label(model: str | None) -> str:
    m = (model or "").lower()
    for k, v in (("haiku", "Haiku"), ("sonnet", "Sonnet"), ("opus", "Opus"), ("fable", "Fable")):
        if k in m:
            return v
    return model or "bawaan"


def split_prefix(text: str) -> tuple[str | None, str]:
    """'!cepat ...' / '!teliti ...' memaksa tingkat untuk satu perintah. Kembalikan (tingkat, teks tanpa awalan)."""
    m = PREFIX.match(text.strip())
    if not m:
        return None, text
    return ALIASES[m.group(1).lower()], text.strip()[m.end():] or text


def classify(text: str, has_upload: bool = False, prev: tuple[str, float] | None = None, now: float | None = None) -> tuple[str, str]:
    """(tingkat, alasan). Urutan: web/aksi -> berat; dokumen/analisis/lampiran/panjang -> sedang; balasan singkat -> warisan; lain -> ringan."""
    t = text.strip()
    if HEAVY.search(t):
        return "berat", "tugas web/aksi"
    if has_upload or MEDIUM.search(t) or len(t) > 150:
        return "sedang", "dokumen/analisis/lampiran" if (has_upload or MEDIUM.search(t)) else "perintah panjang"
    if prev and len(t) < 80 and ((now or time.time()) - prev[1]) < FOLLOWUP_TTL:
        return prev[0], "lanjutan tugas sebelumnya"
    return "ringan", "pertanyaan/percakapan singkat"


def parse_choice(arg: str) -> str | None:
    """Nilai untuk /model: 'otomatis', tingkat/alias, atau id model 'claude-...'. None bila tidak dikenali."""
    a = arg.strip().lower()
    if a in ("otomatis", "auto"):
        return "otomatis"
    if a in ALIASES:
        return ALIASES[a]
    return a if MODEL_ID.match(a) else None


def pick(text: str, pref: str | None, has_upload: bool = False, prev: tuple[str, float] | None = None) -> tuple[str | None, str | None, str, str]:
    """(model, tingkat, alasan, teks_bersih). model=None berarti biarkan bawaan (pemilahan mati)."""
    tier_prefix, text = split_prefix(text)
    fixed = fixed_model()
    if fixed:
        return fixed, None, "CHUNAI_MODEL tetap", text
    if tier_prefix:
        return model_for(tier_prefix), tier_prefix, "awalan perintah", text
    if pref and pref != "otomatis":
        return (model_for(pref), pref, "pilihan /model", text) if pref in TIERS else (pref, None, "pilihan /model", text)
    if not auto_enabled():
        return None, None, "pemilahan mati", text
    tier, why = classify(text, has_upload, prev)
    return model_for(tier), tier, why, text


def scheduled_model(text: str) -> str | None:
    """Tugas terjadwal berjalan tanpa pengawasan (aksi berdampak ditolak): murah, maksimal Sonnet."""
    if fixed_model():
        return fixed_model()
    if not auto_enabled():
        return None
    body = re.sub(r"\b(ingatkan|jadwal\w*)\b", "", text, flags=re.I)         # menjalankan pengingat tersimpan itu ringan
    return model_for("sedang" if MEDIUM.search(body) else "ringan")
