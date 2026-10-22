import time

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from chunai.interfaces.core import SessionManager
from chunai.interfaces.web import create_app

TOKEN = "t0ken-rahasia"


@pytest.fixture
def client(fake_factory, tmp_path):
    mgr = SessionManager(fake_factory, tmp_path, approval_timeout=5)
    with TestClient(create_app(mgr, TOKEN)) as c:
        yield c


def login(ws, token=TOKEN):
    ws.send_json({"type": "auth", "token": token})
    return ws.receive_json()


def collect_until(ws, stop_type="done"):
    out = []
    while True:
        m = ws.receive_json()
        out.append(m)
        if m["type"] == stop_type:
            return out


def test_index_and_health(client):
    r = client.get("/")
    assert r.status_code == 200 and "ChunAI" in r.text and "Content-Security-Policy" in r.headers
    assert client.get("/healthz").json() == {"ok": True}


def test_wrong_token_rejected(client):
    with client.websocket_connect("/ws") as ws:
        assert login(ws, "salah")["type"] == "error"
        with pytest.raises(WebSocketDisconnect):
            ws.receive_json()


def test_cross_origin_websocket_rejected(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws", headers={"origin": "https://evil.example"}) as ws:
            ws.receive_json()


def test_chat_roundtrip(client):
    with client.websocket_connect("/ws") as ws:
        assert login(ws)["type"] == "ready"
        ws.send_json({"type": "message", "text": "halo"})
        msgs = collect_until(ws)
        assert {"type": "text", "text": "echo: halo"} in msgs and msgs[-1]["type"] == "done"


def test_approval_roundtrip(client):
    with client.websocket_connect("/ws") as ws:
        login(ws)
        ws.send_json({"type": "message", "text": "minta izin"})
        while (m := ws.receive_json())["type"] != "approval":
            pass
        assert m["final"] is True and m["image"] is None      # tanpa file screenshot -> tanpa gambar
        ws.send_json({"type": "approval", "id": m["id"], "decision": "deny", "note": "jangan"})
        msgs = collect_until(ws)
        assert {"type": "text", "text": "DITOLAK:jangan"} in msgs


def test_files_signed_download(client):
    with client.websocket_connect("/ws") as ws:
        login(ws)
        ws.send_json({"type": "message", "text": "buatfile"})
        files = [m for m in collect_until(ws) if m["type"] == "file"]
        assert {f["name"] for f in files} == {"hasil.docx", "grafik.png"}
        url = next(f["url"] for f in files if f["name"] == "hasil.docx")
        r = client.get(url)
        assert r.status_code == 200 and r.content == b"PK-fake-docx"
        assert client.get(url[:-3] + "abc").status_code == 403                      # tanda tangan diubah
        assert client.get(url.replace("hasil.docx", "..%2F..%2Fx")).status_code in (403, 404)
        assert client.get("/files?p=output/hasil.docx&e=%d&s=x" % (time.time() + 99)).status_code == 403


def test_upload_requires_token_and_sanitizes(client):
    r = client.post("/upload", files={"file": ("a.csv", b"x")})
    assert r.status_code == 401
    r = client.post("/upload", files={"file": ("../../evil.csv", b"1,2")}, headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200 and r.json()["path"] == "masukan/evil.csv"


def test_only_mentioned_deliverables_are_sent():
    from pathlib import Path
    from chunai.interfaces.core import pick_deliverables
    ch = [Path("o/a.docx"), Path("o/a_2.docx"), Path("o/uji.pptx")]
    assert pick_deliverables(ch, "Hasil akhir: a_2.docx") == [Path("o/a_2.docx")]
    assert pick_deliverables(ch, "selesai") == ch


def test_deliverable_detection_covers_whole_workspace_but_skips_internal(tmp_path):
    from chunai.interfaces.core import changed_since, snapshot
    w = tmp_path
    before = snapshot(w)
    (w / "bebas").mkdir(); (w / ".tmp").mkdir(); (w / "masukan").mkdir(); (w / "review").mkdir()
    for rel in ("laporan.docx", "catatan.txt", "bebas/data.xlsx", "bebas/foto.JPEG", "a.spec.json",
                ".tmp/x.png", "masukan/in.csv", "review/shot.png", "kode.py"):
        (w / rel).write_bytes(b"x")
    names = {p.relative_to(w).as_posix() for p in changed_since(w, before)}
    assert names == {"laporan.docx", "catatan.txt", "bebas/data.xlsx", "bebas/foto.JPEG"}


def test_web_sends_files_created_anywhere_in_workspace(client):
    with client.websocket_connect("/ws") as ws:
        login(ws)
        ws.send_json({"type": "message", "text": "buatdiakar"})
        names = {m["name"] for m in collect_until(ws) if m["type"] == "file"}
        assert names == {"laporan.docx", "catatan.txt", "data.xlsx"}      # internal (.tmp, masukan, .spec.json) tidak ikut


def test_web_sends_existing_file_requested_via_kirim_file(client, tmp_path):
    with client.websocket_connect("/ws") as ws:
        login(ws)
        arsip = tmp_path / "web" / "workspace" / "arsip"
        arsip.mkdir(parents=True, exist_ok=True)
        (arsip / "kajian_lama.pdf").write_bytes(b"%PDF-lama")
        ws.send_json({"type": "message", "text": "kirimlama"})
        files = [m for m in collect_until(ws) if m["type"] == "file"]
        assert [f["name"] for f in files] == ["kajian_lama.pdf"]
        assert client.get(files[0]["url"]).content == b"%PDF-lama"


def test_outbox_rejects_paths_outside_workspace(tmp_path):
    from chunai.interfaces.core import drain_outbox
    class A: outbox = []
    (tmp_path / "ws").mkdir()
    (tmp_path / "ws" / "ok.pdf").write_bytes(b"x"); (tmp_path / "rahasia.pdf").write_bytes(b"x")
    a = A(); a.outbox = [tmp_path / "ws" / "ok.pdf", tmp_path / "rahasia.pdf", tmp_path / "ws" / "../rahasia.pdf"]
    got = drain_outbox(a, tmp_path / "ws")
    assert [g.name for g in got] == ["ok.pdf"] and a.outbox == []


def test_explicit_kirim_file_choice_overrides_autodetect(client):
    with client.websocket_connect("/ws") as ws:
        login(ws)
        ws.send_json({"type": "message", "text": "pilihfinal"})
        names = [m["name"] for m in collect_until(ws) if m["type"] == "file"]
        assert names == ["kajian_2.docx"]                         # versi perantara kajian.docx tidak ikut


@pytest.fixture
def open_client(fake_factory, tmp_path):
    mgr = SessionManager(fake_factory, tmp_path, approval_timeout=5)
    with TestClient(create_app(mgr, auth_off=True), base_url="http://localhost:8787") as c:
        yield c


def test_auth_off_config_and_chat_without_token(open_client):
    assert open_client.get("/config").json() == {"auth": False}
    with open_client.websocket_connect("/ws", headers={"host": "localhost:8787"}) as ws:
        ws.send_json({"type": "auth", "token": ""})
        assert ws.receive_json()["type"] == "ready"


def test_auth_on_config_reports_auth(client):
    assert client.get("/config").json() == {"auth": True}


def test_auth_off_rejects_foreign_host_and_cross_site(open_client):
    assert open_client.get("/config", headers={"host": "evil.example"}).status_code == 403
    assert open_client.get("/config", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    r = open_client.post("/upload", files={"file": ("a.txt", b"x")}, headers={"origin": "http://evil.example"})
    assert r.status_code == 403
    with pytest.raises(WebSocketDisconnect):
        with open_client.websocket_connect("/ws", headers={"origin": "http://evil.example"}) as ws:
            ws.receive_json()


def test_auth_off_upload_without_bearer(open_client):
    r = open_client.post("/upload", files={"file": ("a.txt", b"halo")})
    assert r.status_code == 200 and r.json()["path"].endswith("a.txt")


def test_auth_off_signed_files_still_need_signature(open_client):
    assert open_client.get("/files?p=a.txt&e=9999999999&s=abc").status_code == 403


def test_serve_refuses_auth_off_on_public_host(monkeypatch):
    from chunai.interfaces import web
    monkeypatch.setenv("CHUNAI_WEB_AUTH", "off")
    with pytest.raises(SystemExit):
        web.serve(host="0.0.0.0")


def test_run_serve_passes_auth_off(monkeypatch):
    import asyncio

    import uvicorn

    from chunai import cli
    from chunai.interfaces import core, web
    seen = {}
    monkeypatch.setenv("CHUNAI_WEB_AUTH", "off")
    monkeypatch.delenv("CHUNAI_TELEGRAM_TOKEN", raising=False)
    monkeypatch.setattr(core, "default_agent_factory", lambda: None)
    monkeypatch.setattr(web, "create_app", lambda m, t, auth_off=False: seen.setdefault("off", auth_off) or object())
    class S:
        def __init__(self, c): pass
        async def serve(self): pass
    monkeypatch.setattr(uvicorn, "Server", S)
    asyncio.run(cli.run_serve())
    assert seen["off"] is True
