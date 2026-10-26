# Operasional ChunAI (harian, cadangan, keamanan)

Semua perintah dijalankan di jendela Ubuntu (WSL) di folder `~/chunai` dengan lingkungan aktif:
```bash
cd ~/chunai && source .venv/bin/activate
```

## 1. Menjalankan dan menghentikan
| Tujuan | Perintah |
|---|---|
| Menjalankan (Web + Telegram, restart otomatis) | `./scripts/run.sh` (biarkan jendela terbuka) |
| Menghentikan | `Ctrl+C` di jendela itu |
| Otomatis saat Windows login | lihat `docs/PANDUAN_WINDOWS.md` (bagian `schtasks`) |
| Periksa kesehatan | `chunai doctor` (tambahkan `--live` untuk uji Claude nyata) |
| Lihat log | `tail -n 50 data/logs/chunai.log` |

Bot hanya aktif selama komputer menyala dan tidak tidur. Atur Windows: *Power & sleep → Never* saat daya tersambung.

## 2. Membaca catatan audit
```bash
chunai audit          # 30 catatan terakhir
chunai audit 100      # 100 catatan terakhir
```
Contoh: `PERINTAH`, `IZIN?`, `KEPUTUSAN DISETUJUI/DITOLAK`, `DIBLOKIR`, `KIRIM FILE`, `SELESAI biaya setara $...`.
Setiap aksi berdampak (tulis file, perintah Bash di luar baca-saja, klik/kirim form) tercatat beserta keputusan Anda.
Berkas mentahnya: `data/sessions/<pengguna>/audit.jsonl` (waktu dalam zona waktu Anda).

## 3. Batas pemakaian harian
Pengaman terhadap tugas yang berulang tanpa henti. Pada langganan, angka ini adalah "biaya setara" (bukan tagihan).
- Media sosial: batas tindakan keluar per hari `CHUNAI_SOCIAL_DAILY_LIMIT` (default 15). Chrome sendiri: `CHUNAI_BROWSER=cdp`, `CHUNAI_CDP_URL=http://127.0.0.1:9222`. Data diri: `data/data_diri.json` (jangan dibagikan).
- Default: **$20/hari**. Ubah di `.env`: `CHUNAI_DAILY_BUDGET_USD=40` (0 = tanpa batas), lalu jalankan ulang.
- Bila tercapai, bot membalas pesan yang menjelaskan dan tidak menjalankan tugas baru sampai besok.
- Telegram `/status` menampilkan pemakaian hari ini.

## 4. Cadangan
```bash
./scripts/backup.sh            # ke ~/chunai-backup (14 cadangan terakhir disimpan)
```
Berisi percakapan, hasil kerja, audit, tema, dan daftar domain. **Tidak** berisi `.env`, `.venv`, atau profil browser
(berisi sesi login). Simpan `.env` Anda di pengelola kata sandi, bukan di cadangan.
Pulihkan: `tar -xzf ~/chunai-backup/chunai-YYYYMMDD-HHMM.tar.gz` di folder `~/chunai`.
Cadangan harian otomatis (opsional): `crontab -e` lalu tambahkan
`0 18 * * * cd ~/chunai && ./scripts/backup.sh >/dev/null 2>&1` (WSL perlu sedang berjalan).

## 5. Pembaruan
Unduh ZIP terbaru, ekstrak, lalu `cp -r /mnt/c/Users/NAMA/Downloads/chunai-main/. ~/chunai/`. `.env`, `.venv`, dan `data/`
tidak tertimpa. Hentikan ChunAI sebelum menyalin dan jalankan ulang sesudahnya.

## 6. Daftar periksa keamanan
`chunai doctor` memeriksa butir bertanda ⚙ secara otomatis.

- [ ] ⚙ `.env` berizin 600 dan tidak pernah dibagikan atau di-commit
- [ ] ⚙ Token Web panjang (>= 24 karakter); Web hanya di `127.0.0.1`
- [ ] ⚙ `CHUNAI_TELEGRAM_USERS` terisi (hanya ID Anda); pesan dari orang lain ditolak
- [ ] ⚙ Batas pemakaian harian aktif
- [ ] Tiap permintaan 🔒 dibaca sebelum **Setuju**; jangan menekan "Selalu izinkan" untuk `Bash`
- [ ] Token bot/Claude yang pernah terlihat orang lain dibuat ulang (BotFather `/revoke`; `chunai auth`)
- [ ] Dokumen berklasifikasi rahasia tidak diproses lewat Telegram/cloud tanpa izin instansi
- [ ] Jangan membuka port 8787 ke internet tanpa HTTPS; akses jarak jauh lewat VPN/tunnel
- [ ] Web Agent: daftarkan hanya domain tepercaya di `data/allowlist.txt`; login dilakukan sendiri oleh Anda
- [ ] Tinjau `chunai audit` secara berkala

## 7. Rotasi token
- **Claude:** `chunai auth` (token baru otomatis tersimpan; cabut yang lama di pengaturan akun Claude bila perlu).
- **Telegram:** di @BotFather `/revoke` pada bot, lalu `chunai setup-telegram`.
- **Web:** ganti nilai `CHUNAI_WEB_TOKEN` di `.env` dengan teks acak panjang, jalankan ulang.
- **Web tanpa token:** `CHUNAI_WEB_AUTH=off` (opt-in). Hanya jalan di 127.0.0.1; server menolak start bila `CHUNAI_HOST` bukan localhost. Pengaman: validasi Host (anti DNS rebinding), Origin/Sec-Fetch-Site (anti CSRF/WebSocket lintas situs), unduhan tetap bertanda tangan dengan kunci acak per-proses. Risiko: proses lain di komputer yang sama bisa memakai ChunAI.

## Pemilah model (hemat biaya)
- Kode: `src/chunai/router.py` (aturan kata kunci, tanpa panggilan LLM tambahan). Tingkat: ringan=Haiku, sedang=Sonnet, berat=Opus; id model dapat diganti dengan `CHUNAI_MODEL_RINGAN/SEDANG/BERAT`.
- Aturan keras: tugas web/aksi tidak pernah ke Haiku. Pengaman (kartu izin, allowlist, sandbox) tidak bergantung pada model.
- Pengaturan: `/model` (Telegram dan Web), awalan `!cepat`/`!teliti`, `CHUNAI_MODEL` (kunci satu model), `CHUNAI_MODEL_AUTO=off`.
- `chunai audit` menampilkan model tiap giliran (`SELESAI [Haiku] ...`). Catatan: tiap model punya cache sendiri; pemakaian pertama sebuah model dalam sesi lebih mahal (uji: Sonnet giliran pertama ±$0,12, lalu Haiku ±$0,002-0,006).

## Jalur Claude: langganan atau kunci API
- `CHUNAI_AUTH=langganan` (bawaan): `CLAUDE_CODE_OAUTH_TOKEN`; `ANTHROPIC_API_KEY` dibuang dari lingkungan proses bila token langganan ada. `CHUNAI_AUTH=api`: kunci dari `CHUNAI_API_KEY` (atau `ANTHROPIC_API_KEY`), token langganan dibuang. Logika: `envfile.apply_auth_mode`, dipanggil di `cli.main` setelah `load_env`.
- Perintah: `chunai auth-key`, `chunai mode api|langganan`; `chunai doctor` menampilkan jalur aktif.
- Galat Claude (kuota/saldo/otorisasi/batas sesi) kini diterjemahkan ke saran berbahasa Indonesia (`doctor.explain_error`, dipakai `ChunAI.ask` saat `ResultMessage.is_error`).
- BELUM diuji dengan kunci API asli (sesi cloud memakai proxy; tidak ada kunci). Yang teruji: logika pemilihan, penyimpanan kunci tanpa dicetak, terjemahan galat. Uji nyata: `chunai mode api` lalu `chunai doctor --live`.

## Beban awal token (diukur 26 Okt 2026, sesi cloud, Haiku, pesan "halo")
- Penuh: ±29,6 ribu token. Prompt sistem ChunAI sendiri: ±7,4 ribu (±15 ribu karakter). Pengaturan/skill lingkungan cloud: ±2,9 ribu (`setting_sources=[]` menghapusnya). Subagen ±0,3 ribu. 49 tool MCP ChunAI hanya ±0,8 ribu karena CLI menunda definisinya (ToolSearch); bila tool bawaan dimatikan (`tools=[]`) definisi lengkapnya ±12 ribu ikut dimuat, jadi JANGAN mematikan tool bawaan.
- Sisanya (±18 ribu) = tool bawaan CLI dan lingkungan cloud (banyak tool/skill khusus cloud); di komputer pengguna berbeda. Ukur di sana: `chunai ukur` (3 pesan kecil di Haiku).
- Mematikan tool bawaan tertentu (`disallowed_tools`) TIDAK mengecilkan beban (diuji). Penghematan terkendali yang tersisa: memecah prompt ChunAI (±7,4 ribu) per topik (potensi ±3-4 ribu) dan `setting_sources=[]` (bila hasil `chunai ukur` pengguna menunjukkan selisih berarti).
