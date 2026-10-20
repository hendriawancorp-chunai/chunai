"""Unduh berkas (PDF/XLSX/CSV) dari domain yang diizinkan ke workspace/masukan/unduhan/. Pagar: skema http/https, domain terdaftar/disetujui pengguna,
alamat privat ditolak, pengalihan diperiksa per langkah, jenis berkas diverifikasi dari isinya, ukuran dibatasi."""
from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from .policy import host_allowed, is_public_host

MAX_BYTES = 30 * 1024 * 1024
MAX_REDIRECTS = 3
EXT_BY_MAGIC = ((b"%PDF-", ".pdf"), (b"PK\x03\x04", ".xlsx"))


class DownloadError(ValueError):
    ...


def _safe_name(name: str, ext: str) -> str:
    stem = re.sub(r"[^\w.\-]", "_", Path(name).stem)[:60] or "berkas"
    return stem + ext


def _check_host(url: str, allowed: set[str]) -> None:
    p = urlparse(url)
    if p.scheme not in ("http", "https"):
        raise DownloadError(f"Skema '{p.scheme}' ditolak (hanya http/https).")
    if not host_allowed(url, allowed):
        raise DownloadError(f"Domain '{p.hostname}' belum diizinkan (minta pengguna menyetujui lewat kartu).")
    if not is_public_host(url) and not host_allowed(url, allowed):
        raise DownloadError("Alamat internal/privat ditolak.")


def download(url: str, dest_dir: Path, allowed: set[str], name: str = "", client: httpx.Client | None = None) -> Path:
    own = client is None
    client = client or httpx.Client(timeout=60, follow_redirects=False, headers={"User-Agent": "ChunAI/1.0 (pengunduh berkas, pengguna menyetujui domain)"})
    try:
        cur = url
        for _ in range(MAX_REDIRECTS + 1):
            _check_host(cur, allowed)
            with client.stream("GET", cur) as r:
                if r.is_redirect:
                    cur = str(httpx.URL(cur).join(r.headers.get("location", "")))
                    continue
                if r.status_code != 200:
                    raise DownloadError(f"Server menjawab HTTP {r.status_code} (situs mungkin membatasi akses otomatis; unduh sendiri lalu unggah ke bot).")
                chunks, total = [], 0
                for chunk in r.iter_bytes():
                    total += len(chunk)
                    if total > MAX_BYTES:
                        raise DownloadError(f"Berkas melebihi {MAX_BYTES // 1024 // 1024} MB.")
                    chunks.append(chunk)
                data = b"".join(chunks)
                break
        else:
            raise DownloadError("Terlalu banyak pengalihan.")
        ext = next((e for magic, e in EXT_BY_MAGIC if data.startswith(magic)), "")
        if not ext:
            head = data[:2000].decode("utf-8", "ignore")
            if head.lstrip().lower().startswith(("<!doctype html", "<html")):
                raise DownloadError("Yang diterima halaman web (HTML), bukan berkas data. Mungkin perlu login/captcha atau tautan salah; unduh sendiri lalu unggah.")
            if "," in head or ";" in head or "\t" in head:
                ext = ".csv"
            else:
                raise DownloadError("Jenis berkas tidak dikenali (didukung: PDF, XLSX, CSV).")
        base = name or unquote(Path(urlparse(cur).path).name) or "berkas"
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / _safe_name(base, ext)
        i = 2
        while path.exists():
            path = dest_dir / f"{path.stem.rsplit('_v', 1)[0]}_v{i}{path.suffix}"
            i += 1
        path.write_bytes(data)
        return path
    except httpx.HTTPError as e:
        raise DownloadError(f"Gagal terhubung ({type(e).__name__}). Periksa internet atau unduh sendiri lalu unggah.") from None
    finally:
        if own:
            client.close()
