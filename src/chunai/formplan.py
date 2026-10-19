"""Peta soal/form dan rencana isian (tabel jawaban yang ditinjau pengguna). Murni: tanpa browser, mudah diuji."""
from __future__ import annotations

import json
import re
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

# Isian yang berisi data pribadi: ditandai di tinjauan dan kartu kirim (tidak diblokir; pengguna yang memutuskan)
_PII = re.compile(
    r"\b(nik|ktp|npwp|kk|kartu keluarga|ibu kandung|paspor|passport|no\.? ?rek|rekening|tanggal lahir|tempat lahir|alamat|telepon|telp|hp|"
    r"no\.? ?hp|whatsapp|agama|golongan darah|status (pernikahan|perkawinan)|nama (ayah|ibu)|suami|istri|anak|gaji|salary|bpjs|sim)\b", re.I)
KEYAKINAN = ("tinggi", "sedang", "rendah", "tidak_ada")
STATUS = ("usulan", "disetujui", "dilewati")
MAX_ITEMS = 300


class PlanError(ValueError):
    ...


def is_pii(text: str) -> bool:
    return bool(_PII.search(text or ""))


def norm(s) -> str:
    s = str(s or "").replace("’", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", re.sub(r"[*:]+$", "", s.strip())).strip().lower()


# =====================================================================
# Peta soal dari elemen halaman
# =====================================================================
def build_questions(els: list[dict]) -> list[dict]:
    qs: list[dict] = []
    groups: dict[tuple, dict] = {}
    for e in els:
        tag, typ, role = e.get("tag", ""), e.get("type", ""), e.get("role", "")
        label = str(e.get("label", "")).strip()
        base = {"wajib": bool(e.get("required")), "maxlen": e.get("maxlen", 0), "iframe": bool(e.get("iframe"))}
        if e.get("disabled") or tag in ("button", "a") or role in ("button", "tab", "menuitem", "switch") or typ in ("submit", "button", "reset", "image"):
            continue
        if typ == "radio" or role == "radio":
            soal = str(e.get("group") or "").strip() or str(e.get("name") or "") or "(soal tanpa teks)"
            key = ("radio", e.get("name") or soal, soal)
            q = groups.get(key)
            if q is None:
                q = groups[key] = {**base, "jenis": "pilihan_ganda", "soal": soal, "opsi": [], "idx": None}
                qs.append(q)
            q["wajib"] = q["wajib"] or base["wajib"]
            q["opsi"].append({"idx": e["idx"], "label": label or str(e.get("value", "")), "terpilih": bool(e.get("checked"))})
        elif typ == "checkbox" or role == "checkbox":
            grp = str(e.get("group") or "").strip()
            if grp:
                key = ("cb", grp)
                q = groups.get(key)
                if q is None:
                    q = groups[key] = {**base, "jenis": "pilihan_jamak", "soal": grp, "opsi": [], "idx": None}
                    qs.append(q)
                q["opsi"].append({"idx": e["idx"], "label": label, "terpilih": bool(e.get("checked"))})
            else:
                qs.append({**base, "jenis": "centang", "soal": label or "(kotak centang)", "opsi": [], "idx": e["idx"],
                           "nilai": "ya" if e.get("checked") else "tidak"})
        elif tag == "select":
            qs.append({**base, "jenis": "dropdown", "soal": label or str(e.get("name", "")) or "(dropdown)", "idx": e["idx"],
                       "opsi": [{"idx": None, "label": o, "terpilih": o == e.get("value")} for o in e.get("options", [])], "nilai": e.get("value", "")})
        elif typ == "password":
            qs.append({**base, "jenis": "sandi", "soal": label or "(kata sandi)", "idx": e["idx"], "opsi": [], "catatan": "diisi pengguna sendiri"})
        elif typ == "file":
            qs.append({**base, "jenis": "unggah", "soal": label or "(unggah berkas)", "idx": e["idx"], "opsi": [], "catatan": "pakai unggah_berkas (kartu izin)"})
        elif role == "combobox" or role == "option":
            qs.append({**base, "jenis": "dropdown_kustom", "soal": label or "(pilihan kustom)", "idx": e["idx"], "opsi": [],
                       "catatan": "pilih lewat klik; setiap opsi muncul setelah dibuka"})
        elif tag == "textarea" or e.get("ce") or role == "textbox":
            qs.append({**base, "jenis": "essay", "soal": label or str(e.get("name", "")) or "(isian panjang)", "idx": e["idx"], "opsi": [],
                       "nilai": e.get("value", "")})
        elif tag == "input":
            qs.append({**base, "jenis": "isian", "soal": label or str(e.get("name", "")) or "(isian)", "idx": e["idx"], "opsi": [],
                       "tipe": typ or "text", "nilai": e.get("value", "")})
    for n, q in enumerate(qs, 1):
        q["no"] = n
        q["sensitif"] = is_pii(q["soal"])
        if q["jenis"] in ("pilihan_ganda", "pilihan_jamak"):
            sel = [o["label"] for o in q["opsi"] if o["terpilih"]]
            q["nilai"] = "; ".join(sel)
    return qs


def render_questions(qs: list[dict], url: str = "", title: str = "") -> str:
    lines = [f"URL: {url}", f"JUDUL: {title}", f"{len(qs)} butir isian terdeteksi:"]
    for q in qs:
        flags = ["wajib"] if q.get("wajib") else []
        if q.get("maxlen"):
            flags.append(f"maks {q['maxlen']} karakter")
        if q.get("sensitif"):
            flags.append("⚠ DATA PRIBADI")
        if q.get("iframe"):
            flags.append("iframe")
        head = f"Q{q['no']} [{q['jenis']}]" + (f" ({', '.join(flags)})" if flags else "") + f" {q['soal']}"
        if q.get("idx") is not None:
            head += f"  [idx {q['idx']}]"
        lines.append(head)
        if q["jenis"] in ("pilihan_ganda", "pilihan_jamak"):
            lines.append("     " + "  ".join(f"[{o['idx']}] {o['label']}{' ✔' if o['terpilih'] else ''}" for o in q["opsi"]))
        elif q["jenis"] == "dropdown":
            lines.append("     opsi: " + " | ".join(o["label"] for o in q["opsi"]))
        if q.get("catatan"):
            lines.append(f"     catatan: {q['catatan']}")
        if q.get("nilai"):
            lines.append(f"     nilai sekarang: {q['nilai'][:120]}")
    return "\n".join(lines)


# =====================================================================
# Rencana isian
# =====================================================================
def _safe_name(n: str) -> str:
    return re.sub(r"[^\w-]", "_", str(n or "rencana"))[:50] or "rencana"


def plan_path(workdir: Path, nama: str) -> Path:
    return Path(workdir) / "rencana" / f"{_safe_name(nama)}.json"


def save_plan(workdir: Path, nama: str, items: list[dict], url: str = "") -> dict:
    if not isinstance(items, list) or not items:
        raise PlanError("'items' harus daftar yang tidak kosong.")
    if len(items) > MAX_ITEMS:
        raise PlanError(f"Terlalu banyak butir (maks {MAX_ITEMS}).")
    out, errors = [], []
    for n, it in enumerate(items, 1):
        if not isinstance(it, dict) or not str(it.get("soal", "")).strip():
            errors.append(f"butir {n}: 'soal' kosong.")
            continue
        kek = str(it.get("keyakinan", "sedang")).strip().lower()
        if kek not in KEYAKINAN:
            errors.append(f"butir {n}: 'keyakinan' harus salah satu dari {', '.join(KEYAKINAN)}.")
            continue
        jaw = it.get("jawaban")
        if kek == "tidak_ada":
            jaw = None
        elif jaw in (None, "", []):
            errors.append(f"butir {n}: 'jawaban' kosong (pakai keyakinan='tidak_ada' bila tidak ada dasar).")
            continue
        out.append({"no": int(it.get("no") or n), "soal": str(it["soal"]).strip(), "jenis": str(it.get("jenis", "")),
                    "jawaban": jaw, "dasar": str(it.get("dasar", ""))[:400], "keyakinan": kek,
                    "sensitif": is_pii(it["soal"]) or bool(it.get("sensitif")),
                    "status": "dilewati" if kek == "tidak_ada" else "usulan"})
    if errors:
        raise PlanError("Rencana tidak disimpan. Perbaiki:\n- " + "\n- ".join(errors))
    plan = {"nama": _safe_name(nama), "url": url, "dibuat": datetime.now().isoformat(timespec="seconds"), "items": out}
    p = plan_path(workdir, nama)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")
    return plan


def load_plan(workdir: Path, nama: str) -> dict:
    p = plan_path(workdir, nama)
    if not p.is_file():
        raise PlanError(f"Rencana '{nama}' tidak ada. Buat dulu dengan simpan_rencana.")
    return json.loads(p.read_text(encoding="utf-8"))


def _write(workdir: Path, plan: dict) -> None:
    plan_path(workdir, plan["nama"]).write_text(json.dumps(plan, ensure_ascii=False, indent=1), encoding="utf-8")


def update_item(workdir: Path, nama: str, no: int, jawaban=None, status: str | None = None, dasar: str | None = None) -> dict:
    plan = load_plan(workdir, nama)
    it = next((i for i in plan["items"] if i["no"] == int(no)), None)
    if it is None:
        raise PlanError(f"Butir no {no} tidak ada.")
    if jawaban not in (None, "", []):
        it["jawaban"] = jawaban
        it["keyakinan"] = "sedang" if it["keyakinan"] == "tidak_ada" else it["keyakinan"]
        it["status"] = "usulan"                            # diubah -> harus disetujui ulang
        it["diubah_pengguna"] = True
    if status:
        if status not in STATUS:
            raise PlanError(f"status harus salah satu dari {', '.join(STATUS)}.")
        it["status"] = status
    if dasar is not None:
        it["dasar"] = str(dasar)[:400]
    _write(workdir, plan)
    return it


def approve(workdir: Path, nama: str) -> tuple[int, int]:
    """Setujui semua butir 'usulan'. Mengembalikan (disetujui, dilewati/tanpa dasar)."""
    plan = load_plan(workdir, nama)
    ok = skipped = 0
    for it in plan["items"]:
        if it["status"] == "usulan" and it["jawaban"] not in (None, "", []):
            it["status"] = "disetujui"
            ok += 1
        elif it["status"] == "dilewati":
            skipped += 1
    _write(workdir, plan)
    return ok, skipped


def render_plan(plan: dict) -> str:
    lines = [f"Rencana '{plan['nama']}' ({len(plan['items'])} butir) {plan.get('url', '')}", "",
             "| No | Soal | Jawaban | Dasar | Keyakinan | Status |", "|---|---|---|---|---|---|"]
    for it in plan["items"]:
        jaw = "; ".join(map(str, it["jawaban"])) if isinstance(it["jawaban"], list) else (it["jawaban"] if it["jawaban"] is not None else "—")
        flag = " ⚠PRIBADI" if it.get("sensitif") else ""
        lines.append(f"| {it['no']} | {it['soal'][:70]}{flag} | {str(jaw)[:120].replace('|', '/')} | {it['dasar'][:70].replace('|', '/')} | "
                     f"{it['keyakinan']} | {it['status']} |")
    low = [it["no"] for it in plan["items"] if it["keyakinan"] in ("rendah", "tidak_ada")]
    if low:
        lines.append(f"\nPerlu perhatian (keyakinan rendah/tanpa dasar): no {', '.join(map(str, low))}")
    return "\n".join(lines)


# =====================================================================
# Pencocokan rencana <-> halaman
# =====================================================================
def match_question(item: dict, qs: list[dict]) -> dict | None:
    target = norm(item["soal"])
    best, score = None, 0.0
    for q in qs:
        s = norm(q["soal"])
        r = 1.0 if s == target else SequenceMatcher(None, s, target).ratio()
        if r > score:
            best, score = q, r
    return best if score >= 0.8 else None


def _opt_matches(label: str, ans: str) -> bool:
    l, a = norm(label), norm(ans)
    if not a:
        return False
    if l == a:
        return True
    m = re.match(r"^([a-z0-9])[\.\)]\s", l + " ")
    if m and len(a) == 1 and m.group(1) == a:             # jawaban 'B' cocok dengan opsi 'B. Biasa'
        return True
    return False


def _find_option(q: dict, ans: str) -> dict | None:
    cands = [o for o in q["opsi"] if _opt_matches(o["label"], ans)]
    if not cands:
        cands = [o for o in q["opsi"] if norm(ans) and norm(ans) in norm(o["label"])]
    return cands[0] if len(cands) == 1 else None


def actions_for(item: dict, q: dict) -> tuple[list[tuple[int, str]], str | None]:
    """[(idx, nilai)] untuk mengisi butir; atau ([], alasan) bila tidak bisa."""
    jaw = item["jawaban"]
    j = q["jenis"]
    if j in ("sandi", "unggah", "dropdown_kustom"):
        return [], f"jenis '{j}' tidak diisi otomatis ({q.get('catatan', '')})"
    if j == "pilihan_ganda":
        o = _find_option(q, str(jaw if not isinstance(jaw, list) else jaw[0]))
        return ([(o["idx"], "ya")], None) if o else ([], f"opsi '{jaw}' tidak ditemukan/ambigu di {[x['label'] for x in q['opsi']]}")
    if j == "pilihan_jamak":
        want = jaw if isinstance(jaw, list) else [s for s in re.split(r"\s*;\s*", str(jaw)) if s]
        acts = []
        for w in want:
            o = _find_option(q, w)
            if not o:
                return [], f"opsi '{w}' tidak ditemukan/ambigu"
            acts.append((o["idx"], "ya"))
        for o in q["opsi"]:                                  # lepas centang yang tidak diinginkan
            if o["terpilih"] and o["idx"] not in {a[0] for a in acts}:
                acts.append((o["idx"], "tidak"))
        return acts, None
    if j == "centang":
        return [(q["idx"], "ya" if norm(jaw) in ("ya", "true", "centang", "1", "yes") else "tidak")], None
    if j == "dropdown":
        o = _find_option(q, str(jaw))
        return ([(q["idx"], o["label"])], None) if o else ([], f"opsi '{jaw}' tidak ada. Pilihan: {[x['label'] for x in q['opsi']]}")
    text = "; ".join(map(str, jaw)) if isinstance(jaw, list) else str(jaw)
    if q.get("maxlen") and len(text) > q["maxlen"]:
        return [], f"jawaban {len(text)} karakter melebihi batas {q['maxlen']}"
    return [(q["idx"], text)], None


def compare(plan: dict, qs: list[dict]) -> list[str]:
    """Bandingkan jawaban yang DISETUJUI dengan isi halaman sekarang. Daftar masalah (kosong = sesuai)."""
    issues, used = [], set()
    for it in plan["items"]:
        if it["status"] != "disetujui":
            continue
        q = match_question(it, qs)
        if q is None:
            issues.append(f"no {it['no']} '{it['soal'][:50]}': tidak ditemukan di halaman ini (mungkin di halaman lain).")
            continue
        used.add(q["no"])
        jaw = it["jawaban"]
        if q["jenis"] in ("pilihan_ganda", "pilihan_jamak"):
            want = jaw if isinstance(jaw, list) else ([jaw] if q["jenis"] == "pilihan_ganda" else re.split(r"\s*;\s*", str(jaw)))
            wanted = {o["idx"] for w in want if (o := _find_option(q, str(w)))}
            have = {o["idx"] for o in q["opsi"] if o["terpilih"]}
            if wanted != have:
                issues.append(f"no {it['no']} '{it['soal'][:50]}': rencana {want}, halaman '{q['nilai'] or '(kosong)'}'.")
        elif q["jenis"] == "centang":
            if (norm(jaw) in ("ya", "true", "centang", "1", "yes")) != (q.get("nilai") == "ya"):
                issues.append(f"no {it['no']} '{it['soal'][:50]}': centang tidak sesuai rencana.")
        elif q["jenis"] in ("sandi", "unggah", "dropdown_kustom"):
            issues.append(f"no {it['no']} '{it['soal'][:50]}': jenis '{q['jenis']}' harus diperiksa manual.")
        else:
            want = "; ".join(map(str, jaw)) if isinstance(jaw, list) else str(jaw)
            if norm(want) != norm(q.get("nilai", "")):
                issues.append(f"no {it['no']} '{it['soal'][:50]}': rencana '{want[:60]}', halaman '{str(q.get('nilai', ''))[:60] or '(kosong)'}'.")
    for q in qs:
        if q["no"] not in used and q.get("wajib") and q["jenis"] not in ("sandi", "unggah") and not q.get("nilai"):
            issues.append(f"WAJIB belum terisi dan tidak ada di rencana: '{q['soal'][:60]}'.")
    return issues
