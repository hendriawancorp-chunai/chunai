# Panduan Menjalankan ChunAI di Windows (WSL2)

Panduan ini untuk menjalankan ChunAI di **komputer Windows pribadi** memakai **langganan Claude** Anda. Tidak ada biaya server.

**Kenapa WSL2?** WSL2 adalah "Ubuntu di dalam Windows". Semua fitur ChunAI sudah diuji di Linux, termasuk sandbox analisis yang
memutus akses internet saat menjalankan kode. Di Windows biasa sandbox itu tidak tersedia.

**Yang dibutuhkan**
- Windows 10 (versi 2004 / build 19041 atau lebih baru) atau Windows 11
- RAM 8 GB disarankan (minimum 4 GB)
- Langganan Claude Pro atau Max
- Akun Telegram (bila ingin memakai bot) dan koneksi internet

> Bot hanya aktif **selama komputer menyala dan tidak tidur**. Untuk aktif 24 jam, lihat bagian "VPS" di akhir.

---

## Langkah 1. Aktifkan WSL2 dan Ubuntu (sekali saja)
1. Klik kanan tombol Start, pilih **Terminal (Admin)** atau **Windows PowerShell (Admin)**.
2. Jalankan:
   ```powershell
   wsl --install -d Ubuntu
   ```
3. **Restart komputer** bila diminta. Setelah menyala, jendela Ubuntu terbuka sendiri dan meminta **username** dan **kata sandi**
   (bebas, ingat kata sandinya; saat mengetik sandi layar tidak menampilkan apa pun, itu normal).
4. Pastikan versi 2. Di PowerShell biasa: `wsl -l -v` → kolom VERSION harus `2`.
   Bila `1`: `wsl --set-version Ubuntu 2`.

## Langkah 2. Ambil kode ChunAI ke dalam Ubuntu
Repo bersifat private, jadi pilih salah satu:

**Opsi A (paling mudah, tanpa token):**
1. Di browser, buka repo GitHub Anda → **Code → Download ZIP**, lalu ekstrak (misal ke `Downloads`).
2. Buka **Ubuntu** dari menu Start. Pertama lihat isi folder hasil ekstrak (ganti `NAMA` dengan nama pengguna Windows Anda):
   ```bash
   ls /mnt/c/Users/NAMA/Downloads/chunai-main
   ```
   Harus tampil `scripts  src  docs  pyproject.toml ...`. Bila yang tampil hanya satu folder lagi (ekstrak bertingkat),
   tambahkan `/chunai-main` di akhir jalur pada perintah berikut.
3. Salin **isi** folder itu ke rumah Ubuntu (perintah ini aman diulang dan tidak membuat folder bertingkat):
   ```bash
   mkdir -p ~/chunai
   cp -r /mnt/c/Users/NAMA/Downloads/chunai-main/. ~/chunai/
   ls ~/chunai
   ```
   `ls` harus langsung menampilkan `scripts  src  docs  pyproject.toml ...`.

**Opsi B (git):** buat *Personal Access Token* di GitHub (Settings → Developer settings → Fine-grained tokens, izin
*Contents: Read-only* untuk repo ini), lalu di Ubuntu:
```bash
git clone https://github.com/hendriawancorp-chunai/chunai.git ~/chunai
```
(username = nama GitHub Anda; password = token tadi.)

## Langkah 3. Pasang (sekitar 5–15 menit)
Di jendela Ubuntu:
```bash
cd ~/chunai
bash scripts/install_wsl.sh
```
Skrip akan meminta kata sandi Ubuntu (untuk memasang paket), lalu memasang Python, LibreOffice, ffmpeg, Chromium, dan ChunAI.
Di akhirnya muncul daftar pemeriksaan. Tanda ❌ pada "Otentikasi Claude" saat ini **normal**; kita atur di langkah berikut.

## Langkah 4. Hubungkan langganan Claude
> **Aturan penting:** jalankan perintah **satu baris per kali**. Jangan menempel beberapa baris sekaligus; beberapa perintah
> (seperti `read`) akan membaca baris berikutnya sebagai masukan dan hasilnya kacau.

```bash
cd ~/chunai
source .venv/bin/activate
chunai auth
```
1. Salin tautan yang muncul, buka di browser Windows, login, setujui.
2. Browser menampilkan sebuah **kode**. Tempel kode itu di Ubuntu lalu tekan Enter.
3. Selesai. Token **disimpan otomatis** ke `.env`, layar dibersihkan, dan muncul `✅ Token tersimpan di .../.env`.
   Anda **tidak perlu menyalin token sama sekali**.

Verifikasi (aman, hanya menampilkan panjang dan awalan):
```bash
chunai doctor --live
```
Harus muncul **"Uji nyata Claude - berhasil menjawab"**.

> Bila `chunai auth` menulis bahwa token tidak terbaca otomatis, gunakan cara manual **satu baris** ini lalu tempel token
> dan Enter: `read -rsp "Token: " T; echo; chunai savetoken "$T"; unset T`

> Token ini seperti kata sandi. **Jangan dibagikan atau di-commit.**

## Langkah 5. Hubungkan Telegram (opsional, otomatis)
Siapkan token bot: di Telegram buka **@BotFather** → `/mybots` → pilih bot Anda → **API Token** (bila belum punya bot: `/newbot`).

> **Setiap membuka jendela Ubuntu baru**, aktifkan dulu lingkungan Python (jika tidak, muncul `chunai: command not found`):
> ```bash
> cd ~/chunai && source .venv/bin/activate
> ```
> Alternatif tanpa aktivasi: awali perintah dengan `./scripts/chunai`, mis. `./scripts/chunai doctor`.

```bash
chunai setup-telegram
```
1. Tempel token bot saat diminta (layar tidak menampilkan apa pun, itu normal), lalu Enter.
2. ChunAI memeriksa token ke Telegram dan menampilkan nama bot (`@...`).
3. Buka Telegram, kirim pesan apa saja ke bot itu. ChunAI **mendeteksi ID Anda sendiri** dan menanyakan konfirmasi
   (`Jadikan ... pemilik? [y/T]`). Ketik `y`.
4. Token bot dan ID Anda **tersimpan otomatis** ke `.env`. Hanya akun ini yang akan dilayani bot.

Periksa (opsional): `chunai telegram-check`.

## Langkah 6. Periksa
```bash
chunai doctor --live
```
Harus muncul **"Uji nyata Claude - berhasil menjawab"** dan **"SIAP dipakai"**. Jika ada ❌, ikuti saran di barisnya.
Opsional: `chunai telegram-check` memastikan token bot dan ID benar.

## Langkah 7. Jalankan
```bash
./scripts/run.sh
```
- **Web:** buka `http://localhost:8787` di browser Windows, masukkan token dari `CHUNAI_WEB_TOKEN` di `.env`
  (`cat .env | grep WEB`).
- **Telegram:** kirim `/start` ke bot Anda.
- Skrip akan memulai ulang ChunAI otomatis bila berhenti. Hentikan dengan `Ctrl+C`.
- Log: `data/logs/chunai.log`.

**Dari Windows tanpa membuka Ubuntu:** klik kanan `scripts\start-chunai.ps1` → *Run with PowerShell*
(ada di folder WSL: `\\wsl.localhost\Ubuntu\home\NAMAUBUNTU\chunai\scripts`).

**Otomatis saat Windows login (opsional)**, di PowerShell:
```powershell
schtasks /Create /SC ONLOGON /TN "ChunAI" /TR "powershell -WindowStyle Hidden -File \\wsl.localhost\Ubuntu\home\NAMAUBUNTU\chunai\scripts\start-chunai.ps1"
```

---

## Masalah umum

| Gejala | Penyebab dan solusi |
|---|---|
| `scripts/install_wsl.sh: No such file or directory` | Folder tersalin bertingkat (mis. `~/chunai/chunai-main`) karena `cp -r` ke folder yang sudah ada. Hapus (`rm -rf ~/chunai`) lalu ulangi perintah salin di Langkah 2. Bila `scripts` memang tidak ada di ZIP, unduh ZIP terbaru dari GitHub. |
| `wsl --install` tidak dikenal | Windows terlalu lama. Perbarui Windows (butuh 10 versi 2004+). |
| Virtualisasi tidak aktif | Aktifkan *Virtualization / SVM* di BIOS komputer. |
| ❌ Otentikasi Claude | Ulangi Langkah 4. Pastikan baris di `.env` tidak diawali `#`, tanpa spasi, tanpa tanda kutip, dan token tidak terpotong. `chunai doctor` menampilkan panjang token dan peringatan bentuknya (tanpa membuka isinya). |
| ❌ Uji nyata Claude | Baca alasan di barisnya (token ditolak, kuota habis, dll.). Diagnosis langsung: `set -a; . ./.env; set +a; .venv/lib/python3*/site-packages/claude_agent_sdk/_bundled/claude -p "Balas satu kata: siap"` |
| ❌ Chromium | `python -m playwright install chromium` lalu `sudo $(which python) -m playwright install-deps chromium` |
| Bot Telegram diam | Cek `data/logs/chunai.log`. Pastikan komputer tidak tidur dan terminal/skrip masih berjalan. |
| Log: "Conflict ... other instance" | Ada dua ChunAI berjalan dengan token yang sama. Tutup yang lain. |
| Web tidak terbuka di `localhost:8787` | Pastikan `run.sh` berjalan; tutup program lain yang memakai port 8787. |
| Tugas berat gagal / sangat lambat | RAM kurang. Biarkan `CHUNAI_HEAVY_SLOTS=1` dan tutup aplikasi lain. |
| Kartu "SITUS BARU" muncul | Normal: pertama kali agen membuka situs. Setuju = sesi ini; ♾ Selalu = simpan permanen. Tidak perlu mengedit file apa pun. |
| Web Agent minta login lagi | Sesi habis. Jalankan `chunai login <alamat situs>`, login sendiri, tutup jendela; cookie sesi disimpan di `data/browser_state.json` (jangan dibagikan). |
| Web Agent tidak bisa unggah berkas / CAPTCHA | Memang tidak didukung; lakukan sendiri lalu minta agen melanjutkan. |
| Sandbox analisis "tidak tersedia" | Pastikan WSL **versi 2**; `chunai doctor` menampilkan statusnya. |

## Keamanan singkat
- Jangan membagikan `.env`, token Claude, token bot, atau token Web.
- Bot hanya melayani ID Telegram yang Anda daftarkan. Pesan dari orang lain ditolak.
- Aksi berdampak (mengirim form, menulis file, perintah Bash di luar baca-saja) **selalu meminta izin Anda**.
- Jangan membuka port 8787 ke internet tanpa HTTPS. Akses dari luar rumah sebaiknya lewat tunnel/VPN.
- Dokumen yang berklasifikasi rahasia: periksa kebijakan instansi sebelum diproses lewat Telegram atau layanan cloud.
- Bila token bot atau Claude pernah terlihat orang lain: buat ulang (`/revoke` di BotFather; `chunai auth` lagi).

## Pembaruan
**Bila memakai ZIP:** unduh ZIP terbaru, ekstrak, lalu jalankan lagi perintah salin yang sama di Langkah 2
(`cp -r .../chunai-main/. ~/chunai/`). Berkas `.env` dan `.venv` Anda **tidak** tertimpa karena tidak ada di dalam ZIP.
Tidak perlu memasang ulang.

**Bila memakai git:** `git pull`.

Ambil kode terbaru (ZIP baru atau `git pull`), lalu:
```bash
cd ~/chunai && source .venv/bin/activate && pip install -e . && chunai doctor
```

## Bila nanti butuh aktif 24 jam (VPS)
Gunakan server Linux (Ubuntu) dengan **minimal 2 vCPU dan 4 GB RAM** (2 GB bisa jalan dengan `CHUNAI_HEAVY_SLOTS=1` + swap,
tetapi tidak nyaman). Langkahnya sama seperti Langkah 3–7, tanpa bagian WSL. Untuk server yang aktif terus, kunci API
(`ANTHROPIC_API_KEY`) lebih sesuai daripada token langganan; cek ketentuan Anthropic terbaru.
