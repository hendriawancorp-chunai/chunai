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
