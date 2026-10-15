"""Pemeriksa spesifikasi dokumen: sitasi APA (Penulis, tahun) harus cocok dengan Daftar Pustaka."""
from __future__ import annotations

import re

_PAREN = re.compile(r"\(([^()]*\b(?:19|20)\d{2}[a-z]?[^()]*)\)")
_YEAR = re.compile(r"\b((?:19|20)\d{2})[a-z]?\b")
_NUMERIC_CLAIM = re.compile(r"(\d+[.,]?\d*\s?(%|persen|triliun|miliar|juta|ribu)|\bRp\s?\d)", re.I)
_CITE_ANY = re.compile(r"\([^()]*\b(?:19|20)\d{2}[a-z]?[^()]*\)")


def _texts(spec: dict):
    for b in spec.get("blocks", []):
        if "p" in b:
            yield b["p"]
        for k in ("bullets", "numbered"):
            for it in b.get(k, []):
                yield it
        if "table" in b:
            for row in b["table"].get("rows", []):
                for c in row:
                    yield str(c)


def lint_doc_spec(spec: dict) -> list[str]:
    issues: list[str] = []
    refs = [r.lower() for r in spec.get("references", [])]
    cited: set[int] = set()
    texts = list(_texts(spec))
    for t in texts:
        for m in _PAREN.finditer(t):
            for part in m.group(1).split(";"):
                ym = _YEAR.search(part)
                if not ym:
                    continue
                author = part[: ym.start()].strip(" ,").lower()
                author = re.split(r"\s*(?:&|dan|and|et al\.?)\s*|,", author)[0].strip()
                if len(author) < 2:
                    continue
                hit = [i for i, r in enumerate(refs) if r.startswith(author[:6]) and ym.group(1) in r]
                if not hit:
                    issues.append(f"Sitasi ({part.strip()}) tidak ada di Daftar Pustaka.")
                cited.update(hit)
    for i, r in enumerate(spec.get("references", [])):
        if i not in cited:
            issues.append(f"Pustaka tidak pernah disitasi: {r[:70]}")
        if not re.search(r"https?://|doi", r, re.I):
            issues.append(f"Pustaka tanpa URL/DOI: {r[:70]}")
    for t in texts:
        if _NUMERIC_CLAIM.search(t) and not _CITE_ANY.search(t) and len(t) > 60:
            issues.append(f"Klaim berangka tanpa sitasi: {t[:80]}")
    if not spec.get("references"):
        issues.append("Daftar Pustaka kosong.")
    for b in spec.get("blocks", []):
        if "table" in b and not b["table"].get("caption"):
            issues.append("Ada tabel tanpa keterangan (caption).")
        if "figure" in b and not b["figure"].get("caption"):
            issues.append("Ada gambar tanpa keterangan (caption).")
    return issues
