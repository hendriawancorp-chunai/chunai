import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
import pytest_asyncio

from chunai.browser import WebConfig, WebError, WebSession, find_chromium

HARD = """<html><head><title>Sulit</title></head><body>
<div role="combobox" aria-label="Pilih unit">Unit</div>
<label>Unggah dokumen <input type="file" id="f"></label>
<div>Verifikasi: saya bukan robot (CAPTCHA)</div>
<iframe src="http://127.0.0.1:{port}/frame"></iframe>
<iframe src="http://localhost:{port}/frame"></iframe>
</body></html>"""
FRAME = "<html><body><label>Isian dalam bingkai <input name=x></label></body></html>"
LOGIN = "<html><head><title>Masuk</title></head><body><form><label>Kata sandi <input type=password></label></form></body></html>"
INSIDE = "<html><head><title>Dasbor</title></head><body><h1>Halo demo</h1></body></html>"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): ...

    def do_GET(self):
        port = self.server.server_port
        if self.path == "/frame":
            body = FRAME
        elif self.path == "/secret":
            body = INSIDE if "sid=valid" in (self.headers.get("Cookie") or "") else LOGIN
        else:
            body = HARD.format(port=port)
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
        self.wfile.write(body.encode())


@pytest.fixture(scope="module")
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


@pytest_asyncio.fixture
async def web(tmp_path):
    if not find_chromium():
        pytest.skip("Chromium tidak tersedia")
    s = WebSession(WebConfig(allowed_domains={"127.0.0.1"}), tmp_path)
    yield s
    await s.close()


def idx_of(text, label):
    for line in text.splitlines():
        if label in line and line.startswith("["):
            return int(line[1:line.index("]")])
    raise AssertionError(f"{label} tidak ditemukan:\n{text}")


async def test_role_elements_and_allowed_iframe_listed(web, server):
    out = await web.buka(server + "/hard")
    assert "combobox" in out
    assert "(iframe)" in out and "Isian dalam bingkai" in out
    i = idx_of(out, "Isian dalam bingkai")
    assert "diisi" in await web.isi(i, "halo")
    assert "halo" in await web.form_state()


async def test_offlist_iframe_ignored_with_warning(web, server):
    out = await web.buka(server + "/hard")
    assert out.count("Isian dalam bingkai") == 1          # iframe localhost tidak ikut terdaftar
    assert "iframe" in out.lower() and "diabaikan" in out.lower()


async def test_captcha_detected_and_file_input_refused(web, server):
    out = await web.buka(server + "/hard")
    assert "CAPTCHA" in out and "TIDAK boleh" in out
    with pytest.raises(WebError, match="tidak didukung"):
        await web.isi(idx_of(out, "Unggah dokumen"), "x")


async def test_login_page_detected(web, server):
    out = await web.buka(server + "/secret")
    assert "login" in out.lower() and "chunai login" in out


async def test_session_cookie_restored_from_state_file(tmp_path, server):
    if not find_chromium():
        pytest.skip("Chromium tidak tersedia")
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"cookies": [
        {"name": "sid", "value": "valid", "domain": "127.0.0.1", "path": "/", "expires": -1,
         "httpOnly": True, "secure": False, "sameSite": "Lax"},
        {"name": "sid", "value": "valid", "domain": "evil.example", "path": "/", "expires": -1,
         "httpOnly": True, "secure": False, "sameSite": "Lax"}], "origins": []}))
    cfg = WebConfig(allowed_domains={"127.0.0.1"}, mode="profile", profile_dir=str(tmp_path / "prof"),
                    headless=True, state_file=str(state))
    w = WebSession(cfg, tmp_path)
    try:
        out = await w.buka(server + "/secret")
        assert "Halo demo" in out
        cookies = await w._ctx.cookies()
        assert all(c["domain"].lstrip(".") != "evil.example" for c in cookies)
    finally:
        await w.close()
