"""Gerbang kualitas laporan analisis saham: struktur wajib, larangan kata kepastian, dan penelusuran angka ke keluaran tool."""
from __future__ import annotations

import re

_UNIT = {"triliun": 1e12, "t": 1e12, "miliar": 1e9, "m": 1e9, "b": 1e9, "juta": 1e6, "jt": 1e6, "ribu": 1e3, "rb": 1e3, "k": 1e3}
_NUM = re.compile(r"(?<![\w.,/])([-+]?\d(?:[\d.,]*\d)?)(%?)(?:\s*(triliun|miliar|juta|ribu|jt|rb|T|M|B|K)\b)?", re.I)
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}\b|\b\d{1,2}\s+(?:jan|feb|mar|apr|mei|jun|jul|agu|sep|okt|nov|des)\w*\s+\d{4}\b", re.I)
_MONTH_DATE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b|\b\d{1,2}\s+(?:jan|feb|mar|apr|mei|jun|jul|agu|sep|okt|nov|des)\w*\s+20\d{2}\b|\b(?:jan|feb|mar|apr|mei|jun|jul|agu|sep|okt|nov|des)\w*\s+20\d{2}\b", re.I)
CERTAINTY = re.compile(r"\b(pasti (naik|untung|menguntungkan|tembus|cuan)|dijamin|tanpa risiko|bebas risiko|100% aman|guaranteed|risk[- ]free|sudah pasti|cuan pasti|pasti cuan)\b", re.I)
RECO = re.compile(r"\b(beli|akumulasi|kandidat|jual|tahan|kurangi|hindari|rekomendasi)\b", re.I)


def _candidates(tok: str) -> list[float]:
    t = re.sub(r"[+\-]", "", tok).strip(".,")
    if not t:
        return []
    try:
        if "." in t and "," in t:
            return [float(t.replace(".", "").replace(",", "."))] if t.rfind(",") > t.rfind(".") else [float(t.replace(",", ""))]
        for sep in (".", ","):
            if sep in t:
                parts = t.split(sep)
                if len(parts) > 2:
                    return [float("".join(parts))]
                if len(parts[1]) == 3 and 1 <= len(parts[0]) <= 3:
                    return [float(parts[0] + parts[1]), float(parts[0] + "." + parts[1])]
                return [float(parts[0] + "." + parts[1])]
        return [float(t)]
    except ValueError:
        return []


def extract_numbers(text: str, check_only: bool = False) -> list[tuple[str, list[float]]]:
    """[(token, kandidat nilai dasar)]. check_only=True: hanya angka yang layak diperiksa (bukan tanggal/tahun/bilangan kecil)."""
    text = re.sub(r"(?i)\bRp\.?\s*(?=\d)", "Rp ", _DATE.sub(" ", text))
    out = []
    for m in _NUM.finditer(text):
        tok, pct, unit = m.group(1), m.group(2), (m.group(3) or "").lower()
        cands = _candidates(tok)
        if not cands:
            continue
        scale = _UNIT.get(unit, 1.0)
        vals = [c * scale for c in cands]
        has_dec = bool(re.search(r"[.,]\d{1,2}$", tok))
        if check_only:
            if not pct and not has_dec and not unit and all(abs(v) < 100 for v in vals):
                continue                                           # bilangan kecil (jumlah lot, hitungan) tidak diperiksa
            if not pct and not unit and len(cands) == 1 and "." not in tok and "," not in tok and 1900 <= vals[0] <= 2100:
                continue                                           # tahun
        out.append((m.group(0).strip(), vals))
    return out


def registry_values(texts: list[str]) -> list[float]:
    vals: set[float] = set()
    for t in texts:
        for _, cands in extract_numbers(t):
            for v in cands:
                vals.update({v, v * 100, v / 100})
    return sorted(vals)


def untraced(text: str, registry: list[float]) -> list[str]:
    import bisect
    bad = []
    for tok, cands in extract_numbers(text, check_only=True):
        ok = False
        for v in cands:
            tol = max(abs(v) * 0.011, 0.0051)
            i = bisect.bisect_left(registry, v - tol)
            if i < len(registry) and registry[i] <= v + tol:
                ok = True
                break
        if not ok:
            bad.append(tok)
    return bad


def lint_report(text: str, registry: list[float] | None = None) -> dict:
    low = text.lower()
    issues, warns = [], []
    if not re.search(r"bukan nasihat|bukan saran (keuangan|investasi)|bukan rekomendasi (berlisensi|resmi)", low):
        issues.append("tidak ada pernyataan bahwa ini analisis pendukung keputusan dan bukan nasihat keuangan berlisensi")
    if not _MONTH_DATE.search(text):
        issues.append("tidak ada tanggal data (mis. 'data s.d. 2026-10-16'): setiap analisis harus menyebut tanggal datanya")
    if not re.search(r"\bsumber\b", low):
        issues.append("tidak ada bagian/penyebutan Sumber data")
    if "risiko" not in low:
        issues.append("tidak membahas risiko")
    if not re.search(r"keterbatasan|belum dianalisis|batasan data|tidak tersedia|belum tersedia", low):
        issues.append("tidak ada keterbatasan data/analisis (apa yang BELUM dianalisis atau datanya belum ada)")
    bad = CERTAINTY.search(text)
    if bad:
        issues.append(f"memakai kata kepastian '{bad.group(0)}': ganti dengan rentang, keyakinan, dan syarat pembatalan")
    if RECO.search(text):
        if not re.search(r"pesimis|skenario negatif|bear case|skenario buruk|skenario turun", low):
            issues.append("ada rekomendasi/kandidat tetapi tidak ada skenario pesimis/negatif (bear case)")
        if not re.search(r"pembatalan|invalidasi|stop|batas rugi|cut ?loss", low):
            issues.append("ada rekomendasi/kandidat tetapi tidak ada syarat pembatalan/stop")
    if re.search(r"undervalued|overvalued|murah|mahal|nilai wajar|margin of safety", low) and "asumsi" not in low:
        issues.append("menyatakan valuasi (murah/mahal/nilai wajar) tanpa menuliskan asumsi")
    if registry is not None:
        nums = extract_numbers(text, check_only=True)
        bad_nums = untraced(text, registry)
        if nums and len(bad_nums) / len(nums) > 0.5 and len(bad_nums) >= 4:
            issues.append(f"{len(bad_nums)} dari {len(nums)} angka tidak dapat ditelusuri ke keluaran tool (contoh: {', '.join(bad_nums[:5])}): hitung lewat tool atau hapus")
        elif bad_nums:
            warns.append(f"{len(bad_nums)} angka tidak ditemukan di keluaran tool sesi ini (turunan hitungan sendiri atau salah?): {', '.join(bad_nums[:8])}. Pastikan dihitung dengan benar.")
    return {"lolos": not issues, "masalah": issues, "peringatan": warns}


def render(r: dict) -> str:
    if r["lolos"]:
        return "LOLOS: struktur dan penelusuran angka memenuhi standar." + ("".join(f"\n⚠ {w}" for w in r["peringatan"]))
    return "PERLU PERBAIKAN:\n- " + "\n- ".join(r["masalah"]) + "".join(f"\n⚠ {w}" for w in r["peringatan"])
