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
