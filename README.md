# ChunAI

AI Agent Assistant pribadi: riset, analisis data, kajian, presentasi, media, dan kerja web
dengan **persetujuan sebelum eksekusi akhir**.

## Jalankan
```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
export ANTHROPIC_API_KEY=...     # jangan di-commit
chunai                            # mulai chat
pytest                            # jalankan tes
```

## Struktur
- `policy.py`   – baca bebas / tulis minta izin / berbahaya ditolak (default tak dikenal = minta izin)
- `approval.py` – Approval Gate (reviewer pluggable: CLI sekarang, Telegram/web nanti)
- `audit.py`    – audit log JSONL (`data/audit.jsonl`)
- `agent.py`    – orkestrator (Claude Agent SDK)
- `agents.py`   – subagen: peneliti, analis

## Web Agent (form, survei, kuesioner, portal)
Alur: buka → baca → isi (DRAF) → review (nilai nyata dari halaman + screenshot) → **izin Anda** → kirim.

```bash
# 1. daftar situs yang boleh dibuka tanpa tanya (satu domain per baris)
echo "portal.contoh.go.id" >> data/allowlist.txt      # atau env CHUNAI_ALLOWED_DOMAINS=a.com,b.com

# 2. situs yang butuh login -> login MANUAL sekali (jalankan di komputer Anda, bukan cloud)
chunai login https://portal.contoh.go.id               # jendela browser terbuka, Anda login sendiri
CHUNAI_BROWSER=profile CHUNAI_HEADLESS=0 chunai        # agen melanjutkan dengan sesi tersimpan

# alternatif: sambung ke Chrome Anda yang sudah login
#   chrome --remote-debugging-port=9222 ; lalu CHUNAI_BROWSER=cdp chunai
```
Pengaman: allowlist domain (juga setelah redirect), kolom password/OTP/kartu tidak pernah diisi agen,
isi halaman dibungkus sebagai data + pemindai prompt-injection, klik & kirim **selalu** minta izin
(tidak bisa "selalu izinkan"). Tidak untuk menjawab ujian/penilaian yang dinilai atau diawasi.

## Roadmap
0 Fondasi ✅ · 1 Riset ✅ + Analisis data ✅ · 3 Web Agent ✅ · 2 Dokumen/PPT · 4 Media · 5 Penguatan
