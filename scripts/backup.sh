#!/usr/bin/env bash
# Cadangan data ChunAI (percakapan, workspace hasil kerja, audit, tema, daftar domain).
# TIDAK menyertakan .env (rahasia), .venv, maupun profil browser (berisi sesi login).
# Pemakaian: ./scripts/backup.sh [folder_tujuan]   (default: ~/chunai-backup; menyimpan 14 cadangan terakhir)
set -euo pipefail
cd "$(dirname "$0")/.."
DEST="${1:-$HOME/chunai-backup}"
mkdir -p "$DEST"
STAMP="$(date +%Y%m%d-%H%M)"
OUT="$DEST/chunai-$STAMP.tar.gz"
ITEMS=()
for p in data/sessions data/themes data/allowlist.txt data/logs; do [ -e "$p" ] && ITEMS+=("$p"); done
if [ "${#ITEMS[@]}" -eq 0 ]; then echo "Belum ada data untuk dicadangkan."; exit 0; fi
tar --exclude='.tmp' --exclude='.mpl' --exclude='browser_profile' -czf "$OUT" "${ITEMS[@]}"
chmod 600 "$OUT"
ls -1t "$DEST"/chunai-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm -f
echo "Cadangan: $OUT ($(du -h "$OUT" | cut -f1))"
echo "Pulihkan: tar -xzf $OUT   (dijalankan di folder ChunAI)"
