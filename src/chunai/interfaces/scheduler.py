"""Penjadwal: menjalankan pengingat dan tugas terjadwal saat ChunAI hidup (komputer menyala).
Tugas agen berjalan TANPA pengawasan: aksi yang butuh izin otomatis DITOLAK dan dilaporkan (kartu izin tidak dikirim saat Anda tidak ada)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Awaitable, Callable

from .. import schedule as S
from ..approval import ApprovalRequest, ApprovalResult
from ..timeutil import describe, now
from .core import changed_since, drain_outbox, pick_deliverables, snapshot

log = logging.getLogger(__name__)
GRACE = timedelta(hours=24)          # lewat dari ini (komputer mati lama) -> dilewati, bukan dijalankan terlambat
TASK_TIMEOUT = 15 * 60

UNATTENDED = ("[TUGAS TERJADWAL, tanpa pengawasan: tidak ada pengguna yang bisa menyetujui izin. Kerjakan HANYA membaca/riset/analisis/"
              "penyusunan dokumen di workspace. Aksi yang butuh izin (klik, kirim form, situs baru, menulis di luar workspace) akan ditolak; "
              "jangan mencobanya berulang, cukup laporkan bahwa itu butuh izin. Hasil singkat dan langsung ke inti; sertakan sumber bila ada.]\n")


class Scheduler:
    def __init__(self, mgr, channels: Callable[[], list] | None = None, store: Path | None = None, factory=None,
                 now_fn: Callable[[], datetime] = now, tick: float = 30.0):
        self.mgr = mgr
        self.channels = channels or (lambda: [])
        self.store = Path(store) if store else S.default_path()
        self.now, self.tick_s = now_fn, tick
        if factory is None:
            from .core import default_agent_factory
            factory = default_agent_factory(max_budget_usd=1.0)
        self.factory = factory
        self.lock = asyncio.Lock()
        self._stop = False

    def stop(self):
        self._stop = True

    # ---------- pengiriman ----------
    async def _say(self, text: str):
        chans = self.channels()
        if not chans:
            d = self.mgr.base / "jadwal" / "workspace" / "hasil"
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{self.now():%Y%m%d_%H%M%S}.txt").write_text(text, encoding="utf-8")
            log.info("jadwal: tidak ada kanal Telegram; hasil disimpan di %s", d)
            return
        for ch in chans:
            try:
                await ch.send_text(text)
            except Exception as e:
                log.warning("jadwal: pesan tidak terkirim (%s)", type(e).__name__)

    async def _send_file(self, path: Path, caption: str):
        for ch in self.channels():
            try:
                await ch.send_file(path, caption)
            except Exception as e:
                log.warning("jadwal: file tidak terkirim (%s)", type(e).__name__)

    # ---------- eksekusi ----------
    async def tick(self) -> int:
        """Jalankan semua jadwal yang jatuh tempo. Mengembalikan jumlah yang diproses."""
        at = self.now()
        tasks = S.load(self.store)
        todo = S.due(tasks, at)
        if not todo:
            return 0
        by_id = {t["id"]: t for t in tasks}
        for t in todo:                                   # majukan jadwal SEBELUM menjalankan (paling banyak satu kali, aman bila macet)
            planned = S.parse_dt(t["berikutnya"])
            t["_planned"] = planned
            nxt = S.next_run(t["jadwal"], at)
            t["berikutnya"] = nxt.isoformat() if nxt else None
            t["terakhir"] = at.isoformat()
        S.save(self.store, [t for t in (self._clean(x) for x in tasks) if not (t["jadwal"]["tipe"] == "sekali" and t["berikutnya"] is None
                                                                                 and t["id"] in {d["id"] for d in todo})])
        async with self.lock:
            for t in todo:
                await self._run_one(t, at)
        return len(todo)

    @staticmethod
    def _clean(t: dict) -> dict:
        return {k: v for k, v in t.items() if not k.startswith("_")}

    async def _run_one(self, t: dict, at: datetime):
        planned: datetime = t["_planned"]
        late = at - planned
        title = f"⏰ {t['nama']}"
        if late > GRACE:
            await self._say(f"{title}\nJadwal {describe(planned)} terlewat karena ChunAI/komputer tidak aktif ({late.days} hari lalu); dilewati.")
            return
        note = f"\n(terlambat {int(late.total_seconds() // 60)} menit; komputer/ChunAI baru aktif)" if late > timedelta(minutes=5) else ""
        if t["jenis"] == "pengingat":
            await self._say(f"{title}\n{t['isi']}{note}")
            return
        await self._run_agent(t, title, note)

    async def _run_agent(self, t: dict, title: str, note: str):
        msg = self.mgr.budget_message()
        if msg:
            await self._say(f"{title}\nTugas tidak dijalankan.\n{msg}")
            return
        denied: list[str] = []

        async def reviewer(req: ApprovalRequest) -> ApprovalResult:
            denied.append(req.tool.replace("mcp__chunai__", ""))
            return ApprovalResult(False, "Tugas terjadwal berjalan tanpa pengawasan; aksi ini butuh izin Anda dan dilewati.")

        workdir = self.mgr.base / "jadwal" / "workspace"
        workdir.mkdir(parents=True, exist_ok=True)
        try:
            async with self.factory(reviewer, workdir) as agent:
                before = snapshot(workdir)
                said: list[str] = []

                async def go():
                    async for chunk in agent.ask(UNATTENDED + t["isi"]):
                        if chunk.strip():
                            said.append(chunk)
                await asyncio.wait_for(go(), TASK_TIMEOUT)
                files = drain_outbox(agent, workdir) or pick_deliverables(changed_since(workdir, before), " ".join(said))
            body = "\n".join(said).strip() or "(tidak ada keluaran)"
            tail = f"\n\n⚠ {len(denied)} aksi butuh izin dan dilewati: {', '.join(sorted(set(denied)))}." if denied else ""
            await self._say(f"{title}{note}\n\n{body}{tail}")
            for f in files[:5]:
                await self._send_file(f, f"Hasil: {f.name}")
        except asyncio.TimeoutError:
            await self._say(f"{title}\n⚠ Tugas dihentikan karena melebihi {TASK_TIMEOUT // 60} menit.")
        except Exception as e:
            log.exception("tugas terjadwal gagal")
            await self._say(f"{title}\n⚠ Tugas gagal: {type(e).__name__}: {str(e)[:200]}")

    async def run(self):
        log.info("Penjadwal aktif (%d jadwal tersimpan)", len(S.load(self.store)))
        while not self._stop:
            try:
                await self.tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("penjadwal: galat pada tick")
            await asyncio.sleep(self.tick_s)
