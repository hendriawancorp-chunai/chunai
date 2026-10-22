# Komparasi "otak" ChunAI (22 Okt 2026)

## Pertanyaan
Adakah alternatif pengganti Claude sebagai otak ChunAI yang lebih efektif dan efisien?

## Fakta arsitektur
- ChunAI dibangun di atas Claude Agent SDK (harness Claude Code). Gerbang izin (hook PreToolUse), tool in-process, subagen, dan batas biaya berjalan di sisi harness, bukan di model.
- Anthropic menyatakan tidak mendukung pengalihan Claude Code ke model non-Claude lewat gateway apa pun (https://code.claude.com/docs/en/llm-gateway). Beberapa penyedia menawarkan endpoint kompatibel-Anthropic (DeepSeek, Z.ai/GLM, Moonshot/Kimi, Alibaba/Qwen)
  yang bisa dipakai lewat `ANTHROPIC_BASE_URL`, tetapi itu konfigurasi tak resmi (bisa rusak saat pembaruan), memakai kunci API penyedia itu (tanpa langganan Claude), dan fidelitas tool/gambar/subagen harus diuji.
- Mengganti ke OpenAI/Gemini langsung berarti menulis ulang lapisan agen (loop tool, hook izin, subagen, MCP in-process): pekerjaan besar dan berisiko pada pagar keamanan.

## Harga (per 1 juta token, masukan/keluaran; sumber resmi via pencarian, bisa berubah)
| Model | Masukan | Keluaran | Catatan |
|---|---|---|---|
| Claude Haiku 5.5 | $0,10 | $0,50 | (prompt <= 100K token) |
| Claude Sonnet 5.5 | $2,00 | $10,00 | |
| Claude Opus 5.5 | $4,00 | $20,00 | |
| Claude Fable 5.1 | $10,00 | $50,00 | terkuat, termahal |
| OpenAI GPT-6 Luna / Sol / Astra | $0,10 / $2 / $10 | $0,50 / $10 / $50 | halaman model OpenAI |
| Gemini 3 Flash Preview; 3.1 Pro Preview | $0,50; $2-4 | $3; $12-18 | halaman harga Google |
| DeepSeek V4.1 Flash | ±$0,15-0,30 (cache miss) | ±$0,60-1,20 | puncak/non-puncak; halaman harga DeepSeek berbeda-beda, WAJIB diperiksa langsung |
Harga bukan tolok ukur tunggal: efisiensi sebenarnya = biaya per tugas selesai dan benar.

## Pengujian sendiri di tugas ChunAI (3 kali per sel; model dijalankan lewat ChunAI(model=...); biaya = "biaya setara" tarif API dari SDK)
| Tugas (skor maks) | Haiku 5.5 | Sonnet 5.5 | Opus 5.5 |
|---|---|---|---|
| Revisi PPTX satu angka (1) | 1,1,1; $0,005; 16 dtk | 1,1,1; $0,08-0,17; 17 dtk | 1,1,1; $0,19-0,36; 20 dtk |
| Ringkas PDF 80 hlm + sitasi + injeksi (5) | 4,5,5; $0,025; 50 dtk | 5,5,5; $0,33; 45 dtk | 5,5,5; $0,70-0,75; 50 dtk |
| Analisis saham: profil, impor, teknikal, rencana (9) | 8,5,7; $0,011; 40 dtk | 9,8,9; $0,10-0,13; 28 dtk | 9,9,9; $0,21; 34 dtk |
| Form kuis web 2 langkah + materi + data diri + persetujuan (7) | 6,0,0 (+6); $0,018; 40 dtk | 6,6,6 (+7); $0,23-0,33; 70 dtk | 7,7,7; $0,48; 45 dtk |
Catatan hasil: Haiku salah pada form (tidak memakai lembar data diri, kota terisi default; dua kali tidak menyelesaikan); varian lebih besar pada analisis saham. Opus paling konsisten. Sonnet hampir setara dengan biaya sekitar separuh Opus.
Total satu putaran 4 tugas (median): Haiku ±$0,06; Sonnet ±$0,76; Opus ±$1,6.
Batas pengujian: tugas sintetis, 3 sampel, situs tiruan; model non-Claude TIDAK diuji (tak ada kunci/akses, dan tidak didukung resmi).

## Opsi
| Opsi | Efektif | Efisien | Risiko | Kesimpulan |
|---|---|---|---|---|
| A. Tetap Claude, atur model per jenis tugas (Haiku/Sonnet/Opus) | Tinggi | Sangat baik (hemat 2-25x) | Rendah; semua pagar utuh | DIREKOMENDASIKAN |
| B. Endpoint kompatibel-Anthropic (DeepSeek/GLM/Kimi/Qwen) | Belum terbukti untuk ChunAI | Biaya token sangat rendah | Tak didukung resmi; kunci API terpisah; data (CV, keuangan) ke penyedia lain; gambar/subagen belum tentu jalan; injeksi prompt belum teruji | Eksperimen opsional dengan uji yang sama, bukan pengganti |
| C. Tulis ulang untuk OpenAI/Gemini | Tidak pasti | Tergantung | Tinggi (pagar keamanan harus dibangun ulang) | Tidak disarankan sekarang |
| D. Model lokal (Ollama) | Rendah untuk tool multi-langkah di laptop | Gratis, privat | Kualitas, bahasa Indonesia, konteks panjang | Hanya untuk tugas ringan privat, bukan otak utama |
