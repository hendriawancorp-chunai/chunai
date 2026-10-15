import asyncio
import json
import subprocess
from datetime import date, datetime
from pathlib import Path

from chunai import timeutil
from chunai.doctor import security_checks
from chunai.interfaces.core import SessionManager
from chunai.usage import day_cost, render_audit
from conftest import FakeAgent


def write_audit(base: Path, key: str, rows):
    d = base / key
    d.mkdir(parents=True, exist_ok=True)
    with (d / "audit.jsonl").open("a") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def test_day_cost_sums_only_today(tmp_path):
    today = timeutil.now().date().isoformat()
    write_audit(tmp_path, "tg1", [
        {"ts": f"{today}T09:00:00+07:00", "event": "turn_done", "cost_usd": 0.5},
        {"ts": f"{today}T10:00:00+07:00", "event": "turn_done", "cost_usd": 0.25},
        {"ts": "2020-01-01T10:00:00+07:00", "event": "turn_done", "cost_usd": 99},
        {"ts": f"{today}T10:00:00+07:00", "event": "user_prompt"}])
    write_audit(tmp_path, "web", [{"ts": f"{today}T11:00:00+07:00", "event": "turn_done", "cost_usd": 1.0}])
    assert day_cost(tmp_path, date.fromisoformat(today)) == 1.75


async def test_budget_exceeded_blocks_agent_and_tells_user(tmp_path, fake_factory):
    today = timeutil.now().date().isoformat()
    write_audit(tmp_path, "tg1", [{"ts": f"{today}T09:00:00+07:00", "event": "turn_done", "cost_usd": 3.0}])
    mgr = SessionManager(fake_factory, tmp_path, daily_budget=2.0)
    sess = mgr.get("tg1")
    sent = []

    class Ch:
        async def send_text(self, t): sent.append(t)
        async def send_file(self, *a): ...
        async def request_approval(self, *a): ...
    sess.channel = Ch()
    assert sess.start_turn("halo")
    await sess.task
    assert sent and "Batas pemakaian harian" in sent[0] and FakeAgent.last_prompts == []


async def test_under_budget_runs_normally(tmp_path, fake_factory):
    mgr = SessionManager(fake_factory, tmp_path, daily_budget=2.0)
    sess = mgr.get("tg1")
    got = []

    class Ch:
        async def send_text(self, t): got.append(t)
        async def send_file(self, *a): ...
        async def request_approval(self, *a): ...
    sess.channel = Ch()
    sess.start_turn("halo")
    await sess.task
    assert "echo: halo" in got


def test_budget_zero_means_unlimited(tmp_path, fake_factory):
    assert SessionManager(fake_factory, tmp_path, daily_budget=0).budget_message() is None


def test_render_audit_is_readable(tmp_path):
    write_audit(tmp_path, "tg1", [
        {"ts": "2026-10-15T12:00:00+07:00", "event": "user_prompt", "prompt": "buat kajian"},
        {"ts": "2026-10-15T12:00:01+07:00", "event": "auto_allowed", "tool": "WebSearch"},
        {"ts": "2026-10-15T12:00:02+07:00", "event": "approval_requested", "tool": "Write"},
        {"ts": "2026-10-15T12:00:09+07:00", "event": "approval_decision", "tool": "Write", "approved": False, "note": "jangan"},
        {"ts": "2026-10-15T12:00:30+07:00", "event": "tool_use", "tool": "mcp__chunai__kirim_file", "path": "output/a.docx"},
        {"ts": "2026-10-15T12:00:31+07:00", "event": "turn_done", "cost_usd": 0.0712}])
    out = render_audit(tmp_path, 10)
    assert "PERINTAH" in out and "DITOLAK Write jangan" in out and "KIRIM FILE output/a.docx" in out and "$0.071" in out
    assert "WebSearch" not in out                                  # izin otomatis tidak memenuhi tampilan


def test_security_checks_flag_open_env_and_weak_token(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("X=1\n"); env.chmod(0o644)
    monkeypatch.setenv("CHUNAI_ENV_FILE", str(env))
    monkeypatch.setenv("CHUNAI_WEB_TOKEN", "pendek")
    monkeypatch.setenv("CHUNAI_HOST", "0.0.0.0")
    monkeypatch.setenv("CHUNAI_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.delenv("CHUNAI_TELEGRAM_USERS", raising=False)
    bad = {c.name for c in security_checks() if not c.ok}
    assert {"Keamanan: izin .env", "Keamanan: kekuatan token Web", "Keamanan: alamat Web", "Keamanan: daftar pengguna Telegram"} <= bad
    env.chmod(0o600)
    assert "Keamanan: izin .env" not in {c.name for c in security_checks() if not c.ok}


def test_backup_script_excludes_secrets_and_rotates(tmp_path):
    repo = Path(__file__).parent.parent
    work = tmp_path / "w"
    (work / "scripts").mkdir(parents=True)
    (work / "scripts" / "backup.sh").write_text((repo / "scripts" / "backup.sh").read_text())
    (work / "data" / "sessions" / "tg1" / "workspace" / "output").mkdir(parents=True)
    (work / "data" / "sessions" / "tg1" / "workspace" / "output" / "k.docx").write_bytes(b"x")
    (work / "data" / "sessions" / "tg1" / "workspace" / ".tmp").mkdir()
    (work / "data" / "sessions" / "tg1" / "workspace" / ".tmp" / "t.png").write_bytes(b"x")
    (work / "data" / "browser_profile").mkdir()
    (work / "data" / "browser_profile" / "cookies").write_bytes(b"RAHASIA")
    (work / ".env").write_text("CLAUDE_CODE_OAUTH_TOKEN=RAHASIA\n")
    dest = tmp_path / "bk"
    r = subprocess.run(["bash", "scripts/backup.sh", str(dest)], cwd=work, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    arc = next(dest.glob("chunai-*.tar.gz"))
    names = subprocess.run(["tar", "-tzf", str(arc)], capture_output=True, text=True).stdout
    assert "k.docx" in names and "RAHASIA" not in names and "browser_profile" not in names and ".tmp" not in names and ".env" not in names
