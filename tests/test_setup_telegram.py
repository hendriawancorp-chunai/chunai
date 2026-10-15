import json

import httpx

from chunai import setup_telegram as S

TOKEN = "123456789:" + "AbC_-" * 8
OWNER = {"id": 192674928, "first_name": "Budi", "username": "budi", "is_bot": False}


class FakeAPI:
    def __init__(self, updates=None, webhook="", bad_token=False):
        self.updates, self.webhook, self.bad = list(updates or []), webhook, bad_token
        self.calls = []

    def handler(self, req: httpx.Request):
        method = req.url.path.rsplit("/", 1)[1]
        body = json.loads(req.content or b"{}")
        self.calls.append((method, body))
        if self.bad:
            return httpx.Response(401, json={"ok": False, "description": "Unauthorized"})
        if method == "getMe":
            return httpx.Response(200, json={"ok": True, "result": {"id": 1, "username": "chunai_bot"}})
        if method == "getWebhookInfo":
            return httpx.Response(200, json={"ok": True, "result": {"url": self.webhook}})
        if method == "getUpdates":
            out, self.updates = self.updates, []
            return httpx.Response(200, json={"ok": True, "result": out})
        return httpx.Response(200, json={"ok": True, "result": True})

    def client(self):
        return httpx.Client(transport=httpx.MockTransport(self.handler))


def msg(uid_from, chat_type="private", uid=1, is_bot=False):
    return {"update_id": uid, "message": {"chat": {"id": 5, "type": chat_type}, "from": {**uid_from, "is_bot": is_bot}, "text": "halo"}}


def run(api, token=TOKEN, yes=True, saved=None):
    out, saved = [], saved if saved is not None else {}
    ok = S.run_setup(lambda p: token, lambda p: yes, out.append, api.client(), saved.__setitem__, base="https://t.test", wait_seconds=2)
    return ok, "\n".join(out), saved


def test_token_format():
    assert S.valid_token_format(TOKEN)
    assert not S.valid_token_format("bukan token") and not S.valid_token_format("123:abc") and not S.valid_token_format("")
    assert not S.valid_token_format(TOKEN + "\nbaris2")


def test_happy_path_detects_owner_and_saves_both(monkeypatch):
    api = FakeAPI(updates=[msg(OWNER)])
    ok, text, saved = run(api)
    assert ok and saved == {"CHUNAI_TELEGRAM_TOKEN": TOKEN, "CHUNAI_TELEGRAM_USERS": "192674928"}
    assert "@chunai_bot" in text and "Budi (@budi)" in text and TOKEN not in text          # token tidak pernah dicetak
    methods = [m for m, _ in api.calls]
    assert "sendMessage" in methods                                                          # konfirmasi dikirim ke pemilik


def test_owner_confirmation_declined_saves_nothing():
    ok, text, saved = run(FakeAPI(updates=[msg(OWNER)]), yes=False)
    assert not ok and saved == {} and "Dibatalkan" in text


def test_groups_and_bots_are_ignored():
    api = FakeAPI(updates=[msg({"id": 7, "first_name": "Grup"}, chat_type="group"), msg({"id": 8, "first_name": "Bot"}, is_bot=True, uid=2)])
    ok, text, saved = run(api)
    assert not ok and saved == {} and "Tidak ada pesan masuk" in text


def test_bad_token_gives_clear_message_without_leaking():
    ok, text, saved = run(FakeAPI(bad_token=True))
    assert not ok and "Unauthorized" in text and TOKEN not in text and saved == {}


def test_bad_format_is_rejected_before_any_network_call():
    api = FakeAPI()
    ok, text, _ = run(api, token="salah")
    assert not ok and api.calls == [] and "tidak sesuai" in text


def test_stale_webhook_is_removed_without_dropping_updates():
    api = FakeAPI(updates=[msg(OWNER)], webhook="https://lama.example/hook")
    run(api)
    dw = [b for m, b in api.calls if m == "deleteWebhook"]
    assert dw and dw[0]["drop_pending_updates"] is False
