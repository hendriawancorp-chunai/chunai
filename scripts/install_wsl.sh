#!/usr/bin/env bash
# Pemasangan ChunAI di Ubuntu (WSL2 atau Linux). Jalankan dari dalam folder proyek:  bash scripts/install_wsl.sh
# Variabel opsional: SKIP_APT=1 (lewati paket sistem), SKIP_BROWSER=1 (lewati unduhan Chromium)
set -euo pipefail
cd "$(dirname "$0")/.."
say() { printf '\n▶ %s\n' "$*"; }

if [ "$(id -u)" -eq 0 ] && [ "${ALLOW_ROOT:-0}" != "1" ]; then
  echo "Jalankan sebagai pengguna biasa (bukan root)."; exit 1
fi

if [ "${SKIP_APT:-0}" != "1" ]; then
  say "Memasang paket sistem (Ubuntu akan meminta kata sandi Anda)"
  sudo apt-get update -y
  sudo apt-get install -y python3 python3-venv python3-pip ffmpeg poppler-utils \
       libreoffice-writer libreoffice-impress fonts-liberation fonts-dejavu-core curl ca-certificates
  sudo apt-get install -y fonts-inter || true
fi

say "Membuat lingkungan Python (.venv) dan memasang ChunAI"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -e .

if [ "${SKIP_BROWSER:-0}" != "1" ]; then
  say "Memasang Chromium untuk Web Agent dan pembuat gambar"
  python -m playwright install chromium
  sudo "$(command -v python)" -m playwright install-deps chromium || echo "(install-deps dilewati; jalankan manual bila Chromium gagal)"
fi

say "Menyiapkan berkas .env"
if [ ! -f .env ]; then
  cp .env.example .env
  TOKEN="$(python -c 'import secrets; print(secrets.token_urlsafe(24))')"
  sed -i "s|^CHUNAI_WEB_TOKEN=.*|CHUNAI_WEB_TOKEN=${TOKEN}|" .env
  echo "Berkas .env dibuat; token Web dibuat otomatis."
else
  echo "Berkas .env sudah ada; tidak diubah."
fi
chmod 600 .env
chmod +x scripts/*.sh

say "Pemeriksaan prasyarat"
chunai doctor || true

cat <<'MSG'

SELESAI. Langkah berikutnya:
  1) Login Claude   :  source .venv/bin/activate && chunai auth   (tempel token ke .env: nano .env)
  2) Telegram       :  chunai setup-telegram   (opsional; token dan ID tersimpan otomatis)
  3) Cek ulang      :  chunai doctor --live
  4) Jalankan       :  ./scripts/run.sh      (Web: http://localhost:8787)
MSG
