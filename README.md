# ChunAI

AI Agent Assistant pribadi: riset, analisis data, kajian, presentasi, media, dan kerja web
dengan **persetujuan sebelum eksekusi akhir**.

## Pasang di Windows (disarankan: WSL2)
Panduan langkah demi langkah: **[docs/PANDUAN_WINDOWS.md](docs/PANDUAN_WINDOWS.md)** (satu skrip pemasangan + `chunai doctor`).
Perintah bantu: `chunai doctor [--live]` (periksa prasyarat), `chunai auth` (token langganan), `chunai telegram-check`.
Pengaturan disimpan di `.env` (lihat `.env.example`); `.env` tidak boleh di-commit.

## Jalankan
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...     # jangan di-commit
chunai                            # mulai chat
pytest                            # jalankan tes
```

## Struktur
- `policy.py`   – baca bebas / tulis minta izin / berbahaya ditolak (default tak dikenal = minta izin)
- `approval.py` – Approval Gate (reviewer pluggable: CLI sekarang, Telegram/web nanti)
- `audit.py`    – audit log JSONL (`data/audit.jsonl`)
- `agent.py`    – orkestrator (Claude Agent SDK)
- `agents.py`   – subagen: peneliti, analis

## Antarmuka: Web dan Telegram
```bash
export CHUNAI_WEB_TOKEN="isi-token-panjang-acak"       # wajib untuk Web (kalau kosong dibuat acak & dicetak)
chunai web            # http://127.0.0.1:8787  (hanya localhost; untuk akses jarak jauh pakai HTTPS/tunnel)

# Telegram: buat bot di @BotFather -> token. Kirim /id ke bot untuk tahu ID Anda.
export CHUNAI_TELEGRAM_TOKEN="123456:ABC..."
export CHUNAI_TELEGRAM_USERS="11111111"                # hanya ID ini yang dilayani (wajib)
chunai telegram       # atau: chunai serve  (Web + Telegram sekaligus)
```
- Persetujuan: tombol ✅/❌ (Telegram) atau kartu (Web). Tidak dijawab dalam 10 menit = **ditolak**.
- Aksi final web (klik/kirim) tidak punya tombol "selalu izinkan".
- Kirim file (CSV/XLSX/PDF/…) lewat chat untuk dianalisis. Hasil kerja (docx/pptx/xlsx/gambar/video/teks) **dikirim langsung ke chat**:
  agen memakai tool `kirim_file` (atau, bila tidak, semua file baru di workspace yang bukan internal).
- Perintah Telegram: `/status` `/stop` `/reset` `/id`. Hanya chat pribadi; grup diabaikan.

## Dokumen & presentasi
Tool `buat_dokumen` (DOCX gaya kajian + daftar pustaka APA) dan `buat_presentasi` (PPTX 16:9, chart editable).
Tema khusus (warna, font, footer, logo): `data/themes/<nama>.json`, lihat `src/chunai/office/theme.py`.
Contoh spesifikasi: `examples/`.

## Analisis data & media
- `jalankan_python`: kode analisis berjalan di sandbox (tanpa internet via `unshare -rn`, tulis/baca terbatas di workspace,
  batas waktu/memori, environment bersih tanpa API key). Bila isolasi tidak tersedia, eksekusi ditolak (gagal-aman).
- `buat_gambar` (HTML/CSS → PNG tanpa JavaScript & tanpa jaringan), `edit_gambar`, `buat_video` (adegan → MP4 via ffmpeg),
  `slide_ke_video` (PPTX → MP4). Gambar fotorealistik AI memerlukan penyedia eksternal (belum dikonfigurasi).

## Web Agent (form, survei, kuesioner, portal)
Alur: buka → baca → isi (DRAF) → review (nilai nyata dari halaman + screenshot) → **izin Anda** → kirim.

```bash
# 1. daftar situs yang boleh dibuka tanpa tanya (satu domain per baris)
echo "portal.contoh.go.id" >> data/allowlist.txt      # atau env CHUNAI_ALLOWED_DOMAINS=a.com,b.com

# 2. situs yang butuh login -> login MANUAL sekali (jalankan di komputer Anda, bukan cloud)
chunai login https://portal.contoh.go.id               # jendela browser terbuka, Anda login sendiri
CHUNAI_BROWSER=profile CHUNAI_HEADLESS=0 chunai        # agen melanjutkan dengan sesi tersimpan

# alternatif: sambung ke Chrome Anda yang sudah login
#   chrome --remote-debugging-port=9222 ; lalu CHUNAI_BROWSER=cdp chunai
```
Pengaman: allowlist domain (juga setelah redirect), kolom password/OTP/kartu tidak pernah diisi agen,
isi halaman dibungkus sebagai data + pemindai prompt-injection, klik & kirim **selalu** minta izin
(tidak bisa "selalu izinkan"). Tidak untuk menjawab ujian/penilaian yang dinilai atau diawasi.

## Roadmap
0 Fondasi ✅ · 1 Riset ✅ + Analisis ✅ · 2 Dokumen/PPT ✅ · 3 Web Agent ✅ · 4 Media ✅ · Web/Telegram ✅ · 5 Penguatan (berikutnya)
