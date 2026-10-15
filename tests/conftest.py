import pytest

from chunai.approval import ApprovalRequest


class FakeAgent:
    """Pengganti ChunAI untuk menguji antarmuka tanpa LLM."""
    last_prompts: list[str] = []

    def __init__(self, reviewer, workdir):
        self.reviewer, self.workdir = reviewer, workdir

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
