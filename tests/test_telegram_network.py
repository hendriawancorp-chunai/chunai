import httpx
import pytest

from chunai.interfaces.core import Session
from chunai.interfaces.telegram import TelegramBot


class Mgr:
    pass


def bot_with(handler, retries=3):
    b = TelegramBot("T", {1}, Mgr(), base_url="https://tg.test", client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    b.connect_retries = retries
    return b


async def test_connect_error_is_retried_then_succeeds(monkeypatch):
    async def nosleep(_): ...
    monkeypatch.setattr("chunai.interfaces.telegram.asyncio.sleep", nosleep)
    calls = []

    def handler(req):
        calls.append(1)
        if len(calls) < 3:
            raise httpx.ConnectError("putus", request=req)
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})
    assert (await bot_with(handler).api("sendMessage", {"chat_id": 1, "text": "x"})) == {"message_id": 1}
    assert len(calls) == 3


async def test_persistent_connect_error_gives_clear_message(monkeypatch):
    async def nosleep(_): ...
    monkeypatch.setattr("chunai.interfaces.telegram.asyncio.sleep", nosleep)

    def handler(req):
        raise httpx.ConnectError("", request=req)
    with pytest.raises(RuntimeError, match="Tidak bisa terhubung ke Telegram.*internet/VPN/DNS"):
        await bot_with(handler).api("getMe")


async def test_read_timeout_is_not_retried():
    calls = []

    def handler(req):
        calls.append(1)
        raise httpx.ReadTimeout("lambat", request=req)
    with pytest.raises(httpx.ReadTimeout):
        await bot_with(handler).api("sendMessage", {"chat_id": 1, "text": "x"})
    assert len(calls) == 1                      # bisa saja sudah terkirim: jangan kirim ganda


async def test_failed_chat_send_does_not_crash_turn(tmp_path):
    class Ch:
        async def send_text(self, t): raise RuntimeError("putus")
    s = Session.__new__(Session)
    await s._say(Ch(), "halo")                  # tidak melempar
