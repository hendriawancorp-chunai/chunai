# Catatan Proyek ChunAI (serah-terima antar sesi)

Dibuat pada 15 Oktober 2026 setelah sesi pembangunan pertama. Repo: `hendriawancorp-chunai/chunai` (private), cabang `main`.
Tidak memuat rahasia (token ada di `.env` pengguna, tidak pernah di repo).

## 1. Tujuan
Asisten kerja pribadi ("ChunAI") yang menjalankan perintah pengguna: mencari informasi/data, analisis data, menyusun kajian,
menyusun presentasi, membuat media grafis (gambar/video), dan pekerjaan berbasis web (membaca, mengisi, menjawab) yang
**eksekusi akhirnya selalu diminta review dan izin terlebih dahulu**. Dioperasikan lewat Telegram dan Web.

## 2. Status

| Bagian | Status | Catatan |
|---|---|---|
| Inti agen (Claude Agent SDK), approval gate, audit | ✅ | hook `PreToolUse` menggerbangi SEMUA tool |
| Riset bersitasi + pemeriksa laporan | ✅ | sumber primer terbatas oleh akses jaringan sesi cloud |
| Analisis data (`profil_data`, `buat_grafik`, `jalankan_python` sandbox) | ✅ | angka diverifikasi ulang; sandbox tanpa internet |
| Dokumen DOCX + presentasi PPTX bergaya referensi pengguna | ✅ | tema default biru korporat; logo/font belum |
| Media: gambar (HTML→PNG), edit gambar, video (ffmpeg) | ✅ | gambar AI fotorealistik BELUM (butuh penyedia eksternal) |
| Web Agent (Playwright, draf→review→izin→kirim) | ✅ di form tiruan | belum diuji di situs nyata + login manual |
| Antarmuka Web | ✅ | teruji headless + agen asli |
| Antarmuka Telegram | ✅ di Telegram asli | `/start`, `/id`, `/status`, `/stop`, tombol izin, unggah file, kirim file hasil |
| Pemasangan Windows (WSL2) | ✅ | `install_wsl.sh`, `chunai doctor/auth/setup-telegram` |
| Operasional (cadangan, audit, batas harian, daftar keamanan) | ✅ | `docs/OPERASIONAL.md` |
| **Tahap 3: penyesuaian ke pekerjaan pengguna** | ⏳ | lihat bagian 7 |

Terakhir: 148 tes lolos; commit `6a50899` (16 Okt 2026).

## 3. Arsitektur (modul utama di `src/chunai/`)
- `agent.py` orkestrator `ChunAI` (hook izin, MCP in-process, konteks waktu, `outbox` untuk `kirim_file`); `agents.py` subagen peneliti/analis.
- `policy.py` baca bebas / tulis minta izin / berbahaya ditolak; Bash baca-saja aman otomatis; `approval.py` gate + pratinjau nyata; `audit.py`.
- `tools.py` (laporan, data, `jalankan_python`, `kirim_file`), `office/` (docx/pptx/render/doccheck/tema), `media.py` + `media_tools.py`,
  `browser.py` (Web Agent), `sandbox.py`, `resources.py` (satu pekerjaan berat sekaligus).
- `interfaces/core.py` sesi per pengguna + `ApprovalBroker` (tidak dijawab = ditolak) + pengiriman file; `telegram.py`, `web.py` (+ `static/index.html`).
- Operasional: `cli.py`, `doctor.py`, `auth.py`, `setup_telegram.py`, `envfile.py`, `usage.py`, `timeutil.py`, `scripts/`.

## 4. Keputusan penting dan alasannya
1. **Berjalan di komputer pengguna (Windows + WSL2), bukan sesi cloud**: mesin cloud tidur tiap giliran selesai, bot mati. WSL2 dipilih karena sandbox
   (`unshare -rn`) hanya tersedia di Linux/WSL2; Windows asli tidak mendukung.
2. **Langganan Claude lewat token `chunai auth`** (disimpan otomatis ke `.env`), bukan kunci API. Untuk server 24 jam kunci API lebih sesuai ketentuan.
3. **Aksi berdampak selalu minta izin**; klik/kirim form tidak punya "selalu izinkan"; pratinjau izin dibaca dari halaman nyata, bukan klaim agen.
4. **Telegram hanya ID pemilik** (terdeteksi otomatis + konfirmasi). Web wajib token, Origin dicek, unduhan bertanda tangan.
5. **File hasil dikirim langsung ke chat**: agen memanggil `kirim_file`; bila tidak, semua file baru di workspace (kecuali folder internal).
6. **Konteks waktu di tiap pesan** (WIB), audit dalam WIB.
7. **Batas pemakaian harian** default setara $20 (pengaman, bukan tagihan pada langganan).
8. VPS ditunda; bila dipakai: min. 2 vCPU / 4 GB RAM (diukur: agen ≈330 MB, Chromium ≈830 MB, LibreOffice ≈220 MB, ffmpeg ≈375 MB).

## 5. Lingkungan pengguna (tanpa data pribadi)
Windows dengan WSL2 Ubuntu; Python 3.14 di dalam WSL; kode di `~/chunai` (diperbarui dari **ZIP GitHub**, bukan git):
`cp -r /mnt/c/Users/<NAMA>/Downloads/chunai-main/. ~/chunai/` (`.env`, `.venv`, `data/` tidak tertimpa). Bot Telegram: `@ChunAI_Assistant_bot`.
Jalankan: `cd ~/chunai && ./scripts/run.sh` (biarkan jendela terbuka). Setiap jendela Ubuntu baru: `source .venv/bin/activate`.

## 5b. Uji lanjutan 16 Oktober 2026 (tugas nyata riset → kajian → presentasi → kirim file)
- Dua kali dijalankan dengan agen asli lewat lapisan sesi: 152 dtk/$0,52 → setelah perbaikan 57 dtk/$0,21. File final terkirim, tanpa versi perantara.
- Klaim bersumber halaman primer Anthropic cocok dengan sumbernya (diperiksa sendiri). Temuan: agen sempat menulis "menurut dokumentasi resmi" untuk
  halaman yang TIDAK bisa dibuka (cuplikan pencarian). Perbaikan: hook WebFetch mencatat `fetch_log` (ok/gagal) + audit `source_opened/source_failed`;
  `buat_dokumen/periksa_dokumen` menampilkan "PERHATIAN SUMBER"; prompt mewajibkan subbagian "Keterbatasan". Setelah perbaikan agen jujur dan menulis keterbatasan.
- Agen sempat men-grep kode ChunAI untuk mencari skema slide dan mengirim referensi berbentuk objek: skema kini ada di deskripsi `buat_presentasi`,
  referensi objek dinormalkan menjadi string APA.
- `modelcontextprotocol.io` tidak terjangkau dari sesi cloud (DNS/proxy); di komputer pengguna tidak dibatasi.

## 6. Pelajaran / kesalahan yang jangan diulang
- Blok multi-baris yang ditempel merusak `read -rsp` → beri **satu baris per kali**; kini `chunai auth` dan `chunai setup-telegram` otomatis.
- `cp -r SRC ~/chunai` ke folder yang sudah ada membuat folder bertingkat → pakai `cp -r SRC/. ~/chunai/`.
- `${VAR:-x}` pada pengecekan rahasia mencetak nilainya → jangan.
- `pkill -f` pola yang cocok dengan perintah sendiri → exit 144.
- `doctor` awalnya menyembunyikan alasan kegagalan Claude; kini menampilkan alasan + batas waktu + bentuk token (aman).
- Agen kadang membuat ulang dokumen sehingga muncul `_2`; pilihan eksplisit `kirim_file` mengalahkan deteksi otomatis.
- Agen pernah menulis nama penulis "ChunAI" dan nomor/caption ganda di spesifikasi → builder kini membersihkan/mengabaikan.
- LibreOffice mengabaikan `effectLst` kosong (bayangan) → hapus `p:style` pada bentuk PPTX.
- Python 3.14: aliran `query()` harus dihabiskan (`aclosing`), jangan `return` di tengah `async for`.

## 7. Langkah berikutnya (Tahap 3 dan seterusnya)
1. **Tema pengguna**: logo, latar sampul, font (mis. Poppins), teks footer (`data/themes/<nama>.json`; skema ada di `office/theme.py`).
   Bahan referensi gaya: artikel pendek (sampul grafis; Executive Summary; bab bernomor; tabel header navy; Daftar Pustaka tanpa nomor)
   dan presentasi 16:9 (kartu KPI, panel biru, tabel bersih, roadmap, heatmap risiko, footer gradasi hijau-biru). Belum ada tipe slide
   **heatmap risiko** dan **gambar latar sampul**.
2. **Satu tugas nyata** dari awal sampai akhir (kajian + presentasi dengan sumber primer dari domain yang diizinkan), nilai terhadap referensi.
3. **Web Agent di situs nyata** dengan login manual (`chunai login` butuh WSLg/Windows 11, atau mode CDP) dan allowlist domain.
4. Backlog: revisi dokumen yang sudah ada (bukan hanya membuat baru), tugas terjadwal/pengingat, gambar AI (butuh penyedia), unggah template
   pengguna (.pptx/.docx), jalankan `pytest` di Python 3.14 pada mesin pengguna, uji akun Telegram lain ditolak di Telegram asli,
   Dockerfile + VPS bila perlu 24 jam, memori profil pengguna (nama/jabatan; jangan dikarang).

## 8. Cara melanjutkan di sesi baru
Tempel kira-kira: *"Lanjutkan proyek ChunAI. Baca `CLAUDE.md` dan `docs/CATATAN_PROYEK.md`, lalu kita kerjakan Tahap 3: …"*.
Di sesi cloud: tambahkan repo (`hendriawancorp-chunai/chunai`), clone, `pip install -e . && pytest -q`.
