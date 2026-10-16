# Evaluasi pemakaian 1–2 minggu

Tujuan: memakai ChunAI untuk pekerjaan nyata, lalu memutuskan dari DATA (bukan perkiraan) apakah perlu VPS, kunci API, tema khusus,
atau perbaikan tertentu. Tidak ada biaya tambahan selama memakai komputer sendiri + langganan Claude.

## Sebelum mulai (sekali)
1. Perbarui kode ke ZIP terbaru (`cp -r /mnt/c/Users/NAMA/Downloads/chunai-main/. ~/chunai/`), hentikan lalu jalankan ulang `./scripts/run.sh`.
2. `chunai doctor --live` harus "SIAP dipakai". Pastikan **tidak ada** `ANTHROPIC_API_KEY` di `.env` (agar tetap memakai langganan, bukan API berbayar).
3. Biarkan komputer tidak tidur selama jam kerja dan jendela `run.sh` terbuka.

## Selama pemakaian: catat singkat tiap tugas (cukup di catatan ponsel)
| Tanggal | Tugas (1 kalimat) | Jenis | Hasil 1–5 | Perlu edit manual? | Masalah / catatan |
|---|---|---|---|---|---|
| | | riset / analisis / dokumen / slide / media / web | | tidak / sedikit / banyak | |

Skala hasil: 5 = langsung dipakai, 4 = edit kecil, 3 = edit banyak, 2 = hanya sebagian berguna, 1 = gagal.

Hal yang paling berguna dicatat:
- Jawaban yang **salah atau dikarang** (angka, sumber, nama). Sertakan perintah aslinya.
- Tugas yang **terlalu lama** (> 5 menit) atau **macet**.
- Kartu izin 🔒 yang **mengganggu** (terlalu sering) atau yang **seharusnya muncul tetapi tidak**.
- Format dokumen/slide yang **tidak sesuai selera** (contohkan: "slide ringkasan terlalu kosong").
- Saat bot **tidak menjawab** karena komputer tidur/mati (seberapa sering Anda butuh aktif 24 jam?).

## Di akhir periode: kumpulkan data (aman, tanpa rahasia)
```bash
cd ~/chunai && source .venv/bin/activate
```
```bash
chunai audit 300
```
Menampilkan perintah, izin, keputusan Anda, file terkirim, dan "biaya setara" tiap tugas. Untuk total hari ini: `/status` di Telegram.
Isi pesan Anda tampil di audit (perintah dipotong 70 karakter); periksa dulu sebelum menempelkannya ke chat bila ada hal sensitif.

Periksa juga pemakaian kuota langganan di pengaturan akun Claude (apakah sempat mendekati batas).

## Pertanyaan evaluasi (jawab saat kembali)
1. Berapa tugas per hari rata-rata, dan jenis apa yang paling sering?
2. Rata-rata nilai hasil per jenis tugas? Yang mana paling lemah?
3. Apakah kuota langganan cukup? Seberapa sering mendekati batas?
4. Seberapa sering butuh bot aktif saat komputer mati? (→ keputusan VPS/mini PC)
5. Apakah ada dokumen yang perlu tema/logo/font khusus agar layak kirim? (→ Tahap 3)
6. Apakah ada situs tetap yang ingin diotomatiskan (formulir/portal)? (→ uji Web Agent nyata)
7. Apakah ada keluhan keamanan/kerahasiaan (data yang tidak nyaman lewat Telegram/cloud)?

## Aturan keputusan (usulan)
- Kuota langganan sering habis → pertimbangkan paket lebih tinggi ATAU kunci API dengan batas pengeluaran.
- Butuh aktif saat komputer mati ≥ beberapa kali per minggu → VPS (min. 4 GB RAM) atau mini PC; kunci API untuk server.
- Hasil dokumen rata-rata ≤ 3 → perbaiki prompt/tema/templat sebelum menambah fitur baru.
- Banyak izin 🔒 yang membosankan → tambah aturan baca-saja yang aman; jangan melemahkan gerbang aksi final.

## Yang saya lakukan saat Anda kembali
Baca `CLAUDE.md` dan `docs/CATATAN_PROYEK.md`, lalu minta Anda menempelkan hasil `chunai audit 300` dan catatan di atas. Dari situ
saya menyusun prioritas perbaikan, mengerjakan Tahap 3 (tema, tugas nyata, Web Agent di situs nyata), dan menyiapkan VPS bila perlu.
