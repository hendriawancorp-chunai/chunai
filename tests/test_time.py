import json
from datetime import datetime
from zoneinfo import ZoneInfo

from chunai import timeutil
from chunai.audit import AuditLog


def test_describe_wib():
    dt = datetime(2026, 10, 15, 12, 9, tzinfo=ZoneInfo("Asia/Jakarta"))
    assert timeutil.describe(dt) == "Kamis, 15 Oktober 2026, pukul 12.09 WIB (UTC+7)"


def test_describe_wita_and_other(monkeypatch):
    assert "WITA (UTC+8)" in timeutil.describe(datetime(2026, 1, 5, 8, 0, tzinfo=ZoneInfo("Asia/Makassar")))
    assert "UTC+9" in timeutil.describe(datetime(2026, 1, 5, 8, 0, tzinfo=ZoneInfo("Asia/Tokyo")))


def test_env_timezone_override(monkeypatch):
    monkeypatch.setenv("CHUNAI_TZ", "Asia/Makassar")
    assert timeutil.now().utcoffset().total_seconds() == 8 * 3600
    monkeypatch.setenv("CHUNAI_TZ", "Bukan/Zona")          # tidak valid -> aman ke WIB
    assert timeutil.now().utcoffset().total_seconds() == 7 * 3600


def test_audit_timestamp_uses_user_timezone(tmp_path):
    a = AuditLog(tmp_path / "a.jsonl")
    a.record("x")
    assert json.loads((tmp_path / "a.jsonl").read_text())["ts"].endswith("+07:00")
