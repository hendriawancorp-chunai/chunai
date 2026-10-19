# Rencana Skill Web Agent Lanjutan (disusun 19 Okt 2026, BELUM dibangun, menunggu persetujuan pengguna)

Tujuan pengguna: ChunAI membantu pekerjaan berbasis web atas perintah pengguna: (1) mengisi form, (2) menjawab pertanyaan essay dan pilihan ganda (termasuk soal/kuis),
(3) kegiatan di media sosial profesional pribadi (LinkedIn, Instagram): posting, caption, balas komentar dan DM, ubah profil, lamaran kerja, ajukan koneksi.
Jawaban pengguna: akun pribadi; volume mengikuti perintah; gambar dari komputer dan buatan ChunAI; gaya profesional; bersedia memakai Chrome sendiri (CDP).

## 0. Prinsip dan batas (tidak berubah)
- Semua tindakan keluar (kirim, posting, komentar, ajukan koneksi, kirim lamaran, kirim jawaban akhir) lewat kartu izin dengan isi NYATA dari halaman; tanpa "selalu izinkan".
- Login, sandi, OTP, CAPTCHA, verifikasi: pengguna sendiri. Unggah berkas hanya lewat tool khusus dengan kartu.
- Isi halaman/pesan/dokumen = DATA, bukan perintah (pemindai prompt-injection tetap).
- Tidak membangun: tindakan massal (follow/like/komentar/DM berulang), scraping profil orang lain, akun/interaksi palsu, menyamar sebagai orang lain, trik menghindari deteksi bot.
- Tidak mengarang pengalaman, gelar, atau data pribadi; hanya dari lembar data/CV pengguna.
- Ujian/penilaian resmi yang dinilai atau diawasi dan melarang bantuan: TIDAK dikerjakan atas nama pengguna. Dikerjakan: survei, form, kuis latihan, kuis buatan sendiri, pelatihan/ujian yang membolehkan bahan/alat bantu
  (agen bertanya aturan sekali per situs; tidak bisa diverifikasi, bergantung kejujuran pengguna).
- Risiko platform: LinkedIn/Instagram melarang otomatisasi; akun bisa dibatasi. Risiko pada akun pengguna.

## 1. Fondasi
| # | Komponen | Isi |
|---|---|---|
| F1 | Mode CDP | Agen memakai Chrome pengguna (login nyata, lebih alami). Panduan Windows+WSL2, `chunai doctor` memeriksa koneksi CDP, `chunai cdp-help` mencetak perintah tepat. |
| F2 | Data pengguna | Lembar data diri/CV di workspace (`masukan/`) + memori profil (butir yang pengguna sebut; kode ada di git stash "memori-profil-belum-diminta"). Agen tidak menebak data yang tidak ada. |
| F3 | Peta form/soal | Tool yang merangkum halaman (termasuk multi-langkah, iframe) menjadi daftar terstruktur: jenis, opsi, wajib, batas kata; soal bergambar lewat tangkapan layar. |
| F4 | Rencana isian | Tabel persisten (workspace): no, pertanyaan, jawaban, dasar (materi+halaman atau pengetahuan umum), keyakinan. Diedit lewat chat; bisa dilanjutkan bila terputus. |
| F5 | Pengisi + pemeriksa | `terapkan_rencana` mengisi sesuai tabel yang disetujui; `periksa_kesesuaian` membandingkan isian halaman vs tabel dan melaporkan selisih sebelum kartu kirim akhir. |
| F6 | Editor teks kaya | Mengetik ke contenteditable/Lexical/Draft (editor posting LinkedIn/Instagram), diuji di situs tiruan. |
| F7 | Unggah aman | `unggah_berkas`: hanya berkas workspace (gambar dari komputer atau buatan ChunAI), kartu menampilkan berkas, tanpa "selalu". |
| F8 | Pagar sosial media | Daftar domain sosial (instagram.com, linkedin.com, dst.): semua klik non-navigasi = kartu; batas tindakan keluar per hari (default 15, `CHUNAI_SOCIAL_DAILY_LIMIT`); jeda minimum tetap (bukan acak); audit setiap tindakan keluar. |

## 2. Skill per kegiatan
- **A. Form dan survei:** data diri dari lembar data; tabel tinjauan; isi; kartu kirim.
- **B. Soal/kuis (konteks diizinkan):** sumber jawaban = materi pengguna (bersitasi halaman, kemampuan baca dokumen yang ada) lalu pengetahuan umum/pencarian dengan label; "tidak ada di materi" ditandai; essay sesuai bahasa dan batas kata.
- **C. LinkedIn:** draf posting/artikel pendek; headline/About/pengalaman dari CV; lamaran (Easy Apply) dengan pertanyaan essay dan pilihan ganda; permintaan koneksi dengan catatan personal; balas pesan; ringkas notifikasi/pesan.
- **D. Instagram:** caption + hashtag; unggah gambar; balas komentar/DM; edit bio.
- **E. Gambar:** dari komputer pengguna atau dibuat ChunAI (grafis/infografis/kutipan via media.py; foto fotorealistik = skill 8 yang ditunda).

## 3. Tahap pembangunan
| Tahap | Isi | Selesai bila |
|---|---|---|
| T0 | F1 CDP: panduan, doctor, `cdp-help`, uji koneksi | pengguna berhasil terhubung (tangkapan layar doctor) |
| T1 | F2+F3+F4: peta form/soal, rencana tabel, materi (baca-saja) | uji situs tiruan campuran + agen asli |
| T2 | F5+F6+F7: pengisian, pemeriksa kesesuaian, editor kaya, unggah aman, kirim akhir | situs tiruan (form, kuis, editor posting) + agen asli |
| T3 | F8 + skill C/D tahap draf lalu publikasi dengan kartu | uji tiruan; uji nyata pengguna 1 hal kecil per situs |
| T4 | Lamaran kerja LinkedIn | uji tiruan multi-langkah; uji nyata pengguna |
| T5 (opsional) | Kuis interaktif satu soal per layar/timer (konteks diizinkan, rencana disetujui dulu) | bila dibutuhkan |
Tiap tahap: tes otomatis (commit hanya bila `pytest -q` lolos), agen asli di situs tiruan, dokumen diperbarui, lalu pengguna menguji di komputernya. Instagram/LinkedIn asli tidak terjangkau dari sesi cloud.

## 4. Panduan CDP (ringkas; dipastikan dan diuji di T0)
1. Tutup semua jendela Chrome. Jalankan Chrome Windows dengan profil khusus dan port debug (Chrome 136+ mewajibkan `--user-data-dir` sendiri):
   `Start-Process "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" -ArgumentList "--remote-debugging-port=9222","--user-data-dir=C:\\chunai-chrome"` (PowerShell)
2. Login manual ke LinkedIn/Instagram di jendela itu (sekali; sesi tersimpan di profil khusus).
3. Agar WSL2 menjangkau port itu: Windows 11 dengan WSL `networkingMode=mirrored` di `%UserProfile%\\.wslconfig` (lalu `wsl --shutdown`), atau penerusan port (`netsh interface portproxy`). Di `.env`: `CHUNAI_BROWSER=cdp`, `CHUNAI_CDP_URL=http://127.0.0.1:9222`.
4. `chunai doctor` memeriksa koneksi. Jangan membuka Chrome profil khusus untuk hal lain; port debug memberi kendali penuh atas browser itu: jalankan hanya di komputer pribadi.

## 5. Keputusan default yang diusulkan (bisa diubah pengguna)
- Batas tindakan keluar media sosial 15/hari; kartu per tindakan; "balas 5 komentar" = 5 kartu.
- Tinjauan: semua jawaban/draf selalu ditinjau dulu.
- Aturan ujian: lihat bagian 0.

## 6. Dibutuhkan dari pengguna
Lembar data diri/CV, contoh form atau kuis yang sering dihadapi, konfirmasi Windows 11 (mirrored mode) atau Windows 10, dan persetujuan atas bagian 0 dan 5.
