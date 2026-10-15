#!/usr/bin/env bash
# Menjalankan ChunAI (Web + Telegram) dan memulai ulang otomatis bila berhenti. Hentikan dengan Ctrl+C.
cd "$(dirname "$0")/.."
# shellcheck disable=SC1091
. .venv/bin/activate
mkdir -p data/logs
LOG=data/logs/chunai.log
trap 'echo "$(date "+%F %T") dihentikan oleh pengguna" >> "$LOG"; exit 0' INT TERM
while true; do
  if [ -f "$LOG" ] && [ "$(stat -c %s "$LOG")" -gt 5242880 ]; then mv "$LOG" "$LOG.1"; fi
  echo "$(date '+%F %T') ChunAI mulai" >> "$LOG"
  python -m chunai.cli serve >> "$LOG" 2>&1 || true
  echo "$(date '+%F %T') ChunAI berhenti; mulai ulang dalam 10 detik" >> "$LOG"
  sleep 10
done
