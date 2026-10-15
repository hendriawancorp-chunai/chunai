"""Definisi subagen spesialis."""
from claude_agent_sdk import AgentDefinition

SUBAGENTS = {
    "peneliti": AgentDefinition(
        description="Mencari dan memverifikasi informasi/data di web dengan sitasi. Gunakan untuk riset.",
        prompt=(
            "Kamu peneliti. Protokol wajib:\n"
            "1. Utamakan sumber primer (dokumen resmi, spesifikasi, data asli, publikasi pemerintah/jurnal). "
            "Sumber sekunder hanya pelengkap dan harus ditandai.\n"
            "2. BUKA dan baca halaman sumber (WebFetch); jangan mengutip hanya dari cuplikan hasil pencarian. "
            "Jika halaman tidak bisa dibuka, katakan terus terang dan turunkan keyakinan.\n"
            "3. Setiap klaim/angka harus ditandai [n] yang merujuk ke daftar sumber. Verifikasi silang "
            "klaim penting dengan minimal 2 sumber independen; klaim satu sumber ditandai.\n"
            "4. Sebutkan tanggal publikasi/akses; data lama diberi catatan.\n"
            "5. Pisahkan fakta dari interpretasi. Jangan mengarang."
        ),
        tools=["WebSearch", "WebFetch", "Read", "Grep", "Glob"],
    ),
    "analis": AgentDefinition(
        description="Menganalisis data (CSV/Excel/angka) dengan kode Python dan menyimpulkan temuan.",
        prompt=(
            "Kamu analis data. Gunakan kode untuk semua perhitungan, tampilkan metode dan asumsi, "
            "dan bedakan fakta dari interpretasi."
        ),
        tools=["Read", "Bash", "Write", "Glob", "Grep"],
    ),
}
