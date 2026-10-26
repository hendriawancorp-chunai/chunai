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
  - **Model otomatis (hemat):** ChunAI memilih model sendiri. Pertanyaan/percakapan singkat memakai Haiku (murah), dokumen/analisis/lampiran memakai Sonnet, tugas web (form, kuis, media sosial) memakai Opus. Balasan singkat seperti "lanjutkan" mengikuti tingkat tugas sebelumnya. Ketik `/model` untuk melihat atau mengubah (`/model otomatis`, `/model ringan`, `/model sedang`, `/model berat`), atau awali satu perintah dengan `!cepat` atau `!teliti`. Tugas terjadwal memakai Haiku (maksimal Sonnet). Untuk mengunci satu model: `CHUNAI_MODEL=claude-sonnet-5-5` di `.env`; untuk mematikan pemilahan: `CHUNAI_MODEL_AUTO=off`.
  - **Batas pemakaian:** `CHUNAI_DAILY_BUDGET_USD` (harian, 0 = tanpa batas) dan `CHUNAI_SESSION_BUDGET_USD` (per sesi, bawaan 5, 0 = tanpa batas) hanyalah pagar buatan ChunAI dengan angka "setara" (bukan tagihan). Pada 80% batas harian ChunAI memberi peringatan sekali; bila batas tercapai, kirim `/lanjut` (Telegram atau Web) untuk melanjutkan hari itu. Batas sebenarnya adalah kuota langganan Claude Anda.
  - **Tanpa token (opsional):** tambahkan baris `CHUNAI_WEB_AUTH=off` ke `.env`, lalu jalankan ulang. Halaman langsung terbuka tanpa kata sandi, hanya dari komputer ini (alamat selain localhost ditolak). Siapa pun yang memakai komputer/akun Windows Anda dapat memakai ChunAI; kartu izin tetap berlaku.
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
| Telegram: "ConnectError" / "Tidak bisa terhubung ke Telegram" | Koneksi komputer ke api.telegram.org terputus (internet, VPN, DNS WSL, komputer baru bangun dari tidur). ChunAI kini mencoba ulang 3x otomatis. Bila terus: `chunai telegram-check`, lalu di PowerShell `wsl --shutdown` dan buka Ubuntu lagi; matikan VPN; cek `cat /etc/resolv.conf`. |
| Bot Telegram diam | Cek `data/logs/chunai.log`. Pastikan komputer tidak tidur dan terminal/skrip masih berjalan. |
| Log: "Conflict ... other instance" | Ada dua ChunAI berjalan dengan token yang sama. Tutup yang lain. |
| Web tidak terbuka di `localhost:8787` | Pastikan `run.sh` berjalan; tutup program lain yang memakai port 8787. |
| Tugas berat gagal / sangat lambat | RAM kurang. Biarkan `CHUNAI_HEAVY_SLOTS=1` dan tutup aplikasi lain. |
| Kartu "SITUS BARU" muncul | Normal: pertama kali agen membuka situs. Setuju = sesi ini; ♾ Selalu = simpan permanen. Tidak perlu mengedit file apa pun. |
| Web Agent minta login lagi | Sesi habis. Jalankan `chunai login <alamat situs>`, login sendiri, tutup jendela; cookie sesi disimpan di `data/browser_state.json` (jangan dibagikan). |
| Web Agent tidak bisa unggah berkas / CAPTCHA | Memang tidak didukung; lakukan sendiri lalu minta agen melanjutkan. |
| Sandbox analisis "tidak tersedia" | Pastikan WSL **versi 2**; `chunai doctor` menampilkan statusnya. |

## Merevisi dokumen yang sudah ada
Kirim berkas DOCX atau PPTX ke bot (Telegram) atau unggah di Web, lalu tulis perintahnya, mis. "Di presentasi ini ganti pendapatan 2025 di slide 2 menjadi Rp5,40 T" atau
"Perbaiki paragraf pertama bab 2 agar lebih ringkas". ChunAI membuat **salinan baru** berakhiran `_rev` dan mengirimkannya; berkas asli tidak diubah. Angka turunan yang tidak konsisten dilaporkan, tidak diubah diam-diam.

## Form, soal, dan media sosial (Web Agent lanjutan)
1. **Data diri (sekali):** kirim CV/biodata Anda ke bot lalu tulis "Siapkan lembar data diri dari CV ini". Anda menerima kartu izin berisi butir yang akan disimpan (nilai pribadi disamarkan).
   Data disimpan lokal di `data/data_diri.json`; butir dibagi umum / pribadi / sensitif. Data pribadi dan sensitif tidak pernah diposting ke media sosial dan hanya diisi ke form bila ditanyakan.
2. **Form atau soal:** tulis "Buka <alamat> dan kerjakan. Materi: masukan/materi.pdf" (materi opsional). ChunAI menampilkan **tabel rencana** (soal, jawaban, dasar, keyakinan). Koreksi lewat chat ("no 3 ganti B"),
   lalu balas "setuju". Baru setelah itu halaman diisi, diperiksa kesesuaiannya, dan dikirim dengan kartu izin. Soal tanpa dasar dilewati, tidak ditebak.
   Ujian resmi yang melarang bantuan tidak dikerjakan; survei, form, kuis latihan, dan kuis buatan sendiri tidak masalah.
3. **LinkedIn/Instagram:** pakai Chrome sendiri (mode CDP): jalankan `chunai cdp-help` dan ikuti langkahnya (sekali: `.wslconfig` mirrored; tiap kali: `scripts\start-chrome-cdp.ps1`, login manual di jendela itu).
   Minta draf dulu ("buatkan caption/posting tentang ..."), tinjau, lalu ChunAI mengisi dan meminta kartu izin sebelum memposting. Satu tindakan per kartu. Batas 15 tindakan/hari
   (`CHUNAI_SOCIAL_DAILY_LIMIT` di `.env`, 0 = tanpa batas). Platform melarang otomatisasi: gunakan seperlunya; akun bisa dibatasi.

## Analisis saham (IDX): teknikal dan rencana trading
1. Unduh riwayat harga satu saham dari platform Anda (CSV/XLSX; mis. Stockbit, RTI, situs bursa), lalu kirim ke bot.
2. Tulis, mis. "Ini ekspor harga TLKM dari Stockbit. Profil saya: horizon menengah, toleransi moderat, modal Rp200 juta, batas rugi 1% per transaksi. Impor, periksa, analisis teknikal, dan buat rencana trading."
3. ChunAI menyimpan profil (kartu izin), mengimpor dengan mencatat sumber, memeriksa kualitas data (kesegaran, bolong, lonjakan), lalu analisis dan rencana ukuran lot dari batas rugi Anda. "Bandingkan TLKM BBRI BMRI" untuk studi komparatif.
Data tersimpan lokal di `data/saham/`. Hasil adalah pandangan teknikal; fundamental, valuasi, dan berita menyusul (belum ada). Bukan nasihat keuangan berlisensi; keputusan dan risiko ada pada Anda.

## Analisis saham lanjutan (fundamental, valuasi, laporan, rekam jejak)
- **Laporan keuangan:** unggah PDF laporan keuangan emiten (atau minta ChunAI mencarinya di situs bursa/emiten; Anda menyetujui situsnya lewat kartu; bila situs memblokir, unduh sendiri lalu unggah). ChunAI mencatat angka kunci HANYA bila terbukti ada di halaman yang disebut.
- **Perintah contoh:** "Analisis lengkap TLKM: teknikal, fundamental, valuasi DCF dengan asumsi yang dijelaskan, risiko, dan laporan DOCX." / "Bandingkan TLKM, BBRI, BMRI dan saring yang cocok dengan profil saya." / "Catat rekomendasi itu" / "Evaluasi rekam jejak rekomendasi saya."
- **Pemantauan:** "Masukkan TLKM ke watchlist, beri tahu bila menembus 3.500" lalu "Setiap hari bursa 16.30 periksa watchlist saya" (pengingat/tugas terjadwal; hanya membaca data tersimpan, jadi perbarui data harga dulu).
- Laporan diperiksa gerbang kualitas (sumber, tanggal data, risiko, skenario pesimis, pembatalan, tanpa kata kepastian, angka ditelusuri) sebelum dikirim. Bila data tampak janggal, ChunAI berhenti dan meminta data yang benar, bukan memaksakan kesimpulan.
- Bukan nasihat keuangan berlisensi; hasil masa lalu tidak menjamin hasil ke depan.

## Meringkas dokumen panjang
Kirim PDF/DOCX/PPTX (satu atau beberapa berkas) lalu tulis, mis. "Ringkas laporan ini menjadi 5 butir temuan dengan halaman" atau "Di mana dokumen ini menyebut anggaran 2026?". Setiap butir diberi nomor halaman
dan kutipan langsung diverifikasi terhadap dokumennya. PDF hasil pindai (berupa gambar) belum bisa dibaca. Dokumen sangat panjang dibaca bertahap oleh beberapa "pembaca" sehingga butuh beberapa menit.

## Pengingat dan tugas terjadwal
Minta lewat chat (Telegram atau Web), mis. "Ingatkan saya setiap Senin 08.00 menyiapkan laporan" atau "Setiap hari 06.30 ringkas berita sektor logistik". Anda akan menerima kartu izin berisi jadwal yang tepat.
`/jadwal` di Telegram menampilkan daftar; minta "hapus jadwal <id>" untuk menghapus. Hanya berjalan saat komputer dan `run.sh` menyala; jadwal yang terlewat <24 jam dijalankan terlambat, lebih lama dilewati.
Tugas terjadwal berjalan tanpa Anda: hanya membaca/riset/analisis; aksi yang butuh izin dilewati dan dilaporkan. Untuk situs yang sering dipakai, pilih ♾ Selalu agar tugas terjadwal boleh membukanya.

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
