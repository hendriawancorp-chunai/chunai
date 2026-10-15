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
