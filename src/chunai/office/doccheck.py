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


def _norm(url: str) -> str:
    u = re.sub(r"^https?://(www\.)?", "", url.strip().lower())
    return u.split("#")[0].rstrip("/")


def reference_urls(spec: dict) -> list[str]:
    out = []
    for r in spec.get("references", []):
        out += re.findall(r"https?://[^\s)>\]]+", r)
    return out


def source_attention(spec: dict, fetch_log: dict[str, str] | None) -> list[str]:
    """Daftar pustaka yang URL-nya TIDAK pernah berhasil dibuka agen (gagal/tidak dibuka). Bukan galat keras: sumber
    boleh berasal dari data pengguna. Tetapi klaim 'menurut sumber' tanpa membuka sumbernya harus diberi catatan."""
    if fetch_log is None:
        return []
    ok = {_norm(u) for u, st in fetch_log.items() if st == "ok"}
    failed = {_norm(u) for u, st in fetch_log.items() if st == "gagal"}
    notes = []
    for u in reference_urls(spec):
        n = _norm(u)
        if any(n == o or n.startswith(o) or o.startswith(n) for o in ok):
            continue
        status = "GAGAL dibuka" if any(n == f or n.startswith(f) or f.startswith(n) for f in failed) else "tidak pernah dibuka"
        notes.append(f"Sumber {status}: {u}")
    return notes


def attention_text(notes: list[str]) -> str:
    if not notes:
        return ""
    return ("PERHATIAN SUMBER (bukan galat, tetapi wajib ditangani):\n- " + "\n- ".join(notes) +
            "\nAturan: untuk sumber yang gagal/tidak dibuka JANGAN menulis 'menurut dokumentasi/sumber resmi' atau angka/rincian yang hanya "
            "berasal dari cuplikan pencarian. Buka sumbernya, atau tandai klaimnya 'belum terverifikasi dari sumber primer' dan cantumkan di "
            "subbagian 'Keterbatasan'. Abaikan peringatan ini hanya bila datanya memang diberikan pengguna.")


def reference_to_text(r) -> str:
    """Terima referensi berbentuk string ATAU objek {author(s), year, title, source/publisher/journal, url/doi} -> string gaya APA."""
    if isinstance(r, str):
        return r
    if not isinstance(r, dict):
        return str(r)
    g = lambda *k: next((str(r[x]).strip() for x in k if r.get(x)), "")
    authors = r.get("authors") or r.get("author") or r.get("penulis") or ""
    if isinstance(authors, list):
        authors = ", ".join(str(a) for a in authors)
    parts = [str(authors).strip().rstrip(".") + "." if authors else "",
             f"({g('year', 'tahun', 'date', 'tanggal') or 't.t.'}).",
             g("title", "judul").rstrip(".") + "." if g("title", "judul") else "",
             g("source", "publisher", "journal", "sumber", "penerbit").rstrip(".") + "." if g("source", "publisher", "journal", "sumber", "penerbit") else "",
             g("url", "link", "doi")]
    return " ".join(x for x in parts if x)


def normalize_spec(spec: dict) -> dict:
    """Salinan spesifikasi dengan references dinormalkan ke string."""
    out = dict(spec)
    if "references" in out:
        out["references"] = [reference_to_text(r) for r in (out["references"] or [])]
    return out
