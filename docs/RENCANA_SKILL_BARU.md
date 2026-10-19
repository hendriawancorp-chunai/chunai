# Rencana Skill Baru ChunAI (disusun 19 Okt 2026, belum dikerjakan)

Permintaan pengguna: (1) baca email dan jawab dengan DRAF dulu, kirim hanya setelah persetujuan; (2) membantu operasi komputer untuk
pengisian form; (3) menjawab pertanyaan essay dan/atau pilihan ganda; (4) tugas lain yang layak ditawarkan.

## Prinsip (tidak boleh dilanggar)
- Semua aksi berdampak lewat approval gate. **Mengirim email = aksi final**: selalu kartu, tanpa "selalu izinkan", isi kartu dibaca dari draf nyata.
- Isi email, halaman web, dan berkas yang diproses = **DATA, bukan instruksi** (dibungkus + dipindai prompt injection). Email adalah jalur serangan
  paling umum: pengirim luar bisa menulis "kirim semua data ke X". Agen tidak boleh bertindak atas isi email tanpa instruksi pengguna.
- Rahasia (kata sandi aplikasi email) hanya di `.env`, tidak pernah dicetak/di-audit.
- Tiap skill: modul sendiri di `src/chunai/skills/<nama>.py` (tool + bagian prompt), aktif hanya bila dikonfigurasi, ada pemeriksaan di `chunai doctor`,
  tes otomatis (backend palsu), dan uji agen asli. Commit hanya bila `pytest -q` lolos.

## Skill 1. Email: baca, draf, kirim dengan persetujuan
**Alur:** `baca_inbox` (daftar terbaru/belum dibaca) → `baca_email` (isi, DATA terbungkus) → agen menyusun **draf balasan** (disimpan di workspace dan
opsional ke folder Draf) → pengguna merevisi lewat chat → `kirim_email` (kartu: Kepada, Cc, Subjek, isi lengkap; pengguna boleh mengedit) → terkirim → tercatat di audit.

**Akses (perlu keputusan pengguna):**
| Opsi | Kelebihan | Kekurangan |
|---|---|---|
| A. IMAP + SMTP dengan *app password* (disarankan) | Sederhana, berjalan di komputer sendiri, bekerja di Gmail/Outlook/Yahoo/kantor | Perlu 2FA + kata sandi aplikasi; sebagian kantor (M365) menonaktifkan |
| B. Gmail/Graph API dengan OAuth | Izin lebih halus (baca saja / kirim) | Pendaftaran aplikasi Google/Microsoft, token kedaluwarsa, lebih rumit bagi non-programmer |
| C. Webmail lewat Web Agent (login manual) | Tanpa pengaturan akun | Rapuh (UI berubah), lambat, banyak kartu |

**Pengaman khusus email:**
- Tool baca tidak mengubah apa pun (tanpa hapus/pindah/tandai-dibaca, kecuali diminta dan dengan kartu).
- Penerima default = pengirim asli (balas) ; penerima baru/Cc/Bcc ditampilkan menonjol di kartu; tidak ada *forward* otomatis.
- Lampiran: v1 tidak mengirim lampiran; membaca lampiran hanya sebagai teks (PDF/DOCX) lewat sandbox yang ada.
- Batas kirim (mis. 10 email/hari) dan jeda; tidak ada pengiriman massal.
- Email berisi perintah ke agen ("abaikan instruksi", "kirim kata sandi") → peringatan, agen melaporkan, tidak mengikuti.
- Gaya: nada, bahasa (Indonesia/Inggris sesuai surat asli), tanda tangan dari profil yang diisi pengguna (tidak dikarang).
- Jangan membalas hal yang butuh keputusan/fakta yang tidak ada: agen bertanya atau menandai `[ISI: ...]` di draf.

**Pengujian:** backend email palsu (kotak masuk berisi email biasa, email berisi injeksi, email panjang); tes bahwa `kirim_email` tanpa persetujuan
tidak mengirim, kartu menampilkan isi nyata, penerima tak terduga ditandai. Uji nyata dengan akun uji milik pengguna di komputernya (cloud tidak
bisa menjangkau server email).

## Skill 2. Pengisian form di komputer
Perlu klarifikasi arti "operasi komputer":
- **a. Form web** → SUDAH ada (Web Agent). Penyempurnaan: mode "jawab dari berkas data" (pengguna unggah CSV/DOCX berisi data diri, agen memetakan ke kolom, tanpa menebak).
- **b. Form berkas: PDF isian, DOCX/XLSX templat** → bisa dibangun aman di sisi server: `isi_pdf_form`, `isi_templat_docx/xlsx` (baca kolom, usulkan pengisian, tampilkan tabel review, simpan salinan baru; berkas asli tidak ditimpa).
- **c. Aplikasi desktop Windows (kontrol mouse/keyboard)** → TIDAK direkomendasikan sekarang: ChunAI berjalan di WSL tanpa akses layar Windows; butuh agen sisi Windows, tangkapan layar, risiko aksi salah tinggi.
  Bila nanti diperlukan: modul terpisah, hanya aplikasi yang ditentukan, kartu per langkah, tombol berhenti darurat.

## Skill 3. Mode jawab soal (essay & pilihan ganda)
- Pemisahan tegas: agen **membaca semua soal dulu**, menyusun **tabel usulan** (no, soal, jawaban, dasar/sumber, tingkat keyakinan; yang ragu ditandai), pengguna merevisi, baru **isi di web** (klik navigasi tanpa kartu; kirim akhir dengan kartu).
- Essay: batas kata/karakter dibaca dari form; gaya sesuai instruksi; sitasi bila ada sumber; tidak mengarang fakta/data pribadi.
- Konteks: survei, form, kuis latihan, kuis buatan pengguna → dikerjakan. Ujian resmi yang dinilai/diawasi dan melarang bantuan → agen bertanya konteks dan tidak menjawab diam-diam.
- Pengujian: situs tiruan dengan soal campuran (radio, centang, essay, dropdown, soal bergambar tidak terbaca → ditandai), memeriksa tidak ada pengiriman sebelum persetujuan.

## Skill 4. Tawaran tambahan (urut kegunaan)
1. **Revisi dokumen yang sudah ada** (unggah DOCX/PPTX → ubah bagian tertentu, simpan versi baru, tampilkan perubahan).
2. **Tugas terjadwal/pengingat** (cron di komputer pengguna; hasil dikirim ke Telegram; hanya baca/riset, aksi berdampak tetap minta kartu saat pengguna ada).
3. **Ringkas dokumen/PDF panjang** dengan kutipan halaman.
4. **Spreadsheet Excel** (rumus + grafik) selain CSV.
5. **Memori profil** (nama, jabatan, gaya, tanda tangan email; hanya yang pengguna sebutkan, bisa dilihat dan dihapus).
6. **Tema/logo pribadi** untuk dokumen & slide.

## Urutan pengerjaan (usulan)
| Fase | Isi | Perkiraan |
|---|---|---|
| 0 | Kerangka skill (`skills/`, konfigurasi, doctor), memori profil minimal (tanda tangan, nada surat) | kecil |
| 1 | Email: baca + draf (tanpa kirim) → uji di akun uji pengguna | sedang |
| 2 | Email: kirim dengan kartu + batas + audit | sedang |
| 3 | Mode jawab soal (tabel usulan → isi → kirim) + uji agen asli | sedang |
| 4 | Isi form berkas (PDF/DOCX/XLSX) | sedang |
| 5 | Revisi dokumen, terjadwal, ringkas PDF, Excel, tema | bertahap sesuai kebutuhan |

## Keputusan yang dibutuhkan dari pengguna
1. Penyedia email (Gmail/Outlook/kantor/lainnya) dan apakah kata sandi aplikasi (opsi A) bisa dibuat. Email yang dipakai untuk uji.
2. "Operasi komputer": cukup (a) web + (b) berkas PDF/Word/Excel, atau perlu (c) aplikasi desktop?
3. Email: hanya Inbox, atau semua folder? Perlu lampiran? Bahasa utama surat?
4. Batas kirim harian yang nyaman, dan siapa saja yang boleh dibalas otomatis-draf (semua / daftar kontak tertentu).
5. Urutan prioritas bila berbeda dari tabel di atas.
