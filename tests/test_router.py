import asyncio

import pytest

from chunai import router
from chunai.interfaces.core import SessionManager
from conftest import FakeAgent


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("CHUNAI_MODEL", "CHUNAI_MODEL_AUTO", "CHUNAI_MODEL_RINGAN", "CHUNAI_MODEL_SEDANG", "CHUNAI_MODEL_BERAT"):
        monkeypatch.delenv(k, raising=False)


@pytest.mark.parametrize("text,tier", [
    ("halo", "ringan"),
    ("apakah kamu bisa membuat aplikasi melalui chat ini", "ringan"),
    ("siapa presiden pertama indonesia?", "ringan"),
    ("tolong isikan form survei budaya keselamatan ini", "berat"),
    ("buka https://contoh.id dan cari harga", "berat"),
    ("buat draf posting linkedin tentang K3", "berat"),
    ("ringkas pdf ini", "sedang"),
    ("analisis saham TLKM", "sedang"),
    ("x " * 100, "sedang"),
])
def test_classify(text, tier):
    assert router.classify(text)[0] == tier


def test_upload_forces_at_least_medium():
    assert router.classify("tolong lihat", has_upload=True)[0] == "sedang"


def test_short_followup_inherits_recent_tier_only():
    assert router.classify("lanjutkan", prev=("berat", 1000.0), now=1100.0)[0] == "berat"
    assert router.classify("lanjutkan", prev=("berat", 1000.0), now=1000.0 + 3600)[0] == "ringan"


def test_prefix_and_manual_override():
    assert router.split_prefix("!cepat apa kabar") == ("ringan", "apa kabar")
    assert router.pick("!teliti halo", None)[:2] == ("claude-opus-5-5", "berat")
    assert router.pick("isikan form survei", "ringan")[1] == "ringan"          # pilihan /model menang atas deteksi
    assert router.pick("halo", "claude-sonnet-5-5")[0] == "claude-sonnet-5-5"


def test_fixed_model_and_auto_off(monkeypatch):
    monkeypatch.setenv("CHUNAI_MODEL", "claude-opus-5-5")
    assert router.pick("halo", None)[0] == "claude-opus-5-5"
    monkeypatch.delenv("CHUNAI_MODEL")
    monkeypatch.setenv("CHUNAI_MODEL_AUTO", "off")
    assert router.pick("halo", None)[0] is None


def test_env_overrides_tier_model(monkeypatch):
    monkeypatch.setenv("CHUNAI_MODEL_RINGAN", "claude-haiku-9")
    assert router.pick("halo", None)[0] == "claude-haiku-9"


def test_scheduled_model_cheap_and_capped():
    assert router.scheduled_model("ingatkan minum obat") == "claude-haiku-5-5"
    assert router.scheduled_model("periksa watchlist saham") == "claude-sonnet-5-5"
    assert router.scheduled_model("isikan form survei") == "claude-haiku-5-5"     # aksi web dilewati tanpa pengawasan


def test_parse_choice():
    assert router.parse_choice("Teliti") == "berat" and router.parse_choice("otomatis") == "otomatis"
    assert router.parse_choice("claude-sonnet-5-5") == "claude-sonnet-5-5"
    assert router.parse_choice("rm -rf /") is None


class Chan:
    def __init__(self):
        self.out = []
    async def send_text(self, t): self.out.append(t)
    async def send_file(self, *a, **k): pass
    async def request_approval(self, *a, **k): pass


@pytest.mark.asyncio
async def test_session_passes_chosen_model_and_commands(tmp_path):
    models = []

    class Spy(FakeAgent):
        async def ask(self, prompt, model=None):
            models.append((model, prompt))
            async for c in super().ask(prompt, model):
                yield c
    mgr = SessionManager(lambda r, w: Spy(r, w), tmp_path, approval_timeout=5)
    s = mgr.get("web")
    s.channel = Chan()
    for text in ("halo", "tolong isikan form survei", "ya", "!cepat berapa 2+2"):
        assert s.start_turn(text)
        await s.task
    assert [m for m, _ in models] == ["claude-haiku-5-5", "claude-opus-5-5", "claude-opus-5-5", "claude-haiku-5-5"]
    assert models[3][1] == "berapa 2+2"                                      # awalan tidak ikut dikirim ke agen
    assert "otomatis" in s.model_command("")
    assert "berat" in s.model_command("teliti")
    s.start_turn("halo"); await s.task
    assert models[-1][0] == "claude-opus-5-5"
    assert "tidak dikenal" in s.model_command("ngawur")
    s.model_command("otomatis")
