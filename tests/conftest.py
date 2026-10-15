import pytest

from chunai.approval import ApprovalRequest


class FakeAgent:
    """Pengganti ChunAI untuk menguji antarmuka tanpa LLM."""
    last_prompts: list[str] = []

    def __init__(self, reviewer, workdir):
        self.reviewer, self.workdir = reviewer, workdir
        self.outbox = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def interrupt(self):
        pass

    async def ask(self, prompt):
        FakeAgent.last_prompts.append(prompt)
        if "tunggu" in prompt:
            import asyncio
            await asyncio.sleep(30)
        if "izin" in prompt:
            res = await self.reviewer(ApprovalRequest(
                "mcp__chunai__kirim_form", {"index": 3},
                "Elemen [3] button \"Kirim\"\nScreenshot: review/shot.png"))
            yield "DISETUJUI" if res.approved else f"DITOLAK:{res.note}"
        elif "selalu" in prompt:
            res = await self.reviewer(ApprovalRequest("Write", {"file_path": "a"}, "tulis a"))
            yield "OK-SELALU" if res.approved else "NO"
        elif "buatdiakar" in prompt:                      # file di akar & subfolder bebas, plus file internal yang TIDAK boleh terkirim
            w = self.workdir
            (w / "bebas").mkdir(parents=True, exist_ok=True); (w / ".tmp").mkdir(exist_ok=True); (w / "masukan").mkdir(exist_ok=True)
            (w / "laporan.docx").write_bytes(b"PK-akar")
            (w / "catatan.txt").write_text("halo")
            (w / "bebas" / "data.xlsx").write_bytes(b"PK-xlsx")
            (w / "bebas" / "k.spec.json").write_text("{}")
            (w / ".tmp" / "x.png").write_bytes(b"png")
            (w / "masukan" / "unggahan.csv").write_text("a,b")
            yield "Selesai."
        elif "pilihfinal" in prompt:                      # agen membuat 2 versi tetapi memilih satu lewat kirim_file
            out = self.workdir / "output"; out.mkdir(parents=True, exist_ok=True)
            (out / "kajian.docx").write_bytes(b"v1"); (out / "kajian_2.docx").write_bytes(b"v2")
            self.outbox.append(out / "kajian_2.docx")
            yield "Final: kajian_2.docx"
        elif "kirimlama" in prompt:                       # file lama (tidak berubah) dikirim lewat outbox, sebagai kirim_file
            self.outbox.append(self.workdir / "arsip" / "kajian_lama.pdf")
            yield "Mengirim ulang kajian_lama.pdf."
        elif "buatfile" in prompt:
            out = self.workdir / "output"
            out.mkdir(parents=True, exist_ok=True)
            (out / "hasil.docx").write_bytes(b"PK-fake-docx")
            (out / "grafik.png").write_bytes(b"\x89PNG-fake")
            yield "File dibuat."
        else:
            yield f"echo: {prompt}"


@pytest.fixture
def fake_factory():
    FakeAgent.last_prompts = []
    return lambda reviewer, workdir: FakeAgent(reviewer, workdir)
