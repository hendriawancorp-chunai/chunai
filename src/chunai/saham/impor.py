"""Impor berkas harga (CSV/XLSX hasil ekspor platform) ke format baku, dengan pemetaan kolom dan deteksi format angka/tanggal."""
from __future__ import annotations

import csv
import io
import re
from pathlib import Path

import pandas as pd

from .store import SahamError

ALIAS = {
    "date": {"date", "tanggal", "tgl", "datetime", "waktu", "time", "tanggalperdagangan", "tradedate"},
    "open": {"open", "pembukaan", "buka", "openprice", "hargapembukaan", "hargabuka"},
    "high": {"high", "tertinggi", "hi", "highprice", "hargatertinggi"},
    "low": {"low", "terendah", "lo", "lowprice", "hargaterendah"},
    "close": {"close", "penutupan", "tutup", "last", "closeprice", "lastprice", "hargapenutupan", "hargatutup", "terakhir"},
    "volume": {"volume", "vol", "volumelembar", "jumlahvolume", "volumesaham", "volumeshares"},
}
_MONTHS = {"jan": "Jan", "feb": "Feb", "mar": "Mar", "apr": "Apr", "mei": "May", "jun": "Jun", "jul": "Jul", "agu": "Aug", "agt": "Aug", "ags": "Aug",
           "sep": "Sep", "okt": "Oct", "nov": "Nov", "des": "Dec"}
MAX_ROWS = 20000


def _key(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _read_raw(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, header=None, dtype=str)
    if ext in (".csv", ".tsv", ".txt"):
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:4000], delimiters=",;\t|")
            sep = dialect.delimiter
        except csv.Error:
            sep = "\t" if ext == ".tsv" else ","
        return pd.read_csv(io.StringIO(text), sep=sep, header=None, dtype=str, skip_blank_lines=True, engine="python", on_bad_lines="skip")
    raise SahamError(f"Format {ext or '(tanpa ekstensi)'} tidak didukung (CSV, TSV, XLSX).")


def _find_header(raw: pd.DataFrame) -> tuple[int, dict[str, str]]:
    best, best_n, best_map = 0, 0, {}
    for i in range(min(20, len(raw))):
        m: dict[str, str] = {}
        for col, v in raw.iloc[i].items():
            k = _key(v)
            for std, names in ALIAS.items():
                if k in names and std not in m:
                    m[std] = col
        if len(m) > best_n:
            best, best_n, best_map = i, len(m), m
    if "date" not in best_map or "close" not in best_map:
        raise SahamError("Kolom tanggal dan penutupan (close) tidak terdeteksi di 20 baris pertama. Sebutkan pemetaan kolom lewat parameter 'kolom'.")
    return best, best_map


def _num_format(vals: pd.Series) -> str:
    """'en' (1,234.56), 'id' (1.234,56), atau 'plain'/'ambigu'."""
    s = vals.dropna().astype(str).str.replace(r"[^\d.,\-]", "", regex=True)
    both = s[s.str.contains(r"\.") & s.str.contains(",")]
    if len(both):
        last = both.iloc[0]
        return "id" if last.rfind(",") > last.rfind(".") else "en"
    dots = s[s.str.contains(r"\.") & ~s.str.contains(",")]
    commas = s[s.str.contains(",") & ~s.str.contains(r"\.")]
    if len(dots) and dots.str.count(r"\.").ge(2).any():
        return "id"                                           # lebih dari satu titik = pemisah ribuan
    if len(commas) and commas.str.count(",").ge(2).any():
        return "en"                                           # lebih dari satu koma = pemisah ribuan
    thou = r"^-?\d{1,3}([.,]\d{3})+$"
    if len(commas) and (~commas.str.match(thou)).any():
        return "id"                                           # koma dengan bukan 3 digit = desimal
    if len(dots) and (~dots.str.match(thou)).any():
        return "en"                                           # titik dengan bukan 3 digit = desimal
    if len(commas) or len(dots):
        return "ambigu"                                       # semua pola ribuan: 1.234 bisa 1234 atau 1,234
    return "plain"


def _to_num(vals: pd.Series, fmt: str) -> pd.Series:
    s = vals.astype(str).str.strip().str.replace(r"[^\d.,\-]", "", regex=True)
    if fmt == "id":
        s = s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    elif fmt in ("en", "plain"):
        s = s.str.replace(",", "", regex=False)
    return pd.to_numeric(s.replace({"": None, "-": None}), errors="coerce")


def _parse_dates(vals: pd.Series, fmt_tgl: str = "auto") -> tuple[pd.Series, str]:
    s = vals.astype(str).str.strip()
    for k, v in _MONTHS.items():
        s = s.str.replace(rf"(?i)\b{k}[a-z]*\b", v, regex=True)
    if fmt_tgl == "auto":
        if s.str.match(r"^\d{4}-\d{1,2}-\d{1,2}").all():
            return pd.to_datetime(s, errors="coerce"), "YYYY-MM-DD"
        parts = s.str.extract(r"^(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})")
        if parts.notna().all().all():
            a, b = parts[0].astype(int), parts[1].astype(int)
            if (a > 12).any():
                return pd.to_datetime(s, dayfirst=True, errors="coerce", format="mixed"), "DD/MM/YYYY"
            if (b > 12).any():
                return pd.to_datetime(s, dayfirst=False, errors="coerce", format="mixed"), "MM/DD/YYYY"
            return pd.to_datetime(s, dayfirst=True, errors="coerce", format="mixed"), "DD/MM/YYYY (diasumsikan, semua angka <= 12)"
        return pd.to_datetime(s, errors="coerce", format="mixed"), "otomatis"
    return pd.to_datetime(s, dayfirst=(fmt_tgl == "dmy"), errors="coerce", format="mixed"), fmt_tgl


def parse_file(path: Path, kolom: dict[str, str] | None = None, format_angka: str = "auto", format_tanggal: str = "auto") -> tuple[pd.DataFrame, dict]:
    raw = _read_raw(Path(path))
    if raw.empty:
        raise SahamError("Berkas kosong.")
    hdr, mapping = _find_header(raw) if not kolom else (0, {})
    if kolom:
        # pemetaan manual: nilai = nama kolom di berkas; cari baris header yang memuatnya
        for i in range(min(20, len(raw))):
            row = {_key(v): c for c, v in raw.iloc[i].items()}
            if all(_key(v) in row for v in kolom.values()):
                hdr = i
                mapping = {std: row[_key(v)] for std, v in kolom.items()}
                break
        else:
            raise SahamError("Nama kolom pada 'kolom' tidak ditemukan di baris header berkas.")
    body = raw.iloc[hdr + 1:].reset_index(drop=True)
    notes, report = [], {"kolom": {std: str(raw.iloc[hdr][col]) for std, col in mapping.items()}}
    out = pd.DataFrame(index=body.index)
    d, dfmt = _parse_dates(body[mapping["date"]], format_tanggal)
    out["date"] = d
    report["format_tanggal"] = dfmt
    if "diasumsikan" in dfmt:
        notes.append("Format tanggal diasumsikan DD/MM/YYYY; periksa contoh tanggal. Bila salah, ulangi dengan format_tanggal='mdy'.")
    numfmt = {}
    detected = {std: _num_format(body[mapping[std]]) for std in ("open", "high", "low", "close", "volume") if std in mapping}
    definit = [f for f in detected.values() if f in ("id", "en")]
    file_fmt = definit[0] if definit and len(set(definit)) == 1 else None       # format angka seragam antar kolom berkas
    for std in ("open", "high", "low", "close", "volume"):
        if std not in mapping:
            continue
        col = body[mapping[std]]
        f = format_angka if format_angka in ("id", "en") else detected[std]
        if f == "ambigu" and file_fmt:
            f = file_fmt
            notes.append(f"Format angka kolom '{std}' disimpulkan dari kolom lain di berkas ({'titik=ribuan' if file_fmt == 'id' else 'koma=ribuan'}).")
        if f == "ambigu":
            raise SahamError(f"Format angka kolom '{std}' ambigu (pola 1.234 / 1,234 bisa ribuan atau desimal). Ulangi dengan format_angka='id' (1.234,56) atau 'en' (1,234.56).")
        numfmt[std] = f
        out[std] = _to_num(col, f)
    report["format_angka"] = numfmt
    out = out.dropna(subset=["date", "close"])
    if out.empty:
        raise SahamError("Tidak ada baris valid (tanggal dan close terbaca) setelah penguraian.")
    dup = int(out["date"].duplicated().sum())
    if dup:
        notes.append(f"{dup} tanggal ganda: dipakai baris terakhir.")
    out = out.drop_duplicates("date", keep="last").sort_values("date").set_index("date")
    for c in ("open", "high", "low"):
        if c not in out:
            out[c] = float("nan")
    if "volume" not in out:
        out["volume"] = float("nan")
    if out[["open", "high", "low"]].isna().all().all():
        notes.append("Hanya harga penutupan tersedia: ATR/level kunci berbasis high-low tidak dapat dihitung presisi.")
    if len(out) > MAX_ROWS:
        raise SahamError(f"Terlalu banyak baris ({len(out)}; maks {MAX_ROWS}).")
    report["baris"], report["periode"] = int(len(out)), f"{out.index.min().date()}..{out.index.max().date()}"
    report["catatan"] = notes
    return out[["open", "high", "low", "close", "volume"]], report
