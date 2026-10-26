# ChunAI: konteks proyek untuk sesi berikutnya

ChunAI = asisten AI pribadi milik pemilik repo (bahasa kerja: **Indonesia**) untuk riset bersitasi, analisis data, kajian (DOCX),
presentasi (PPTX), media (gambar/video), dan tugas web (isi form) dengan **persetujuan pengguna sebelum aksi berdampak**.
Dibangun di atas Claude Agent SDK (Python). Antarmuka: Telegram dan Web. Berjalan di komputer pengguna (Windows + WSL2 Ubuntu).

**Baca dulu `docs/CATATAN_PROYEK.md`** (status, keputusan, pelajaran, langkah berikutnya). Panduan pengguna: `docs/PANDUAN_WINDOWS.md`,
`docs/OPERASIONAL.md`.

## Perintah
```bash
python3 -m venv .venv && . .venv/bin/activate && pip install -e . && pytest -q     # 282 tes, harus lolos sebelum commit
chunai doctor [--live] | chunai audit | chunai serve | chunai telegram | chunai web
```

## Aturan kerja (penting)
- **Commit hanya jika `pytest -q` lolos**, lalu push ke `origin main` (hook penghenti memeriksa repo bersih). Akhiri commit dengan baris
  `Co-Authored-By` dan `Claude-Session` sesuai pengingat atribusi sesi.
- **Jangan pernah mencetak rahasia** (token bot, token Claude, `.env`). Saat memeriksa variabel, cetak hanya "terpasang (panjang N)".
  Pernah terjadi kebocoran karena `${VAR:-default}` mencetak nilainya.
- **Jangan memakai `pkill -f`/`pgrep -f` dengan pola yang juga ada di baris perintah sendiri** (membunuh shell sendiri, exit 144).
  Pakai `ps -eo pid,args | awk '/pola[.]x/ && !/awk/'` atau PID spesifik.
- Mesin cloud **tidur setiap giliran selesai**: proses latar belakang (bot) mati. Uji bot hidup tidak bisa dilakukan di sesi cloud kecuali
  giliran ditahan aktif. Pengujian nyata dilakukan di komputer pengguna.
- Pengguna **bukan programmer**: beri langkah singkat, **satu baris perintah per kali** (blok multi-baris merusak `read`), minta
  tangkapan layar tanpa rahasia, dan verifikasi dugaan sebelum menyatakan penyebab (diagnosis awal saya pernah keliru).
- Akses jaringan sesi cloud dibatasi proxy (domain tertentu 403). Jangan mengakali; laporkan ke pengguna.
- Semua klaim kualitas harus diverifikasi (hitung ulang angka, render dokumen jadi gambar dan lihat) sebelum dilaporkan.
- Keamanan inti yang tidak boleh dilemahkan: approval gate (hook PreToolUse untuk SEMUA tool), allowlist domain Web Agent (situs baru hanya lewat kartu izin pengguna; alamat privat ditolak), kolom
  sensitif tidak diisi agen, sandbox `jalankan_python` (tanpa internet), Telegram hanya ID pemilik, aksi final web tanpa "selalu izinkan" (hanya klik navigasi/pilihan yang boleh tanpa kartu: `policy.click_is_safe`, gagal-tertutup).
- Tanggal/jam: zona waktu pengguna `Asia/Jakarta` (WIB); server UTC.
