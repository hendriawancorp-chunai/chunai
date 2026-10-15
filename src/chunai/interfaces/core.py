"""Inti antarmuka: sesi per pengguna, persetujuan dengan batas waktu, pengiriman file hasil.
Telegram dan Web hanya perlu mengimplementasikan Channel."""
from __future__ import annotations

import asyncio
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from ..approval import ApprovalRequest, ApprovalResult

SEND_DIRS = ("output", "grafik")          # hasil kerja yang otomatis dikirim ke pengguna
MAX_FILES_PER_TURN = 12
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
_IMG_IN_SUMMARY = re.compile(r"(review/[\w.\-]+\.png)")


class Channel(Protocol):
    async def send_text(self, text: str) -> None: ...
    async def send_file(self, path: Path, caption: str = "") -> None: ...
    async def request_approval(self, approval_id: str, req: ApprovalRequest, image: Path | None) -> None: ...


@dataclass
class PendingApproval:
    id: str
    req: ApprovalRequest
    future: asyncio.Future
    created: float = field(default_factory=time.time)


class ApprovalBroker:
    """Menahan permintaan izin sampai pengguna menjawab. Tidak dijawab = DITOLAK (aman)."""

    def __init__(self, timeout: float = 600):
        self.timeout = timeout
        self.pending: dict[str, PendingApproval] = {}

    async def ask(self, notify: Callable[[str], Awaitable[None]], req: ApprovalRequest) -> ApprovalResult:
        aid = secrets.token_urlsafe(6)
        fut = asyncio.get_running_loop().create_future()
        self.pending[aid] = PendingApproval(aid, req, fut)
        try:
            await notify(aid)
            return await asyncio.wait_for(fut, self.timeout)
        except asyncio.TimeoutError:
            return ApprovalResult(False, "Tidak ada jawaban dalam batas waktu; aksi dibatalkan.")
        finally:
            self.pending.pop(aid, None)

    def resolve(self, aid: str, decision: str, note: str = "") -> bool:
        p = self.pending.get(aid)
        if not p or p.future.done():
            return False
        if decision == "approve":
            p.future.set_result(ApprovalResult(True))
        elif decision == "always":
            p.future.set_result(ApprovalResult(True, "always"))
        else:
            p.future.set_result(ApprovalResult(False, note or "Ditolak oleh pengguna."))
        return True

    def deny_all(self, note: str = "Dibatalkan."):
        for p in list(self.pending.values()):
            if not p.future.done():
                p.future.set_result(ApprovalResult(False, note))


def snapshot(workdir: Path) -> dict[str, float]:
    snap: dict[str, float] = {}
    for d in SEND_DIRS:
        base = workdir / d
        if base.is_dir():
            for f in base.rglob("*"):
                if f.is_file() and f.suffix.lower() in {".docx", ".pptx", ".pdf", ".xlsx", ".png", ".jpg", ".md", ".csv", ".mp4"}:
                    snap[str(f)] = f.stat().st_mtime
    return snap


def changed_since(workdir: Path, before: dict[str, float]) -> list[Path]:
    now = snapshot(workdir)
    return sorted((Path(p) for p, m in now.items() if before.get(p) != m), key=lambda p: p.stat().st_mtime)


def pick_deliverables(changed: list[Path], final_text: str) -> list[Path]:
    """Kirim hanya file yang disebut agen di jawaban akhir (hasil final); bila tak ada yang disebut,
    kirim semua yang berubah. Versi perantara tidak membanjiri pengguna."""
    mentioned = [f for f in changed if f.name in final_text]
    return mentioned or changed


def safe_filename(name: str) -> str:
    name = re.sub(r"[^\w.\- ]", "_", Path(name).name).strip(" .") or "file"
    return name[:80]


def save_upload(workdir: Path, name: str, data: bytes) -> Path:
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError("File terlalu besar (maks 20 MB).")
    d = workdir / "masukan"
    d.mkdir(parents=True, exist_ok=True)
    path = d / safe_filename(name)
    i = 2
    while path.exists():
        path = d / f"{path.stem.rsplit('_v', 1)[0]}_v{i}{path.suffix}"
        i += 1
    path.write_bytes(data)
    return path


class Session:
    """Satu percakapan ChunAI untuk satu pengguna."""

    def __init__(self, key: str, workdir: Path, agent_factory, approval_timeout: float = 600):
        self.key, self.workdir = key, workdir
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._factory = agent_factory
        self.channel: Channel | None = None
        self.broker = ApprovalBroker(approval_timeout)
        self.agent = None
        self._cm = None
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.uploads: list[str] = []          # file yang diunggah pengguna, diberitahukan ke agen pada giliran berikutnya

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()

    async def _reviewer(self, req: ApprovalRequest) -> ApprovalResult:
        ch = self.channel
        if ch is None:
            return ApprovalResult(False, "Tidak ada antarmuka terhubung untuk meminta izin.")
        m = _IMG_IN_SUMMARY.search(req.summary)
        img = (self.workdir / m.group(1)) if m else None
        return await self.broker.ask(lambda aid: ch.request_approval(aid, req, img if img and img.exists() else None), req)

    async def ensure_agent(self):
        if self.agent is None:
            self._cm = self._factory(self._reviewer, self.workdir)
            self.agent = await self._cm.__aenter__()

    async def close(self):
        self.broker.deny_all("Sesi ditutup.")
        if self.task and not self.task.done():
            self.task.cancel()
        if self._cm is not None:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
        self.agent = self._cm = None

    async def stop(self):
        self.broker.deny_all("Dibatalkan pengguna.")
        if self.agent is not None and hasattr(self.agent, "interrupt"):
            try:
                await self.agent.interrupt()
            except Exception:
                pass
        if self.task and not self.task.done():
            self.task.cancel()

    async def turn(self, text: str):
        ch = self.channel
        assert ch is not None
        async with self.lock:
            try:
                await self.ensure_agent()
                before = snapshot(self.workdir)
                said: list[str] = []
                async for chunk in self.agent.ask(text):
                    if chunk.strip():
                        said.append(chunk)
                        await ch.send_text(chunk)
                for f in pick_deliverables(changed_since(self.workdir, before), " ".join(said))[:MAX_FILES_PER_TURN]:
                    await ch.send_file(f, f"Hasil: {f.name}")
            except asyncio.CancelledError:
                await ch.send_text("⏹ Dihentikan.")
            except Exception as e:  # jangan membocorkan detail internal berlebihan
                await ch.send_text(f"⚠ Terjadi kesalahan: {type(e).__name__}: {str(e)[:200]}")

    def start_turn(self, text: str) -> bool:
        if self.busy:
            return False
        if self.uploads:
            text = "File yang diunggah pengguna (di workspace): " + ", ".join(self.uploads) + "\n\n" + text
            self.uploads = []
        self.task = asyncio.create_task(self.turn(text))
        return True


class SessionManager:
    def __init__(self, agent_factory, base_dir: str | Path = "data/sessions", approval_timeout: float = 600):
        self.factory, self.base = agent_factory, Path(base_dir)
        self.timeout = approval_timeout
        self.sessions: dict[str, Session] = {}

    def get(self, key: str) -> Session:
        if key not in self.sessions:
            safe = re.sub(r"[^\w-]", "_", key)
            self.sessions[key] = Session(key, self.base / safe / "workspace", self.factory, self.timeout)
        return self.sessions[key]

    async def reset(self, key: str):
        s = self.sessions.pop(key, None)
        if s:
            await s.close()

    async def close_all(self):
        for k in list(self.sessions):
            await self.reset(k)


def default_agent_factory(max_budget_usd: float = 5.0):
    from ..agent import ChunAI
    from ..config import load_web_config

    def factory(reviewer, workdir):
        return ChunAI(reviewer, workdir=workdir, audit_path=Path(workdir).parent / "audit.jsonl",
                      web=load_web_config(), max_budget_usd=max_budget_usd)
    return factory
