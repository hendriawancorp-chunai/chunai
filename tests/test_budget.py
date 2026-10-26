import asyncio
import pytest
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


def test_old_cumulative_costs_become_per_turn(tmp_path):
    today = date.today().isoformat()
    # catatan lama: total berjalan sesi (0.1, 0.3, 0.6) lalu sesi baru (0.2)
    write_audit(tmp_path, "web", [{"ts": f"{today}T0{i}:00:00+07:00", "event": "turn_done", "cost_usd": c}
                                  for i, c in enumerate([0.1, 0.3, 0.6, 0.2], 1)])
    assert day_cost(tmp_path, date.fromisoformat(today)) == 0.8       # 0.1+0.2+0.3+0.2, bukan 1.2


def test_new_records_store_delta_and_session_total(tmp_path):
    today = date.today().isoformat()
    write_audit(tmp_path, "web", [
        {"ts": f"{today}T01:00:00+07:00", "event": "turn_done", "cost_usd": 0.1, "session_total": 0.1},
        {"ts": f"{today}T02:00:00+07:00", "event": "turn_done", "cost_usd": 0.2, "session_total": 0.3}])
    assert day_cost(tmp_path, date.fromisoformat(today)) == 0.3



def _spend(tmp_path, amount):
    today = timeutil.now().date().isoformat()
    write_audit(tmp_path, "tg1", [{"ts": f"{today}T09:00:00+07:00", "event": "turn_done", "cost_usd": amount, "session_total": amount}])


def test_warning_at_80_percent_once_then_block_then_lanjut(tmp_path, fake_factory):
    mgr = SessionManager(fake_factory, tmp_path, daily_budget=10)
    _spend(tmp_path, 8.5)
    assert "80%" in mgr.budget_warning()
    assert mgr.budget_warning() is None                          # hanya sekali per hari
    assert mgr.budget_message() is None                          # belum mencapai batas
    _spend(tmp_path, 11)
    assert "/lanjut" in mgr.budget_message()
    assert "dilonggarkan" in mgr.allow_today()
    assert mgr.budget_message() is None                          # setelah /lanjut tidak diblokir hari ini


def test_no_warning_below_80_or_unlimited(tmp_path, fake_factory):
    _spend(tmp_path, 5)
    assert SessionManager(fake_factory, tmp_path, daily_budget=10).budget_warning() is None
    assert SessionManager(fake_factory, tmp_path, daily_budget=0).budget_warning() is None


def test_session_limit_env(monkeypatch):
    from chunai.usage import session_limit
    assert session_limit() == 5.0
    monkeypatch.setenv("CHUNAI_SESSION_BUDGET_USD", "0")
    assert session_limit() is None
    monkeypatch.setenv("CHUNAI_SESSION_BUDGET_USD", "12.5")
    assert session_limit() == 12.5


def test_session_continue_command(tmp_path, fake_factory):
    mgr = SessionManager(fake_factory, tmp_path, daily_budget=10)
    assert "dilonggarkan" in mgr.get("web").continue_command()


def test_apply_auth_mode_subscription_ignores_api_key():
    from chunai.envfile import apply_auth_mode
    env = {"CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-x", "ANTHROPIC_API_KEY": "sk-ant-api-y", "CHUNAI_API_KEY": "sk-ant-api-y"}
    assert apply_auth_mode(env) == "langganan"
    assert "ANTHROPIC_API_KEY" not in env and env["CLAUDE_CODE_OAUTH_TOKEN"]
    only_key = {"ANTHROPIC_API_KEY": "sk-ant-api-y"}
    assert apply_auth_mode(only_key) == "langganan" and only_key["ANTHROPIC_API_KEY"]   # tanpa token langganan: jangan dibuang


def test_apply_auth_mode_api_uses_spare_key_and_drops_oauth():
    from chunai.envfile import apply_auth_mode
    env = {"CHUNAI_AUTH": "api", "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-x", "CHUNAI_API_KEY": "sk-ant-api-z"}
    assert apply_auth_mode(env) == "api"
    assert env["ANTHROPIC_API_KEY"] == "sk-ant-api-z" and "CLAUDE_CODE_OAUTH_TOKEN" not in env
    assert apply_auth_mode({"CHUNAI_AUTH": "api"}) == "api-tanpa-kunci"


def test_cli_auth_key_saves_without_printing(tmp_path, monkeypatch, capsys):
    import getpass

    from chunai import cli
    env = tmp_path / ".env"
    monkeypatch.setenv("CHUNAI_ENV_FILE", str(env))
    secret = "sk-ant-api03-" + "a" * 50
    monkeypatch.setattr(getpass, "getpass", lambda *_: secret)
    with pytest.raises(SystemExit) as e:
        cli.run_auth_key()
    assert e.value.code == 0
    out = capsys.readouterr().out
    assert secret not in out and "CHUNAI_API_KEY=" + secret in env.read_text()
    monkeypatch.setattr(getpass, "getpass", lambda *_: "sk-ant-oat01-" + "b" * 50)
    with pytest.raises(SystemExit) as e2:
        cli.run_auth_key()
    assert "token langganan" in str(e2.value)


def test_cli_mode_requires_key(tmp_path, monkeypatch):
    from chunai import cli
    monkeypatch.setenv("CHUNAI_ENV_FILE", str(tmp_path / ".env"))
    monkeypatch.delenv("CHUNAI_API_KEY", raising=False); monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("sys.argv", ["chunai", "mode", "api"])
    with pytest.raises(SystemExit) as e:
        cli.run_mode()
    assert "auth-key" in str(e.value)


def test_explain_error_mentions_both_paths():
    from chunai.doctor import explain_error
    assert "auth-key" in explain_error("unauthorized", 401)
    assert "kuota" in explain_error("usage limit reached", 429)


@pytest.mark.asyncio
@pytest.mark.parametrize("subtype,status,expect", [("error_max_budget_usd", None, "CHUNAI_SESSION_BUDGET_USD"), ("error_status", 429, "kuota")])
async def test_ask_turns_claude_errors_into_indonesian_hints(subtype, status, expect, tmp_path):
    from claude_agent_sdk import ResultMessage

    from chunai.agent import ChunAI

    class FakeClient:
        async def query(self, *_): ...
        async def receive_response(self):
            yield ResultMessage(subtype=subtype, duration_ms=1, duration_api_ms=1, is_error=True, num_turns=1, session_id="s",
                                total_cost_usd=0.0, result="usage limit reached", api_error_status=status)

    a = ChunAI.__new__(ChunAI)
    a._client, a.model, a._cost_total = FakeClient(), None, 0.0
    a.audit = type("A", (), {"record": lambda *x, **k: None})()
    out = "".join([c async for c in a.ask("halo")])
    assert expect in out and "⚠" in out
