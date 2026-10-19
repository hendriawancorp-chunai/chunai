# Rencana Skill Analisis Saham (disusun 19 Okt 2026, BELUM dibangun, menunggu keputusan pengguna)

Tujuan: ChunAI membantu (1) memantau perkembangan saham, (2) evaluasi dan analisis profesional (teknikal, fundamental, valuasi, risiko), (3) menyaring dan memberi **kandidat** saham potensial untuk dibeli
sebagai investasi, lengkap dengan alasan, risiko, dan syarat pembatalan. Keputusan dan eksekusi pembelian tetap di tangan pengguna.

## Prinsip dan batas
- Ini alat bantu analisis, BUKAN nasihat keuangan berlisensi dan bukan jaminan hasil. Setiap laporan memuat: tanggal/jam data, sumber, asumsi, skenario negatif (bear case), dan peringatan risiko.
- Tidak ada eksekusi transaksi dan tidak terhubung ke akun sekuritas. Membeli/menjual dilakukan pengguna sendiri.
- Fakta dipisah dari opini. Semua angka dihitung dengan kode (sandbox), bukan ditebak; data tanpa tanggal atau tidak segar ditandai dan tidak dipakai untuk rekomendasi.
- Output berupa "kandidat untuk ditelaah" dengan tesis, valuasi, risiko, pemicu masuk, dan titik pembatalan; bukan "pasti naik". Bila data tidak cukup: katakan, jangan merekomendasikan.
- Berita dan sentimen lewat pencarian web dengan sitasi sumber (aturan integritas sumber yang sudah ada); rumor/forum ditandai lemah.
- Tidak mengejar hype, tidak menyarankan leverage/margin/gorengan; saham dengan likuiditas rendah ditandai.

## Komponen
| # | Komponen | Isi |
|---|---|---|
| S0 | Lapisan data | Sumber data harga dan laporan keuangan (lihat keputusan di bawah); penyimpanan lokal (`data/saham/`), cap waktu, pemeriksa kesegaran dan kelengkapan data. |
| S1 | Teknikal dan kinerja harga | SMA/EMA, RSI, MACD, volume, ATR/volatilitas, drawdown, tren, support/resistance, kinerja relatif terhadap IHSG/indeks. Diverifikasi silang dengan hitungan independen. |
| S2 | Fundamental dan valuasi | PER, PBV, ROE, ROA, DER, margin, pertumbuhan laba/pendapatan, arus kas, dividen; perbandingan dengan rata-rata sektor dan riwayat sendiri; rentang nilai wajar dengan asumsi eksplisit. |
| S3 | Penyaringan dan skor | Kriteria transparan sesuai profil pengguna (horizon, risiko, dividen, syariah, likuiditas); skor per faktor yang bisa dilihat dan diubah; hasil = daftar kandidat berperingkat dengan alasan. |
| S4 | Laporan profesional | DOCX/PPTX dengan grafik (harga, indikator, valuasi), tesis, risiko, bear case, katalis, ringkasan eksekutif, sumber. Memakai mesin dokumen yang sudah ada. |
| S5 | Pemantauan | Watchlist; ringkasan terjadwal (mis. tiap hari bursa 16.30 WIB) lewat skill jadwal; peringatan perubahan penting (harga menembus level, berita material). Tugas terjadwal tetap hanya membaca/menganalisis. |
| S6 | Opsional | Backtest sederhana atas aturan skrining (dengan peringatan overfitting dan bias data), ukuran posisi/risiko portofolio dasar. |

## Keputusan sumber data (perlu pengguna)
Pasar kemungkinan IDX (kode `.JK`); belum dikonfirmasi. Pilihan (ketersediaan, batas, dan ketentuan layanan harus diperiksa di komputer pengguna sebelum dipakai, tidak bisa saya uji dari cloud):
| Opsi | Catatan |
|---|---|
| A. Ekspor/unduhan pengguna (CSV dari Stockbit/RTI/Ajaib/situs bursa) | Paling pasti legal dan stabil; manual; ChunAI membaca dan menganalisis berkas. |
| B. Pustaka/endpoint gratis tak resmi (mis. Yahoo Finance) | Otomatis, tetapi tak resmi: bisa berubah/terblokir, kualitas data IDX bervariasi, ketentuan layanan perlu diperiksa. |
| C. API berbayar/berlangganan | Lebih andal untuk IDX; ada biaya dan kunci API. |
| D. Situs resmi IDX/emiten (laporan keuangan, keterbukaan informasi) | Sumber primer untuk fundamental; harus lewat kartu situs baru; format bervariasi. |
Usul: mulai A + D (tanpa biaya, sah), lalu B sebagai pelengkap harga otomatis bila lolos pemeriksaan di komputer pengguna.

## Tahap dan pengujian
1. T1: S0 + S1 (data dari berkas, indikator teknikal, laporan harga). Uji: data sampel dengan angka acuan hitung independen; agen asli menganalisis berkas harga.
2. T2: S2 (fundamental, valuasi) dari laporan keuangan unggahan/IDX. Uji: kasus dengan angka diketahui.
3. T3: S3 + S4 (penyaringan, skor, laporan DOCX/PPTX dengan grafik). Uji: render dokumen dan dilihat; aturan "data tidak cukup".
4. T4: S5 (watchlist, ringkasan terjadwal, peringatan).
5. T5 (opsional): S6.
Uji data langsung (sumber nyata) hanya di komputer pengguna.

## Perlu keputusan pengguna
1. Pasar: IDX saja, atau juga saham AS/global?
2. Profil: horizon (jangka pendek/menengah/panjang), toleransi risiko, kisaran modal, preferensi (dividen, syariah, LQ45, sektor).
3. Sumber data: opsi A/D saja, atau juga B/C (biaya)? Punya akun/ekspor dari platform apa?
4. Pemantauan: frekuensi dan jenis peringatan.
5. Format laporan: DOCX, PPTX, atau ringkasan Telegram.

---
# Pembaruan 19 Okt 2026: standar "analis profesional" dan akurasi berbasis sumber kredibel

Permintaan pengguna: analisis saham yang AKURAT, berlandaskan informasi KREDIBEL, dan ChunAI berperan sebagai analis profesional trading, saham, dan investasi.

## Arti "akurat" yang bisa dijanjikan
- BISA dijamin lewat rancangan: angka benar (dihitung kode dari data mentah bersumber), sumber jelas dan tanggalnya, metode dan asumsi terbuka, tidak ada klaim tanpa dasar, skenario negatif selalu ada.
- TIDAK bisa dijamin oleh siapa pun: arah harga di masa depan. ChunAI tidak akan menyatakan kepastian; yang diberikan adalah probabilitas kualitatif, rentang, dan syarat pembatalan.
- Akurasi dibuktikan dari waktu ke waktu lewat catatan rekam jejak (lihat bawah), bukan klaim.

## Hierarki sumber (kredibilitas)
1. Primer: keterbukaan informasi dan laporan keuangan di situs bursa (IDX), situs relasi investor emiten, prospektus, regulator (OJK), bank sentral (BI), statistik resmi (BPS, Kemenkeu).
2. Pasar/berita tepercaya: kantor berita dan media keuangan mapan; data harga dari penyedia berlisensi atau ekspor platform sekuritas pengguna.
3. Lemah (ditandai, tidak boleh jadi dasar tunggal rekomendasi): forum, media sosial, rumor, analis anonim.
Aturan: angka kunci (laba, ekuitas, utang, dividen, jumlah saham) harus dari sumber primer; klaim penting minimal dua sumber independen; bertentangan = dilaporkan, tidak dipilih diam-diam.
Pada situs yang tidak terbuka untuk agen (mis. memblokir otomatisasi), pengguna mengunduh berkas sendiri; agen tidak mengakali pemblokiran.

## Lima lapis pengamanan akurasi
1. Data bersumber: setiap angka tersimpan dengan sumber, tanggal pengambilan, dan periode (kuartal/tahun); data kedaluwarsa ditandai dan tidak dipakai merekomendasikan.
2. Hitung dengan kode: rasio dan indikator dihitung di sandbox dari data mentah tersimpan; tes otomatis membandingkan dengan hitungan acuan independen.
3. Verifikasi silang: rekonsiliasi (laba bersih vs laporan arus kas, jumlah saham vs EPS, total aset = kewajiban + ekuitas), deteksi anomali dan lompatan data.
4. Gerbang kualitas laporan (`periksa_analisis`, seperti `periksa_laporan`): menolak laporan yang angkanya tanpa sumber/tanggal, tanpa asumsi valuasi, tanpa skenario negatif dan risiko, tanpa peringatan, atau yang memakai kata kepastian ("pasti naik", "dijamin").
5. Rekam jejak: setiap kandidat yang dikeluarkan dicatat (tanggal, harga, tesis, target/pembatalan) lalu dievaluasi berkala terhadap hasil dan indeks pembanding; kalibrasi dilaporkan jujur, termasuk yang meleset.

## Standar analisis profesional (isi setiap laporan)
- Ringkasan eksekutif dan kesimpulan (kandidat / pantau / hindari) dengan tingkat keyakinan dan alasan inti.
- Bisnis dan industri: model bisnis, posisi kompetitif, siklus sektor, regulasi, katalis dan risiko.
- Kualitas laba dan neraca: tren pendapatan/margin, arus kas vs laba, utang dan bunga, modal kerja, kualitas dividen, tata kelola dan pihak berelasi.
- Valuasi berlapis: relatif (PER, PBV, EV/EBITDA vs sektor dan riwayat), DCF atau DDM (bila relevan) dengan analisis sensitivitas, dan rentang nilai wajar; asumsi tertulis.
- Skenario: dasar, optimis, pesimis dengan pemicu masing-masing.
- Teknikal dan rencana trading (bila diminta): tren dan struktur harga, level kunci, volume, ATR; titik masuk, pembatalan (stop), target, rasio risiko-imbalan, ukuran posisi berdasarkan batas risiko per transaksi yang ditetapkan pengguna; likuiditas dan biaya transaksi.
- Rezim pasar dan makro (suku bunga, kurs, aliran dana asing, IHSG) sebagai konteks, bukan ramalan.
- Sumber dan tanggal, batasan data, peringatan risiko.

## Pagar tambahan
- Tidak ada eksekusi transaksi dan tidak terhubung ke akun sekuritas. Tidak menyarankan leverage/margin/short, saham gorengan, atau "tip" tanpa dasar.
- Saham dengan likuiditas rendah, status pemantauan khusus/suspensi, atau tata kelola bermasalah ditandai menonjol.
- Bila data tidak memadai: laporan berisi "data tidak cukup untuk menyimpulkan", bukan tebakan.
- Pernyataan jelas bahwa ini analisis pendukung keputusan, bukan nasihat keuangan berlisensi; keputusan dan risiko di tangan pengguna.

## Tahap yang diperbarui
| Tahap | Isi |
|---|---|
| T0 | Keputusan sumber data dan profil pengguna; struktur `data/saham/` dengan metadata sumber dan tanggal |
| T1 | Pemuat data (CSV/ekspor/berkas laporan keuangan), pemeriksa kesegaran dan rekonsiliasi, indikator teknikal terverifikasi |
| T2 | Fundamental dan valuasi berlapis (relatif, DCF/DDM dengan sensitivitas) |
| T3 | Gerbang `periksa_analisis`, laporan profesional DOCX/PPTX dengan grafik, penyaringan dan skor transparan |
| T4 | Rekam jejak dan evaluasi kalibrasi, watchlist dan ringkasan terjadwal setelah bursa tutup, peringatan |
| T5 | Opsional: uji aturan pada data masa lalu (dengan peringatan bias), portofolio dan risiko |
Uji: data sampel dengan angka acuan; laporan dirender dan dilihat; agen asli menganalisis berkas; kasus "data tidak cukup" dan "sumber bertentangan". Uji sumber langsung hanya di komputer pengguna.

## Keputusan yang dibutuhkan untuk mulai T0/T1
1. Pasar: IDX saja, atau juga saham AS/global?
2. Sumber data harga dan laporan keuangan: ekspor platform pengguna (platform apa?), situs resmi IDX/emiten lewat browser, dan/atau penyedia data berbayar berlisensi (paling andal untuk akurasi; ada biaya).
3. Profil: horizon, toleransi risiko, kisaran modal, batas risiko per transaksi, preferensi (dividen, syariah, LQ45, sektor).
4. Fokus awal: investasi (fundamental) atau trading (teknikal), atau keduanya.
