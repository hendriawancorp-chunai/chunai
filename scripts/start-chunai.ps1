# Menjalankan ChunAI (yang terpasang di WSL2 Ubuntu) dari Windows. Klik kanan > Run with PowerShell.
# Ganti $Distro bila nama distribusi WSL Anda berbeda (lihat: wsl -l -v).
$Distro = "Ubuntu"
Write-Host "Memulai ChunAI di WSL ($Distro). Tutup jendela ini untuk menghentikan."
wsl.exe -d $Distro -- bash -lc "cd ~/chunai && ./scripts/run.sh"
