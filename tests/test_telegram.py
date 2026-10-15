import asyncio
import json

import httpx
import pytest

from chunai.interfaces.core import SessionManager
from chunai.interfaces.telegram import TelegramBot, split_text
from conftest import FakeAgent

OWNER, STRANGER = 111, 999


class FakeTG:
    """Telegram Bot API palsu."""
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.files = {"docs/data.csv": b"a,b\n1,2\n"}

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/file/bot" in path:
            return httpx.Response(200, content=self.files[path.split("/file/bot")[1].split("/", 1)[1]])
        method = path.rsplit("/", 1)[1]
        if request.headers.get("content-type", "").startswith("multipart"):
            body = {"_multipart": True}
        else:
            body = json.loads(request.content or b"{}")
        self.calls.append((method, body))
        if method == "getFile":
            return httpx.Response(200, json={"ok": True, "result": {"file_path": "docs/data.csv", "file_size": 8}})
        return httpx.Response(200, json={"ok": True, "result": []})

    def sent(self, method="sendMessage"):
        return [b for m, b in self.calls if m == method]

    def texts(self):
        return [b.get("text", "") for b in self.sent()]


@pytest.fixture
def setup(fake_factory, tmp_path):
    tg = FakeTG()
    client = httpx.AsyncClient(transport=httpx.MockTransport(tg.handler))
    mgr = SessionManager(fake_factory, tmp_path, approval_timeout=5)
    bot = TelegramBot("TOKEN", {OWNER}, mgr, base_url="https://tg.test", client=client)
    return bot, tg, mgr


def msg(uid, text=None, chat_type="private", **extra):
    return {"update_id": 1, "message": {"chat": {"id": uid, "type": chat_type}, "from": {"id": uid}, **({"text": text} if text else {}), **extra}}


def cb(uid, data):
    return {"update_id": 2, "callback_query": {"id": "cq1", "from": {"id": uid}, "data": data,
            "message": {"chat": {"id": uid}, "message_id": 7}}}


async def settle(mgr, uid=OWNER):
    s = mgr.get(f"tg{uid}")
    if s.task:
        await asyncio.wait_for(s.task, 5)


async def wait_for_approval(tg, mgr, uid=OWNER):
    for _ in range(100):
        if any("PERMINTAAN IZIN" in t for t in tg.texts()):
            return next(iter(mgr.get(f"tg{uid}").broker.pending))
        await asyncio.sleep(0.02)
    raise AssertionError("izin tidak diminta")


def test_split_text():
    assert split_text("a" * 9000, 3900)[0] == "a" * 3900 and len(split_text("a" * 9000, 3900)) == 3
    assert split_text("baris1\nbaris2") == ["baris1\nbaris2"]


def test_refuses_empty_allowlist(fake_factory, tmp_path):
    with pytest.raises(ValueError):
        TelegramBot("T", set(), SessionManager(fake_factory, tmp_path))


async def test_stranger_is_refused_and_agent_never_runs(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(STRANGER, "halo"))
    assert "Akses ditolak" in tg.texts()[0] and str(STRANGER) in tg.texts()[0]
    assert FakeAgent.last_prompts == [] and f"tg{STRANGER}" not in mgr.sessions


async def test_group_chat_ignored(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "halo", chat_type="group"))
    assert tg.calls == []


async def test_owner_gets_reply(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "halo dunia"))
    await settle(mgr)
    assert "echo: halo dunia" in tg.texts()


async def test_approval_approve_via_button(setup):
    bot, tg, mgr = setup
    shot = mgr.get(f"tg{OWNER}").workdir / "review" / "shot.png"
    shot.parent.mkdir(parents=True, exist_ok=True)
    shot.write_bytes(b"\x89PNG-shot")
    await bot.handle_update(msg(OWNER, "minta izin"))
    aid = await wait_for_approval(tg, mgr)
    prompt = next(b for b in tg.sent() if "PERMINTAAN IZIN" in b["text"])
    buttons = [x["callback_data"] for row in prompt["reply_markup"]["inline_keyboard"] for x in row]
    assert buttons == [f"ap:{aid}:a", f"ap:{aid}:d"]          # aksi final: TIDAK ada "selalu"
    assert tg.sent("sendPhoto")                                # screenshot dikirim untuk review
    await bot.handle_update(cb(OWNER, f"ap:{aid}:a"))
    await settle(mgr)
    assert "DISETUJUI" in tg.texts()


async def test_approval_deny(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "minta izin"))
    aid = await wait_for_approval(tg, mgr)
    await bot.handle_update(cb(OWNER, f"ap:{aid}:d"))
    await settle(mgr)
    assert any(t.startswith("DITOLAK") for t in tg.texts())


async def test_non_final_has_always_button(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "mau selalu"))
    aid = await wait_for_approval(tg, mgr)
    p = next(b for b in tg.sent() if "PERMINTAAN IZIN" in b["text"])
    assert any(x["callback_data"].endswith(":s") for row in p["reply_markup"]["inline_keyboard"] for x in row)
    await bot.handle_update(cb(OWNER, f"ap:{aid}:s"))
    await settle(mgr)
    assert "OK-SELALU" in tg.texts()


async def test_callback_from_stranger_does_not_approve(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "minta izin"))
    aid = await wait_for_approval(tg, mgr)
    await bot.handle_update(cb(STRANGER, f"ap:{aid}:a"))
    assert mgr.get(f"tg{OWNER}").broker.pending                 # masih menunggu pemilik
    assert any(b.get("show_alert") for b in tg.sent("answerCallbackQuery"))
    await bot.handle_update(cb(OWNER, f"ap:{aid}:d"))
    await settle(mgr)


async def test_unanswered_approval_times_out_as_denied(fake_factory, tmp_path):
    tg = FakeTG()
    mgr = SessionManager(fake_factory, tmp_path, approval_timeout=0.2)
    bot = TelegramBot("T", {OWNER}, mgr, base_url="https://tg.test", client=httpx.AsyncClient(transport=httpx.MockTransport(tg.handler)))
    await bot.handle_update(msg(OWNER, "minta izin"))
    await settle(mgr)
    assert any("batas waktu" in t for t in tg.texts())


async def test_generated_files_are_sent(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "tolong buatfile"))
    await settle(mgr)
    assert len(tg.sent("sendDocument")) == 1 and len(tg.sent("sendPhoto")) == 1


async def test_upload_then_prompt_mentions_file(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, None, document={"file_id": "F1", "file_name": "../../etc/data.csv"}))
    sess = mgr.get(f"tg{OWNER}")
    assert (sess.workdir / "masukan" / "data.csv").read_bytes() == b"a,b\n1,2\n"   # nama dibersihkan
    await bot.handle_update(msg(OWNER, "analisis"))
    await settle(mgr)
    assert "masukan/data.csv" in FakeAgent.last_prompts[-1]


async def test_busy_and_stop(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "tunggu lama"))
    await asyncio.sleep(0.05)
    await bot.handle_update(msg(OWNER, "tugas lain"))
    assert any("Masih memproses" in t for t in tg.texts())
    await bot.handle_update(msg(OWNER, "/stop"))
    await settle(mgr)
    assert any("Dihentikan" in t for t in tg.texts())


async def test_reset_and_id(setup):
    bot, tg, mgr = setup
    await bot.handle_update(msg(OWNER, "/id"))
    assert f"{OWNER}" in tg.texts()[-1]
    await bot.handle_update(msg(OWNER, "/reset"))
    assert "Sesi baru" in tg.texts()[-1]
