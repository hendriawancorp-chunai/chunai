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
| Web Agent (Playwright, draf→review→izin→kirim) | ✅ di situs tiruan (login sesi, form 2 langkah, validasi server, iframe) | belum diuji di situs nyata |
| Antarmuka Web | ✅ | teruji headless + agen asli |
| Antarmuka Telegram | ✅ di Telegram asli | `/start`, `/id`, `/status`, `/stop`, tombol izin, unggah file, kirim file hasil |
| Pemasangan Windows (WSL2) | ✅ | `install_wsl.sh`, `chunai doctor/auth/setup-telegram` |
| Operasional (cadangan, audit, batas harian, daftar keamanan) | ✅ | `docs/OPERASIONAL.md` |
| **Tahap 3: penyesuaian ke pekerjaan pengguna** | ⏳ | lihat bagian 7 |

Terakhir: 153 tes lolos (16 Okt 2026).

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

## 5c. Pemeriksaan Web Agent (16 Okt 2026, situs tiruan)
- Teruji: login manual lalu agen mewarisi sesi; form 2 langkah dengan validasi server; kolom sandi ditolak; teks injeksi ditandai; tidak ada kiriman ke server sebelum klik final.
- Cacat ditemukan: cookie sesi (tanpa kedaluwarsa) hilang dari profil Chromium. Perbaikan: `chunai login` menyimpan `data/browser_state.json` (chmod 600, tidak ikut cadangan) dan cookie dipulihkan saat start, hanya untuk domain di allowlist.
- Ditambah: elemen ber-`role` (combobox, option, tab, dst.), iframe yang domainnya diizinkan, peringatan CAPTCHA dan halaman login.
- Agen asli (Claude) di situs tiruan yang sama: 23 dtk, hanya 2 kartu izin (klik "Lanjut" dan kirim form), data di server tepat, injeksi di langkah 2 diabaikan dan dilaporkan ke pengguna, kolom sandi/telepon dibiarkan kosong. Catatan: `review` pada langkah 2 hanya menampilkan isian halaman itu, bukan langkah 1.
- Batasan jujur: unggah berkas ditolak (minta pengguna), CAPTCHA tidak diselesaikan agen, iframe domain lain diabaikan, setiap klik minta izin (form multi-langkah = banyak kartu izin), dropdown kustom hanya lewat `klik`. Belum diuji di situs nyata.

## 5d. Allowlist domain: izin per situs lewat kartu (16 Okt 2026, atas permintaan pengguna)
Tanpa setelan manual per situs. `buka_halaman` ke situs baru memunculkan kartu "SITUS BARU": Setuju = sesi ini, ♾ Selalu = disimpan di `data/allowlist.txt` (per DOMAIN, bukan per tool).
Tetap: alamat internal/privat DITOLAK (localhost, IP privat, .local; hanya nama/IP, tanpa DNS), klik/kirim form selalu minta izin, redirect/iframe ke domain belum diizinkan diblokir,
sandi/OTP tidak diisi. Entri manual di allowlist (mis. 127.0.0.1 untuk uji) tetap berlaku.

## 5e. Klik navigasi tanpa kartu (16 Okt 2026, disetujui pengguna)
`policy.click_is_safe`: pilih opsi/centang, tab, tautan http(s), tombol Lanjut/Next/Berikutnya/Kembali berjalan tanpa kartu (tercatat di audit). Gagal-tertutup: tombol lain,
teks Kirim/Selesai/Bayar/Hapus/Simpan/Keluar/Kumpulkan/Masuk dst., role switch, dan galat apa pun tetap minta kartu. `kirim_form` selalu kartu. Uji agen asli: kartu 2 → 1.
Catatan risiko: tombol "Lanjut" pada wizard bisa mengirim data antar-langkah ke server (bukan pengiriman akhir). Aturan ujian di prompt: kerjakan survei/latihan/kuis buatan sendiri; ujian resmi yang melarang bantuan → tanya konteks.

## 5f. Skill baru #1: revisi dokumen (19 Okt 2026)
Tool `baca_dokumen` (ID bernomor: DOCX `P12`, `T1R2C3`; PPTX `S5.sh3`, `S5.sh7.r2c3`, grafik) dan `revisi_dokumen` (ops: ganti_teks, ganti_paragraf, sisip_setelah, hapus, ganti_sel;
PPTX: ganti_shape_teks, ganti_sel, ganti_data_grafik). Modul `office/revise.py`. Hasil = SALINAN `output/<nama>_rev.*`, berkas asli tidak ditimpa, format dipertahankan (penggantian per run),
semua perubahan divalidasi dulu (gagal satu = tidak ada yang berubah). Terverifikasi: render LibreOffice (slide dan dokumen tampak benar) dan agen asli (27 dtk: hanya angka diminta berubah,
ketidakkonsistenan di slide 5 dilaporkan, bukan diubah diam-diam). Batas: footer/header hanya lewat penggantian global; grup bentuk bernomor `sh3.1`; komentar/revisi-terlacak tidak ditangani.
Urutan skill yang dipilih pengguna (bertahap): 1 revisi dokumen (SELESAI), 2 pengingat/terjadwal, 4 ringkas dokumen panjang, 8 gambar AI gratis. Memori profil sempat dikerjakan tetapi
belum diminta: disimpan di `git stash` ("memori-profil-belum-diminta").

## 5g. Skill baru #2: pengingat dan tugas terjadwal (19 Okt 2026)
Modul `schedule.py` (jadwal murni: sekali/harian/mingguan/bulanan, WIB, penyimpanan `data/schedules.json`), `interfaces/scheduler.py` (penjadwal, jalan di `chunai serve` dan `chunai telegram`),
tool `buat_jadwal` (kartu izin dengan pratinjau jadwal nyata), `daftar_jadwal`, `hapus_jadwal` (kartu), perintah Telegram `/jadwal`.
- Pengingat = pesan ke Telegram. Tugas = agen mengerjakan perintah **tanpa pengawasan**: reviewer menolak semua aksi yang butuh izin dan melaporkannya (teruji dengan agen asli: percobaan menulis ke /etc ditolak dan dilaporkan).
- Jadwal dimajukan SEBELUM dijalankan (paling banyak sekali). Komputer mati: terlambat <= 24 jam tetap dijalankan dengan catatan terlambat; lebih lama dilewati dan dilaporkan.
- Batas: maks 20 jadwal, 10 tugas agen, 1 USD per tugas, 15 menit per tugas, batas harian tetap berlaku, tugas dijalankan satu per satu. Tanpa Telegram: hasil disimpan di `data/sessions/jadwal/workspace/hasil/`.
- Batas yang jujur: hanya jalan saat komputer dan ChunAI menyala; tidak ada interval di bawah harian untuk tugas; tugas web hanya ke situs yang sudah diizinkan permanen (situs baru = ditolak tanpa kartu).

## 5h. Skill baru #4: ringkas dokumen panjang bersitasi halaman (19 Okt 2026)
`docread.py` + `docread_tools.py`: `info_berkas`, `baca_berkas` (rentang halaman, penanda `=== hlm N ===`, batas ±12.000 karakter), `cari_berkas`, `periksa_kutipan` (ok / halaman_lain / mirip / tidak_ada),
subagen `pembaca` (rentang ±40 halaman, paralel). PDF via `pdftotext` (poppler, sudah dipasang `install_wsl.sh`), PPTX per slide (termasuk catatan pembicara dan data grafik), DOCX via konversi LibreOffice
(nomor halaman mendekati Word), TXT/MD per ±3000 karakter ("bagian"). Isi dokumen dibungkus sebagai DATA + pemindai prompt-injection.
Uji agen asli: PDF 80 halaman dengan 5 fakta tertanam + 1 injeksi: 51 dtk, dua pembaca paralel, kelima sitasi halaman benar (12, 27, 30, 47, 63), injeksi dilaporkan dan tidak diikuti, periksa_kutipan dipanggil.
Batas jujur: PDF hasil pindai (tanpa teks) TIDAK terbaca (OCR belum ada; dilaporkan terus terang); tabel di PDF jadi teks tata letak (kolom bisa bergeser); maks 60 MB / 3000 halaman; Telegram membatasi unggahan 20 MB.
Urutan skill pengguna: 1 revisi dokumen (selesai), 2 jadwal (selesai), 4 ringkas dokumen (selesai), 8 gambar AI gratis (DITUNDA atas keputusan pengguna 19 Okt; perlu riset penyedia gratis, uji nyata di komputer pengguna).
Sisa daftar tunda: 3 Excel (rumus+grafik), 5 tema/logo (butuh bahan pengguna), 6 draf email/surat, 7 memori profil (kode ada di `git stash` "memori-profil-belum-diminta"), email baca/kirim dan isi form berkas (`docs/RENCANA_SKILL_BARU.md`), fase evaluasi 1-2 minggu, keputusan server 24 jam.

## 5i. Web Agent lanjutan T0-T2 + pagar sosial (19 Okt 2026; rencana: `docs/RENCANA_WEB_AGENT_LANJUTAN.md`)
- **CDP (T0):** agen memakai tab BARU di Chrome pengguna (tab pengguna tidak disentuh; saat selesai hanya tab agen ditutup). `chunai cdp-help` (panduan + cek koneksi), `chunai doctor` memeriksa bila `CHUNAI_BROWSER=cdp`,
  `scripts/start-chrome-cdp.ps1`. Win11 + WSL2: `networkingMode=mirrored`. Teruji dengan Chromium sungguhan (tes). BELUM teruji di Chrome/Windows pengguna.
- **Peta soal + rencana isian (T1):** `peta_form` (soal, jenis, opsi, wajib, batas karakter, ⚠DATA PRIBADI), `simpan_rencana/lihat_rencana/ubah_rencana`, `setujui_rencana` (KARTU izin berisi tabel),
  `terapkan_rencana` (isi draf + selisih), `periksa_kesesuaian`. Rencana disimpan di `workspace/rencana/<nama>.json` (bisa dilanjutkan). Butir tanpa dasar = `tidak_ada` (dilewati, tidak ditebak).
- **Editor teks kaya + unggah (T2):** `isi_field` mendukung contenteditable/role=textbox; `unggah_berkas` (hanya workspace, jenis dibatasi, kartu, tanpa "selalu"; bisa lewat tombol yang membuka dialog berkas).
- **Lembar data diri:** `data/data_diri.json` (izin 600, tidak di repo/cadangan); tingkat umum/pribadi/sensitif; `lihat_data_diri`, `simpan_data_diri` (batch, kartu dengan nilai disamarkan), `lupa_data_diri`. Tidak diinjeksi otomatis ke prompt.
  Uji agen asli dengan CV pengguna: 43 butir (27 umum, 8 pribadi, 8 sensitif), kontak referensi orang lain sengaja tidak disimpan.
- **Pagar media sosial (F8):** `social.py`: LinkedIn/Instagram/Facebook/X/TikTok/Threads: tindakan keluar (klik non-navigasi, kirim_form) dihitung per hari (default 15, `CHUNAI_SOCIAL_DAILY_LIMIT`, 0 = tanpa batas)
  dan diberi jeda minimum tetap 20 dtk; tanpa trik menghindari deteksi. Melebihi batas = ditolak tanpa kartu.
- Uji agen asli (kuis latihan + materi PDF): tabel rencana benar, tidak ada kiriman sebelum persetujuan, kartu setujui_rencana + kartu kirim, data server sesuai, injeksi dilaporkan.
- Belum: T3 uji nyata LinkedIn/Instagram (hanya di komputer pengguna), T4 lamaran kerja (prompt sudah ada, belum diuji di situs), T5 kuis interaktif timer. Prompt memuat aturan konten profesional/ujian.

## 5j. T3 (LinkedIn/Instagram) dan T4 (lamaran) disiapkan (19 Okt 2026; atas permintaan pengguna TANPA uji di situs nyata)
- `periksa_draf_sosial` (batas karakter LinkedIn/Instagram, jumlah hashtag, kebocoran data pribadi/sensitif dari lembar data diri). Kartu posting/kirim di situs sosial menambah baris "⚠ PERHATIAN, isi halaman memuat data pribadi Anda" bila ada.
- Langkah "Review/Tinjau lamaran" dianggap navigasi (tanpa kartu); "Easy Apply", "Submit application", "Post", "Connect", "Kirim" tetap kartu. Prompt memuat alur lamaran (cocokkan lowongan dengan data diri, pertanyaan dihitung dari riwayat, unggah CV lewat kartu, satu lamaran per kartu).
- Terverifikasi hanya: tes otomatis (223) dan agen asli memanggil `periksa_draf_sosial`. BELUM diuji di LinkedIn/Instagram asli: selektor/editor mereka bisa berbeda; kirim tangkapan layar atau jawaban agen bila ada yang gagal.

## 5k. Terverifikasi di komputer pengguna (19 Okt 2026)
- Kode terbaru terpasang; `chunai doctor` hijau semua, termasuk "Chrome sendiri (CDP) terhubung ke Chrome/154" (Win11, WSL `networkingMode=mirrored`, Chrome profil `C:\chunai-chrome`).
- Telegram: CV diterima; draf headline LinkedIn dari CV tersusun tanpa mengisi apa pun; kartu SITUS BARU (alamat lengkap) muncul; agen membuka beranda LinkedIn dengan sesi login pengguna (tab baru) dan hanya membaca.
- Pengguna menyatakan "sudah bisa berjalan baik". Belum dicoba: mengisi kolom headline di dialog edit LinkedIn (uji "isi tapi jangan simpan"), posting, lamaran, Instagram. Itu langkah uji berikutnya.
- Pelajaran: perintah PowerShell untuk Chrome harus memakai `Start-Process` (baris dengan path berkutip tanpa `&` error di PowerShell); `chunai cdp-help` pada versi lama jatuh ke mode chat (tanda kode belum diperbarui);
  jangan menggabungkan `pytest | tail` dengan `&&` untuk menggerbangi commit (kode keluar `tail` selalu 0): pakai kode keluar pytest langsung.

## 5l. Skill analisis saham T0+T1 (19 Okt 2026; rencana: `docs/RENCANA_SKILL_SAHAM.md`)
Paket `src/chunai/saham/`: `store.py` (data/saham/<KODE>/prices.csv + meta.json dengan jejak sumber: sumber, metode diunggah/dicari, berkas, sha256, periode, tanggal ambil), `impor.py` (CSV/TSV/XLSX ekspor platform; header terdeteksi
walau ada baris pembuka; kolom Indonesia/Inggris; format angka 1.234,56 vs 1,234.56 disimpulkan atau diminta; tanggal DD/MM vs MM/DD; tanggal ganda), `validasi.py` (kesegaran, bolong, OHLC konsisten, lonjakan >35% = kemungkinan aksi korporasi,
volume nol; hasil lolos/lolos_dengan_catatan/ditolak), `teknikal.py` (SMA, EMA, RSI Wilder, MACD, Bollinger, ATR Wilder, support/resistance swing, tren, kinerja, volatilitas, likuiditas; rencana trading: ukuran lot dari batas rugi,
fraksi harga IDX, biaya beli 0,15%/jual 0,25%, target 1R/2R/3R, peringatan likuiditas), `profil.py` (horizon, toleransi, modal, batas rugi <=5%, preferensi, posisi), `tools.py` (impor_data_saham, daftar_data_saham, periksa_data_saham,
analisis_teknikal, rencana_trading, bandingkan_saham, grafik_saham, profil_investor, simpan_profil_investor[kartu]). Prompt "Analis saham" memuat standar (tanpa kata kepastian, tanggal+sumber, bear case, apa yang BELUM dianalisis).
Verifikasi: indikator dicocokkan dengan hitungan acuan independen (RSI Wilder dengan nilai manual 70,4545, SMA/EMA/ATR loop murni), rencana trading dihitung ulang manual; agen asli (TLKM sintetis, format Stockbit gaya Indonesia): impor, validasi,
analisis, 2 opsi stop, angka cocok hitung ulang (95 lot, rugi ≈ Rp2,08 jt), menyatakan fundamental/valuasi/berita/dividen BELUM dianalisis dan tidak memberi kepastian. Tes 237 lolos.
BELUM: T2 pencarian otomatis (pintu 1) + fundamental + valuasi (relatif, DCF/DDM), T3 gerbang `periksa_analisis` + laporan DOCX/PPTX + penyaringan, T4 rekam jejak + watchlist terjadwal. Uji dengan data pasar NYATA hanya di komputer pengguna.

## 5m. Skill saham T2-T4 (20 Okt 2026)
- **Fundamental** (`saham/fundamental.py`, `fund_tools.py`): `catat_fundamental` mencatat angka dari PDF laporan keuangan HANYA bila `teks_angka` terbukti ada di halaman yang disebut dan cocok dengan nilai (satuan Rp dikonversi; capex mutlak; periode kumulatif
  `YYYY-FY|9M|6M|3M`; jejak sumber+halaman per angka); `impor_fundamental` (XLSX/CSV, label dipetakan); `analisis_fundamental` (margin, ROE rata-rata ekuitas, DER, FCF, CFO/laba, TTM = FY lalu + YTD − YTD tahun lalu, EPS, BVPS, PER, PBV, yield, payout; rekonsiliasi
  aset=liabilitas+ekuitas, satuan antar periode, laporan lama). `valuasi_saham`: DCF (FCF sebagai proksi), DDM dua tahap, relatif (butuh sumber pembanding); asumsi WAJIB eksplisit, batas wajar (diskonto 5-30%, g terminal -2..7%, r−g >= 1 poin), rentang sensitivitas 3x3,
  porsi nilai terminal, margin of safety. Diverifikasi dengan hitungan acuan independen.
- **Pintu 1:** `unduh_berkas` (`download.py`): PDF/XLSX/CSV dari domain yang disetujui lewat kartu (sama seperti buka_halaman; privat ditolak; pengalihan diperiksa per langkah; jenis dicek dari isi, HTML/login ditolak; maks 30 MB; jejak URL disimpan).
  Situs yang memblokir otomatisasi: agen meminta unggahan, tidak mengakali. BELUM diuji di situs IDX/emiten asli (hanya server uji lokal).
- **Gerbang kualitas** `periksa_analisis` (`lint.py`): wajib pernyataan bukan nasihat, tanggal data, sumber, risiko, keterbatasan; skenario pesimis + syarat pembatalan bila ada rekomendasi; asumsi bila ada klaim valuasi; larangan kata kepastian;
  penelusuran angka ke keluaran tool sesi ini (registri; angka tak tertelusuri = peringatan, >50% = gagal).
- **Penyaringan** `saring_saham` (`screen.py`): skor 0-100 per faktor (kualitas, valuasi, momentum, risiko) dengan ambang tetap; bobot mengikuti horizon/toleransi/preferensi dividen; faktor tanpa data dilewati dan bobot dinormalkan; filter; tanggal data berbeda diperingatkan.
- **Rekam jejak + watchlist** (`track.py`): `catat_rekomendasi`, `evaluasi_rekam_jejak` (return, target/pembatalan, relatif indeks, ketepatan per keyakinan, catatan sampel < 20 belum bermakna), `watchlist_atur`, `periksa_watchlist` (penembusan level, RSI ekstrem, lonjakan volume, data tidak segar;
  untuk jadwal: hanya membaca data tersimpan).
- Uji agen asli (TLKM sintetis + 2 PDF laporan keuangan): profil, impor, 2 pencatatan fundamental terverifikasi, teknikal, fundamental, valuasi DCF (angka cocok hitung ulang Rp32.222/saham), grafik, rencana trading, laporan DOCX 6 halaman (dirender dan dilihat: grafik, tabel, sensitivitas, skenario, footer),
  `periksa_analisis` 2x sampai LOLOS. Agen MENDETEKSI data sintetis yang tak masuk akal (PER 1,6x, DCF 8,6x harga) dan menolak memberi kesimpulan beli/jual, meminta laporan lengkap. Tes 254 lolos.
- Belum: uji data pasar nyata (hanya di komputer pengguna), pembanding sektor otomatis, backtest aturan skrining (opsional).

## 5n. Galat "CLIJSONDecodeError: JSON message exceeded maximum buffer size" (20 Okt 2026)
Penyebab (terbukti): hasil tool/Read berisi gambar besar (pratinjau halaman/lembar kontak/screenshot) melewati batas 1 MB bawaan SDK untuk satu pesan JSON dari CLI. Perbaikan: `max_buffer_size` 32 MB di `ChunAI._options`,
dan gambar yang dibuat ChunAI diperkecil (`shrink_image`: lebar maks 1600 px, <= ±700 KB). Teruji: agen asli membaca PNG 6,6 MB tanpa galat.

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

## 7a. Posisi terakhir (16 Okt 2026, akhir sesi)
- Selesai dan ter-push: Web Agent (cookie sesi, iframe, role, deteksi CAPTCHA/login, tolak unggah berkas), izin per situs lewat kartu "SITUS BARU", klik navigasi tanpa kartu, aturan kuis diperlonggar. 163 tes lolos.
- Pengguna sudah memasang versi terbaru; tes kartu situs baru di Telegram asli berjalan baik. Antarmuka Web: http://localhost:8787 (token `CHUNAI_WEB_TOKEN`).
- Login situs: manual oleh pengguna (`chunai login <alamat>`; butuh WSLg/Win11, atau mode CDP dengan Chrome sendiri; panduan CDP belum ditulis).
- Belum teruji: Web Agent di situs nyata (Wayground `wayground.com/admin/quiz/...`; diblokir proxy cloud, harus diuji di komputer pengguna), mode CDP, akun Telegram lain ditolak, pytest di Python 3.14 pengguna.
- Berikutnya: (1) pengguna mencoba satu pekerjaan web nyata lalu kirim jawaban agen + `tail -30 data/logs/chunai.log` (tanpa rahasia); (2) panduan login via CDP; (3) fase evaluasi 1-2 minggu (`docs/EVALUASI_2_MINGGU.md`), lalu Tahap 3 (tema/logo), keputusan server 24 jam.

## 7b. Fase evaluasi (disepakati 16 Okt 2026)
Pengguna memakai ChunAI 1–2 minggu di komputernya (langganan, tanpa biaya tambahan), mencatat tugas dan masalah sesuai `docs/EVALUASI_2_MINGGU.md`.
Saat kembali: minta hasil `chunai audit 300` + catatan, jawab 7 pertanyaan evaluasi, lalu susun prioritas (Tahap 3, VPS/API, perbaikan kualitas).

## 8. Cara melanjutkan di sesi baru
Tempel kira-kira: *"Lanjutkan proyek ChunAI. Baca `CLAUDE.md` dan `docs/CATATAN_PROYEK.md`, lalu kita kerjakan Tahap 3: …"*.
Di sesi cloud: tambahkan repo (`hendriawancorp-chunai/chunai`), clone, `pip install -e . && pytest -q`.

## 5o. Web tanpa token (22 Okt 2026)
Permintaan pengguna: akses Web tanpa token. Dibuat opt-in `CHUNAI_WEB_AUTH=off` (default tetap wajib token). Hanya loopback (serve menolak host lain), middleware `local_request_ok` (Host loopback, Origin==Host, Sec-Fetch-Site same-origin/none), `/config` memberi tahu UI agar langsung connect, kunci penandatangan unduhan acak. Approval gate tidak berubah. 262 tes.

## 5p. Biaya harian terhitung berlipat (26 Okt 2026)
Temuan dari `chunai audit` pengguna: biaya "halo" naik terus (0,105 → 0,406). Penyebab: `ResultMessage.total_cost_usd` dari SDK adalah TOTAL BERJALAN per sesi, tetapi `turn_done` mencatatnya sebagai biaya per giliran dan `day_cost` menjumlahkannya, sehingga batas harian tercapai jauh lebih cepat dari pemakaian nyata. Perbaikan: `agent.py` mencatat selisih per giliran (+ `session_total`); `usage._events` menormalkan catatan lama (tanpa `session_total`) dengan selisih antar giliran. Pelajaran: verifikasi arti angka dari SDK sebelum dijumlahkan. Juga: `test_periksa_analisis_tool_uses_session_registry` bergantung tanggal (angka asing 999,9 bertabrakan dengan umur data); kini memilih angka yang pasti asing. Rencana berikutnya (menunggu persetujuan): pemilahan model otomatis + `/model` + `CHUNAI_MODEL`.

## 5q. Pemilah model otomatis (26 Okt 2026)
`router.py` + `Session.start_turn/turn` + `ChunAI.ask(model=)` (SDK `set_model`) + `/model` (Telegram, Web) + penjadwal memakai Haiku. Diuji dengan agen asli: Haiku -> Sonnet -> Haiku dalam satu sesi, model benar-benar berganti (audit `turn_done.model/served`; `served` = semua model yang pernah melayani sesi). Keterbatasan: aturan kata kunci bisa salah memilah (pengguna dapat memaksa `!teliti`); penghematan belum diukur pada pemakaian nyata pengguna (cek `chunai audit` setelah beberapa hari). Belum dibuat: subagen Haiku untuk membaca dokumen panjang (tahap berikutnya).

## 5r. Pagar lunak (26 Okt 2026)
Peringatan sekali per hari pada 80% batas harian; `/lanjut` melonggarkan pagar sampai besok (`SessionManager.allow_today`); `CHUNAI_SESSION_BUDGET_USD` untuk batas per sesi (bawaan 5, 0 = tanpa batas; sebelumnya tertanam 5.0); doctor menampilkan keduanya. Penjadwal tetap memakai batas 1.0 per tugas.

## 5s. Jalur kunci API (cadangan tanpa langganan) (26 Okt 2026)
`CHUNAI_AUTH`, `chunai auth-key`, `chunai mode`, `apply_auth_mode`, galat Claude berbahasa Indonesia. Kunci disimpan sebagai CHUNAI_API_KEY (bukan ANTHROPIC_API_KEY) agar tidak terpakai tanpa sengaja. Belum diuji dengan kunci asli; pengguna perlu `chunai doctor --live` setelah beralih. 293 tes.

## 5t. Pengukuran beban awal (26 Okt 2026)
Perkiraan awal saya (40-50 ribu token) KELIRU; terukur ±29,6 ribu di cloud. Rincian di OPERASIONAL.md. Perintah baru `chunai ukur`. Pelajaran: jangan menyimpulkan penghematan dari angka perkiraan; matikan tool bawaan justru menambah beban (MCP tidak lagi ditunda). Penghematan terbesar tetap pemilah model (Haiku vs Opus 25x), bukan diet prompt (potensi ~10%).
