# Menjalankan Chrome Windows dengan port debug (CDP) dan profil khusus untuk ChunAI.
# Klik kanan > Run with PowerShell. Tutup semua jendela Chrome lebih dulu.
$candidates = @(
  "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
  "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
  "$env:LocalAppData\Google\Chrome\Application\chrome.exe"
)
$chrome = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $chrome) { Write-Host "Chrome tidak ditemukan. Pasang Google Chrome dulu."; Read-Host "Enter untuk menutup"; exit 1 }
if (Get-Process chrome -ErrorAction SilentlyContinue) {
  Write-Host "Masih ada jendela Chrome yang terbuka. Tutup SEMUA (cek ikon baki sistem), lalu jalankan lagi."
  Read-Host "Enter untuk menutup"; exit 1
}
Start-Process $chrome -ArgumentList "--remote-debugging-port=9222", "--user-data-dir=C:\chunai-chrome"
Write-Host "Chrome khusus ChunAI dijalankan (port 9222, profil C:\chunai-chrome)."
Write-Host "Login manual ke situs yang dibutuhkan di jendela itu. Jangan tutup selama ChunAI bekerja."
