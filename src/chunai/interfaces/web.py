"""Antarmuka Web: chat via WebSocket + kartu persetujuan. Wajib token; default hanya localhost."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from ..approval import ApprovalRequest
from ..policy import WEB_FINAL_TOOLS
from .core import MAX_UPLOAD_BYTES, SessionManager, save_upload

STATIC = Path(__file__).parent / "static"
SESSION_KEY = "web"
URL_TTL = 3600


class WebChannel:
    def __init__(self, ws: WebSocket, signer):
        self.ws, self.sign = ws, signer

    async def _send(self, obj: dict):
        try:
            await self.ws.send_text(json.dumps(obj, ensure_ascii=False))
        except Exception:
            pass                                             # koneksi putus; jawaban izin akan kedaluwarsa = ditolak

    async def send_text(self, text: str) -> None:
        await self._send({"type": "text", "text": text})

    async def send_file(self, path: Path, caption: str = "") -> None:
        await self._send({"type": "file", "name": path.name, "url": self.sign(path), "image": path.suffix.lower() in (".png", ".jpg", ".jpeg")})

    async def request_approval(self, aid: str, req: ApprovalRequest, image: Path | None) -> None:
        await self._send({"type": "approval", "id": aid, "tool": req.tool.replace("mcp__chunai__", ""),
                          "summary": req.summary, "final": req.tool in WEB_FINAL_TOOLS,
                          "image": self.sign(image) if image else None})


def create_app(manager: SessionManager, token: str | None = None) -> FastAPI:
    token = token or os.environ.get("CHUNAI_WEB_TOKEN") or secrets.token_urlsafe(24)
    @asynccontextmanager
    async def lifespan(_app):
        yield
        await manager.close_all()

    app = FastAPI(title="ChunAI", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.token = token
    state = {"ws": None}

    def ok_token(t: str | None) -> bool:
        return bool(t) and hmac.compare_digest(t.encode(), token.encode())

    def workdir() -> Path:
        return manager.get(SESSION_KEY).workdir

    def sign(path: Path) -> str:
        rel = str(path.resolve().relative_to(workdir().resolve()))
        exp = int(time.time()) + URL_TTL
        sig = hmac.new(token.encode(), f"{rel}|{exp}".encode(), hashlib.sha256).hexdigest()
        return f"/files?p={quote(rel)}&e={exp}&s={sig}"

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' ws: wss:"})

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.post("/upload")
    async def upload(file: UploadFile = File(...), authorization: str | None = Header(None)):
        if not ok_token((authorization or "").removeprefix("Bearer ").strip()):
            raise HTTPException(401, "Token salah")
        data = await file.read(MAX_UPLOAD_BYTES + 1)
        try:
            path = save_upload(workdir(), file.filename or "file", data)
        except ValueError as e:
            raise HTTPException(413, str(e))
        rel = str(path.relative_to(workdir()))
        manager.get(SESSION_KEY).uploads.append(rel)
        return JSONResponse({"path": rel})

    @app.get("/files")
    async def files(p: str = Query(...), e: int = Query(...), s: str = Query(...)):
        want = hmac.new(token.encode(), f"{p}|{e}".encode(), hashlib.sha256).hexdigest()
        if e < time.time() or not hmac.compare_digest(want, s):
            raise HTTPException(403, "Tautan tidak valid atau kedaluwarsa")
        base = workdir().resolve()
        path = (base / p).resolve()
        if base not in path.parents or not path.is_file():
            raise HTTPException(404)
        return FileResponse(path, filename=path.name, headers={"X-Content-Type-Options": "nosniff"})

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and urlparse(origin).netloc != ws.headers.get("host"):
            await ws.close(code=4403)                       # cegah cross-site WebSocket hijacking
            return
        await ws.accept()
        try:
            first = json.loads(await asyncio.wait_for(ws.receive_text(), 15))
        except Exception:
            await ws.close(code=4400); return
        if first.get("type") != "auth" or not ok_token(first.get("token")):
            await asyncio.sleep(1)
            await ws.send_text(json.dumps({"type": "error", "text": "Token salah."}))
            await ws.close(code=4401); return
        old = state["ws"]
        if old is not None and old is not ws:
            try: await old.close(code=4000)
            except Exception: pass
        state["ws"] = ws
        sess = manager.get(SESSION_KEY)
        sess.channel = WebChannel(ws, sign)
        await ws.send_text(json.dumps({"type": "ready", "busy": sess.busy, "pending": len(sess.broker.pending)}))

        async def watch(task):
            try:
                await task
            finally:
                await sess.channel._send({"type": "done"})

        try:
            while True:
                msg = json.loads(await ws.receive_text())
                t = msg.get("type")
                if t == "message":
                    text = str(msg.get("text", "")).strip()
                    if not text:
                        continue
                    if sess.start_turn(text):
                        await sess.channel._send({"type": "busy"})
                        asyncio.create_task(watch(sess.task))
                    else:
                        await sess.channel.send_text("Masih memproses tugas sebelumnya. Tekan Stop untuk membatalkan.")
                elif t == "approval":
                    sess.broker.resolve(str(msg.get("id")), str(msg.get("decision")), str(msg.get("note", "")))
                elif t == "stop":
                    await sess.stop()
                elif t == "reset":
                    await manager.reset(SESSION_KEY)
                    sess = manager.get(SESSION_KEY); sess.channel = WebChannel(ws, sign)
                    await sess.channel.send_text("Sesi baru dimulai.")
                elif t == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
        except WebSocketDisconnect:
            pass
        finally:
            if state["ws"] is ws:
                state["ws"] = None

    return app


def serve(host: str = "127.0.0.1", port: int = 8787):
    import uvicorn

    from .core import default_agent_factory
    token = os.environ.get("CHUNAI_WEB_TOKEN") or secrets.token_urlsafe(24)
    mgr = SessionManager(default_agent_factory())
    app = create_app(mgr, token)
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("⚠ Server tidak hanya di localhost. Gunakan HTTPS (reverse proxy/tunnel) dan token yang kuat.")
    print(f"ChunAI Web: http://{host}:{port}\nToken akses: {token}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
