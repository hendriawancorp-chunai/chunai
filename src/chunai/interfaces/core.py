"""Inti antarmuka: sesi per pengguna, persetujuan dengan batas waktu, pengiriman file hasil.
Telegram dan Web hanya perlu mengimplementasikan Channel."""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from .. import router
from ..approval import ApprovalRequest, ApprovalResult
from ..timeutil import now
from ..usage import day_cost, daily_limit

log = logging.getLogger(__name__)

# Folder internal yang TIDAK pernah dikirim otomatis (unggahan pengguna, tangkapan layar review, pratinjau, sementara)
SKIP_DIRS = {".tmp", ".mpl", "masukan", "review", "pratinjau", "frames", "__pycache__", "node_modules"}
SEND_SUFFIXES = {".docx", ".pptx", ".pdf", ".xlsx", ".xls", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".webp",
                 ".md", ".txt", ".mp4", ".zip", ".json", ".html"}
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


def is_deliverable(workdir: Path, f: Path) -> bool:
    try:
        rel = f.relative_to(workdir)
    except ValueError:
        return False
    if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
        return False
    return f.is_file() and f.suffix.lower() in SEND_SUFFIXES and not f.name.endswith(".spec.json")


def snapshot(workdir: Path) -> dict[str, float]:
    """Semua file hasil kerja di workspace (rekursif), kecuali folder internal."""
    snap: dict[str, float] = {}
    if workdir.is_dir():
        for f in workdir.rglob("*"):
            if is_deliverable(workdir, f):
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


def drain_outbox(agent, workdir: Path) -> list[Path]:
    """Ambil (dan kosongkan) daftar file yang diminta agen untuk dikirim; hanya file di dalam workspace."""
    box = getattr(agent, "outbox", None)
    out: list[Path] = []
    if not box:
        return out
    base = workdir.resolve()
    for p in list(box):
        try:
            rp = Path(p).resolve()
            if base in rp.parents and rp.is_file() and rp not in out:
                out.append(rp)
        except OSError:
            pass
    box.clear()
    return out


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

    def __init__(self, key: str, workdir: Path, agent_factory, approval_timeout: float = 600, budget_guard=None):
        self.key, self.workdir = key, workdir
        self.budget_guard = budget_guard                  # callable -> str|None (pesan bila batas harian tercapai)
        self.workdir.mkdir(parents=True, exist_ok=True)
        self._factory = agent_factory
        self.channel: Channel | None = None
        self.broker = ApprovalBroker(approval_timeout)
        self.agent = None
        self._cm = None
        self.task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.uploads: list[str] = []          # file yang diunggah pengguna, diberitahukan ke agen pada giliran berikutnya
        self.model_pref: str | None = None    # pilihan /model: None/"otomatis", tingkat (ringan/sedang/berat) atau id model
        self.last_tier: tuple[str, float] | None = None
        self.last_model: str | None = None

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

    async def _say(self, ch, text: str):
        """Kirim pesan tanpa menggagalkan pekerjaan agen bila jaringan chat sedang putus."""
        try:
            await ch.send_text(text)
        except Exception as e:
            log.warning("pesan tidak terkirim ke chat (%s)", type(e).__name__)

    def model_command(self, arg: str) -> str:
        """Perintah /model: tanpa argumen = tampilkan; otomatis | ringan | sedang | berat | id model claude-..."""
        arg = arg.strip()
        if router.fixed_model():
            return f"Model dikunci oleh CHUNAI_MODEL ({router.fixed_model()}). Hapus pengaturan itu di .env untuk pemilahan otomatis."
        if arg:
            v = router.parse_choice(arg)
            if v is None:
                return "Pilihan tidak dikenal. Gunakan: /model otomatis | ringan | sedang | berat (atau id model, mis. claude-sonnet-5-5)."
            self.model_pref = None if v == "otomatis" else v
        pref = self.model_pref
        mode = ("otomatis" if router.auto_enabled() else "bawaan (pemilahan mati)") if not pref else \
            f"{pref} ({router.label(router.model_for(pref))})" if pref in router.TIERS else pref
        tiers = ", ".join(f"{t}={router.label(router.model_for(t))}" for t in router.TIERS)
        last = f"\nModel giliran terakhir: {router.label(self.last_model)}" if self.last_model else ""
        return (f"Mode model: {mode}\nTingkat: {tiers}{last}\n"
                "Ubah: /model otomatis | ringan | sedang | berat. Satu perintah saja: awali dengan !cepat atau !teliti.")

    async def turn(self, text: str, choice: tuple | None = None):
        ch = self.channel
        assert ch is not None
        async with self.lock:
            try:
                await self.ensure_agent()
                before = snapshot(self.workdir)
                said: list[str] = []
                model, tier = (choice[0], choice[1]) if choice else (None, None)
                if tier:
                    self.last_tier = (tier, time.time())
                self.last_model = model or self.last_model
                kw = {"model": model} if model else {}
                async for chunk in self.agent.ask(text, **kw):
                    if chunk.strip():
                        said.append(chunk)
                        await self._say(ch, chunk)
                chosen = drain_outbox(self.agent, self.workdir)                # pilihan EKSPLISIT agen (kirim_file)
                files = chosen or pick_deliverables(changed_since(self.workdir, before), " ".join(said))
                for f in files[:MAX_FILES_PER_TURN]:
                    try:
                        await ch.send_file(f, f"Hasil: {f.name}")
                    except Exception as e:
                        await ch.send_text(f"⚠ Gagal mengirim {f.name}: {type(e).__name__}. File tetap tersimpan di workspace.")
                if len(files) > MAX_FILES_PER_TURN:
                    await ch.send_text(f"(+{len(files) - MAX_FILES_PER_TURN} file lain tersimpan di workspace)")
            except asyncio.CancelledError:
                await ch.send_text("⏹ Dihentikan.")
            except Exception as e:  # jangan membocorkan detail internal berlebihan
                await self._say(ch, f"⚠ Terjadi kesalahan: {type(e).__name__}: {str(e)[:200] or '(tanpa pesan; biasanya koneksi internet/DNS terputus)'}")

    async def _notify(self, msg: str):
        if self.channel is not None:
            await self.channel.send_text(msg)

    def start_turn(self, text: str) -> bool:
        if self.busy:
            return False
        if self.budget_guard:
            msg = self.budget_guard()
            if msg:
                self.task = asyncio.create_task(self._notify(msg))      # tidak menjalankan agen
                return True
        choice = router.pick(text, self.model_pref, has_upload=bool(self.uploads), prev=self.last_tier)
        text = choice[3]
        if self.uploads:
            text = "File yang diunggah pengguna (di workspace): " + ", ".join(self.uploads) + "\n\n" + text
            self.uploads = []
        self.task = asyncio.create_task(self.turn(text, choice))
        return True


class SessionManager:
    def __init__(self, agent_factory, base_dir: str | Path = "data/sessions", approval_timeout: float = 600,
                 daily_budget: float | None = None):
        self.factory, self.base = agent_factory, Path(base_dir)
        self.timeout = approval_timeout
        self.daily_budget = daily_limit() if daily_budget is None else daily_budget
        self.sessions: dict[str, Session] = {}

    def today_cost(self) -> float:
        return day_cost(self.base, now().date())

    def budget_message(self) -> str | None:
        lim = self.daily_budget
        if lim and lim > 0:
            used = self.today_cost()
            if used >= lim:
                return (f"⛔ Batas pemakaian harian tercapai (setara ${used:.2f} dari ${lim:.2f}). Tugas baru tidak dijalankan "
                        "sampai besok. Untuk menaikkan batas: ubah CHUNAI_DAILY_BUDGET_USD di .env lalu jalankan ulang ChunAI.")
        return None

    def get(self, key: str) -> Session:
        if key not in self.sessions:
            safe = re.sub(r"[^\w-]", "_", key)
            self.sessions[key] = Session(key, self.base / safe / "workspace", self.factory, self.timeout,
                                         budget_guard=self.budget_message)
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
                      web=load_web_config(), max_budget_usd=max_budget_usd,
                      model=os.environ.get("CHUNAI_MODEL") or None)
    return factory
