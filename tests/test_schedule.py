import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from chunai import schedule as S
from chunai.approval import ApprovalResult
from chunai.interfaces.core import SessionManager
from chunai.interfaces.scheduler import Scheduler

WIB = ZoneInfo("Asia/Jakarta")


def at(y, m, d, h=0, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=WIB)


def test_next_run_variants():
    mon = S.normalize_spec({"tipe": "mingguan", "waktu": "08.00", "hari": "Senin"})
    assert mon["hari"] == [0] and mon["waktu"] == "08:00"
    # Kamis 15 Okt 2026 -> Senin berikutnya 19 Okt
    assert S.next_run(mon, at(2026, 10, 15, 12)) == at(2026, 10, 19, 8)
    assert S.next_run(mon, at(2026, 10, 19, 7, 59)) == at(2026, 10, 19, 8)
    assert S.next_run(mon, at(2026, 10, 19, 8)) == at(2026, 10, 26, 8)        # strictly setelah
    daily = S.normalize_spec({"tipe": "harian", "waktu": "06:30"})
    assert S.next_run(daily, at(2026, 10, 15, 6, 30)) == at(2026, 10, 16, 6, 30)
    month = S.normalize_spec({"tipe": "bulanan", "waktu": "09:00", "tgl": 1})
    assert S.next_run(month, at(2026, 12, 20)) == at(2027, 1, 1, 9)
    once = S.normalize_spec({"tipe": "sekali", "waktu": "10:00", "tanggal": "2026-10-20"})
    assert S.next_run(once, at(2026, 10, 15)) == at(2026, 10, 20, 10)
    assert S.next_run(once, at(2026, 10, 21)) is None
    multi = S.normalize_spec({"tipe": "mingguan", "waktu": "07:00", "hari": "senin,kamis"})
    assert S.next_run(multi, at(2026, 10, 15, 8)) == at(2026, 10, 19, 7)


@pytest.mark.parametrize("args", [
    {"tipe": "tiap-menit", "waktu": "08:00"}, {"tipe": "harian", "waktu": "25:00"}, {"tipe": "harian", "waktu": "8"},
    {"tipe": "sekali", "waktu": "08:00"}, {"tipe": "sekali", "waktu": "08:00", "tanggal": "20-10-2026"},
    {"tipe": "mingguan", "waktu": "08:00"}, {"tipe": "mingguan", "waktu": "08:00", "hari": "harisenin"},
    {"tipe": "bulanan", "waktu": "08:00", "tgl": 31}, {"tipe": "bulanan", "waktu": "08:00"}])
def test_invalid_specs(args):
    with pytest.raises(S.ScheduleError):
        S.normalize_spec(args)


def test_store_add_remove_limits(tmp_path):
    f = tmp_path / "s.json"
    spec = S.normalize_spec({"tipe": "harian", "waktu": "08:00"})
    t = S.add(f, "Pagi", "pengingat", "Minum obat", spec, at(2026, 10, 15))
    assert S.load(f)[0]["id"] == t["id"] and "Pagi" in S.render_list(S.load(f))
    with pytest.raises(S.ScheduleError):
        S.add(f, "x", "ngawur", "isi", spec)
    with pytest.raises(S.ScheduleError):
        S.add(f, "x", "tugas", "  ", spec)
    once_past = S.normalize_spec({"tipe": "sekali", "waktu": "08:00", "tanggal": "2020-01-01"})
    with pytest.raises(S.ScheduleError, match="lewat"):
        S.add(f, "x", "pengingat", "isi", once_past, at(2026, 10, 15))
    for i in range(S.MAX_AGENT_TASKS):
        S.add(f, f"t{i}", "tugas", "ringkas", spec, at(2026, 10, 15))
    with pytest.raises(S.ScheduleError, match="penuh"):
        S.add(f, "lagi", "tugas", "ringkas", spec, at(2026, 10, 15))
    assert S.remove(f, t["id"]) and not S.remove(f, t["id"])


class Chan:
    def __init__(self):
        self.texts, self.files = [], []

    async def send_text(self, t): self.texts.append(t)
    async def send_file(self, p, c=""): self.files.append(p)


class FakeAgent:
    """Agen palsu: menulis satu file dan meminta aksi berizin (yang harus ditolak)."""
    def __init__(self, reviewer, workdir):
        self.reviewer, self.workdir, self.outbox = reviewer, Path(workdir), []

    async def __aenter__(self): return self
    async def __aexit__(self, *a): ...

    async def ask(self, prompt):
        assert "TUGAS TERJADWAL" in prompt
        r = await self.reviewer(type("R", (), {"tool": "mcp__chunai__kirim_form", "input": {}, "summary": ""})())
        assert isinstance(r, ApprovalResult) and not r.approved
        (self.workdir / "ringkasan.md").write_text("# Ringkasan")
        yield "Ringkasan selesai."


def make(tmp_path, clock, factory=FakeAgent):
    mgr = SessionManager(lambda r, w: None, base_dir=tmp_path / "sessions", daily_budget=0)
    ch = Chan()
    sched = Scheduler(mgr, channels=lambda: [ch], store=tmp_path / "s.json", factory=factory, now_fn=lambda: clock[0])
    return sched, ch


async def test_reminder_fires_once_and_advances(tmp_path):
    clock = [at(2026, 10, 19, 7, 0)]
    sched, ch = make(tmp_path, clock)
    S.add(sched.store, "Rapat", "pengingat", "Rapat jam 9", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}), clock[0])
    assert await sched.tick() == 0 and ch.texts == []
    clock[0] = at(2026, 10, 19, 8, 0, )
    assert await sched.tick() == 1
    assert "Rapat jam 9" in ch.texts[0] and "terlambat" not in ch.texts[0]
    assert await sched.tick() == 0                                   # tidak berulang pada menit yang sama
    assert S.load(sched.store)[0]["berikutnya"].startswith("2026-10-20T08:00")


async def test_late_reminder_notes_delay_and_old_is_skipped(tmp_path):
    clock = [at(2026, 10, 19, 7, 0)]
    sched, ch = make(tmp_path, clock)
    S.add(sched.store, "A", "pengingat", "isi A", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}), clock[0])
    clock[0] = at(2026, 10, 19, 10, 0)                                # komputer baru hidup 2 jam kemudian
    await sched.tick()
    assert "terlambat 120 menit" in ch.texts[0]
    S.add(sched.store, "B", "pengingat", "isi B", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}), clock[0])
    clock[0] = at(2026, 10, 25, 9, 0)                                 # mati berhari-hari
    await sched.tick()
    assert any("terlewat" in t and "dilewati" in t for t in ch.texts[1:])
    assert not any("isi B" in t for t in ch.texts)


async def test_one_time_task_removed_after_run(tmp_path):
    clock = [at(2026, 10, 19, 7, 0)]
    sched, ch = make(tmp_path, clock)
    S.add(sched.store, "Sekali", "pengingat", "halo", S.normalize_spec({"tipe": "sekali", "waktu": "08:00", "tanggal": "2026-10-19"}), clock[0])
    clock[0] = at(2026, 10, 19, 8, 1)
    await sched.tick()
    assert "halo" in ch.texts[0] and S.load(sched.store) == []


async def test_agent_task_runs_unattended_denies_actions_and_sends_file(tmp_path):
    clock = [at(2026, 10, 19, 7, 0)]
    sched, ch = make(tmp_path, clock)
    S.add(sched.store, "Ringkas", "tugas", "ringkas berita", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}), clock[0])
    clock[0] = at(2026, 10, 19, 8, 0)
    await sched.tick()
    msg = ch.texts[0]
    assert "Ringkasan selesai." in msg and "1 aksi butuh izin dan dilewati: kirim_form" in msg
    assert [f.name for f in ch.files] == ["ringkasan.md"]


async def test_budget_limit_blocks_agent_task(tmp_path):
    clock = [at(2026, 10, 19, 7, 0)]
    sched, ch = make(tmp_path, clock)
    sched.mgr.budget_message = lambda: "⛔ Batas pemakaian harian tercapai"
    S.add(sched.store, "Ringkas", "tugas", "x", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}), clock[0])
    clock[0] = at(2026, 10, 19, 8, 0)
    await sched.tick()
    assert "tidak dijalankan" in ch.texts[0] and ch.files == []


async def test_agent_failure_reported_not_raised(tmp_path):
    class Boom(FakeAgent):
        async def ask(self, prompt):
            raise RuntimeError("putus")
            yield ""
    clock = [at(2026, 10, 19, 7, 0)]
    sched, ch = make(tmp_path, clock, Boom)
    S.add(sched.store, "R", "tugas", "x", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}), clock[0])
    clock[0] = at(2026, 10, 19, 8, 0)
    assert await sched.tick() == 1
    assert "Tugas gagal: RuntimeError" in ch.texts[0]


async def test_no_channel_saves_result_to_workspace(tmp_path):
    clock = [at(2026, 10, 19, 7, 0)]
    mgr = SessionManager(lambda r, w: None, base_dir=tmp_path / "sessions", daily_budget=0)
    sched = Scheduler(mgr, channels=None, store=tmp_path / "s.json", factory=FakeAgent, now_fn=lambda: clock[0])
    S.add(sched.store, "R", "pengingat", "isi penting", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}), clock[0])
    clock[0] = at(2026, 10, 19, 8, 0)
    await sched.tick()
    saved = list((tmp_path / "sessions" / "jadwal" / "workspace" / "hasil").glob("*.txt"))
    assert saved and "isi penting" in saved[0].read_text()


def test_policy_for_schedule_tools():
    from chunai.policy import Decision, classify
    assert classify("mcp__chunai__daftar_jadwal") is Decision.AUTO
    assert classify("mcp__chunai__buat_jadwal", {}) is Decision.ASK
    assert classify("mcp__chunai__hapus_jadwal", {}) is Decision.ASK


async def test_telegram_jadwal_command(tmp_path, monkeypatch):
    import httpx
    from chunai.interfaces.telegram import TelegramBot
    monkeypatch.setenv("CHUNAI_SCHEDULE_FILE", str(tmp_path / "s.json"))
    S.add(tmp_path / "s.json", "Pagi", "pengingat", "halo", S.normalize_spec({"tipe": "harian", "waktu": "08:00"}))
    sent = []

    def handler(req):
        import json
        body = json.loads(req.content) if req.content else {}
        if req.url.path.endswith("sendMessage"):
            sent.append(body["text"])
        return httpx.Response(200, json={"ok": True, "result": {}})
    mgr = SessionManager(lambda r, w: None, base_dir=tmp_path / "sess", daily_budget=0)
    bot = TelegramBot("T", {5}, mgr, base_url="https://tg.test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    await bot.handle_update({"update_id": 1, "message": {"chat": {"id": 5, "type": "private"}, "from": {"id": 5}, "text": "/jadwal"}})
    assert any("Pagi" in t and "setiap hari pukul 08.00" in t for t in sent)
