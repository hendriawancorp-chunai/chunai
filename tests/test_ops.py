import asyncio
import os
import time

from chunai import resources
from chunai.doctor import Check, render, run_checks
from chunai.envfile import load_env, parse_env


def test_parse_env_formats():
    t = '''# komentar
A=1
export B="dua kata"
C='x#y'
D=nilai  # catatan
E=
bad line
F=a=b
'''
    d = parse_env(t)
    assert d == {"A": "1", "B": "dua kata", "C": "x#y", "D": "nilai", "E": "", "F": "a=b"}


def test_load_env_does_not_override_existing(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("CHUNAI_X1=dari_file\nCHUNAI_X2=dari_file\n")
    f.chmod(0o600)
    monkeypatch.setenv("CHUNAI_X1", "dari_lingkungan")
    monkeypatch.delenv("CHUNAI_X2", raising=False)
    assert load_env(f) == f
    assert os.environ["CHUNAI_X1"] == "dari_lingkungan" and os.environ["CHUNAI_X2"] == "dari_file"
    monkeypatch.delenv("CHUNAI_X2")


def test_load_env_warns_on_open_permissions(tmp_path, capsys):
    f = tmp_path / ".env"
    f.write_text("CHUNAI_X3=1\n")
    f.chmod(0o644)
    load_env(f)
    assert "chmod 600" in capsys.readouterr().err
    os.environ.pop("CHUNAI_X3", None)


def test_doctor_never_prints_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-RAHASIA")
    monkeypatch.setenv("CHUNAI_TELEGRAM_TOKEN", "123:TOKENRAHASIA")
    monkeypatch.setenv("CHUNAI_WEB_TOKEN", "WEBRAHASIA")
    text, _ = render(run_checks())
    assert "RAHASIA" not in text and "Otentikasi Claude" in text


def test_doctor_render_marks_critical_failures():
    text, ok = render([Check("a", True), Check("b", False, "perbaiki", critical=True), Check("c", False, critical=False)])
    assert not ok and "❌ b - perbaiki" in text and "⚠️ c" in text


async def test_heavy_jobs_run_one_at_a_time(monkeypatch):
    monkeypatch.setenv("CHUNAI_HEAVY_SLOTS", "1")
    running, peak = 0, 0

    def work():
        nonlocal running, peak
        running += 1; peak = max(peak, running)
        time.sleep(0.15)
        running -= 1
        return "ok"

    res = await asyncio.gather(*(resources.run_heavy(work) for _ in range(4)))
    assert res == ["ok"] * 4 and peak == 1


async def test_heavy_slots_configurable_and_loop_stays_responsive(monkeypatch):
    monkeypatch.setenv("CHUNAI_HEAVY_SLOTS", "2")
    resources._sems.clear()
    running, peak = 0, 0

    def work():
        nonlocal running, peak
        running += 1; peak = max(peak, running)
        time.sleep(0.2)
        running -= 1

    ticks = 0

    async def ticker():
        nonlocal ticks
        for _ in range(8):
            await asyncio.sleep(0.05); ticks += 1

    await asyncio.gather(ticker(), *(resources.run_heavy(work) for _ in range(4)))
    assert peak == 2 and ticks == 8          # loop tidak terblokir selama pekerjaan berat


def test_sandbox_module_safe_without_resource_module(monkeypatch):
    from chunai import sandbox
    monkeypatch.setattr(sandbox, "resource", None)
    assert sandbox.isolation_available() is False
    r = sandbox.run_python("print(1)", __import__("pathlib").Path("/tmp/x_sb"))
    assert not r.ok and "tidak tersedia" in r.stderr


def test_token_shape_never_reveals_secret():
    from chunai.doctor import token_shape
    good = "sk-ant-oat01-" + "A" * 90
    s = token_shape(good)
    assert "sk-ant-oat" in s and "panjang 103" in s and "AAAA" not in s and "peringatan" not in s.lower()
    assert "spasi" in token_shape("sk-ant-oat01-" + "A" * 40 + " " + "B" * 40)
    assert "kutip" in token_shape('"sk-ant-oat01-' + "A" * 90 + '"')
    assert "pendek" in token_shape("sk-ant-oat01-abc")
    assert "awalan tidak dikenal" in token_shape("bukan-token-claude" * 6)


def test_explain_error_hints():
    from chunai.doctor import explain_error
    assert "chunai auth" in explain_error("Invalid API key · Please run /login")
    assert "chunai auth" in explain_error("", 401)
    assert "kredit" in explain_error("Credit balance is too low")
    assert "batas pemakaian" in explain_error("Claude usage limit reached")
    assert "sibuk" in explain_error("", 529)


async def test_live_check_reports_real_reason(monkeypatch):
    import claude_agent_sdk
    from claude_agent_sdk import ResultMessage

    from chunai import doctor

    async def fake_query(**kw):
        yield ResultMessage(subtype="error", duration_ms=1, duration_api_ms=1, is_error=True, num_turns=0, session_id="x",
                            result="Invalid API key · Please run /login", api_error_status=401)
    monkeypatch.setattr(claude_agent_sdk, "query", fake_query)
    c = await doctor.live_auth_check(timeout=5)
    assert not c.ok and "Invalid API key" in c.detail and "chunai auth" in c.detail and "HTTP 401" in c.detail


async def test_live_check_times_out_instead_of_hanging(monkeypatch):
    import asyncio

    import claude_agent_sdk

    from chunai import doctor

    async def hang(**kw):
        await asyncio.sleep(30)
        yield None
    monkeypatch.setattr(claude_agent_sdk, "query", hang)
    c = await doctor.live_auth_check(timeout=0.3)
    assert not c.ok and "tidak ada respons" in c.detail


async def test_live_check_success(monkeypatch):
    import claude_agent_sdk
    from claude_agent_sdk import ResultMessage

    from chunai import doctor

    async def ok_query(**kw):
        yield ResultMessage(subtype="success", duration_ms=1, duration_api_ms=1, is_error=False, num_turns=1, session_id="x", result="siap")
    monkeypatch.setattr(claude_agent_sdk, "query", ok_query)
    assert (await doctor.live_auth_check(timeout=5)).ok
