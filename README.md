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

## Roadmap
0 Fondasi ✅ · 1 Riset ✅ + Analisis data ✅ · 3 Web Agent · 2 Dokumen/PPT · 4 Media · 5 Penguatan
