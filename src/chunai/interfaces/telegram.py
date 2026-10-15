"""Antarmuka Telegram (Bot API, long polling). Hanya melayani ID pengguna yang diizinkan."""
from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx

from ..approval import ApprovalRequest
from ..policy import WEB_FINAL_TOOLS
from ..timeutil import describe
from .core import MAX_UPLOAD_BYTES, SessionManager, save_upload

log = logging.getLogger("chunai.telegram")
MAX_MSG = 3900
HELP = ("Saya ChunAI. Kirim perintah kerja (riset, analisis, kajian, presentasi, tugas web).\n"
        "Aksi berdampak (kirim form, dsb.) selalu meminta izin Anda lewat tombol.\n\n"
        "/status – keadaan sesi\n/stop – hentikan tugas berjalan\n/reset – mulai sesi baru\n/id – ID Telegram Anda\n"
        "Kirim file (CSV/XLSX/PDF/DOCX/PPTX) untuk dianalisis; sebutkan apa yang diinginkan.")


def split_text(text: str, limit: int = MAX_MSG) -> list[str]:
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > limit:
            if cur:
                parts.append(cur); cur = ""
            parts.append(line[:limit]); line = line[limit:]
        if len(cur) + len(line) + 1 > limit:
            parts.append(cur); cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    if cur:
        parts.append(cur)
    return parts or [""]


class TelegramChannel:
    def __init__(self, bot: "TelegramBot", chat_id: int):
        self.bot, self.chat_id = bot, chat_id

    async def send_text(self, text: str) -> None:
        for part in split_text(text):
            if part.strip():
                await self.bot.api("sendMessage", {"chat_id": self.chat_id, "text": part, "disable_web_page_preview": True})

    async def send_file(self, path: Path, caption: str = "") -> None:
        if path.stat().st_size > 49 * 1024 * 1024:
            await self.send_text(f"File {path.name} terlalu besar untuk Telegram.")
            return
        method, field = ("sendPhoto", "photo") if path.suffix.lower() in (".png", ".jpg", ".jpeg") else ("sendDocument", "document")
        await self.bot.api(method, {"chat_id": self.chat_id, "caption": caption[:900]}, files={field: (path.name, path.read_bytes())})

    async def request_approval(self, aid: str, req: ApprovalRequest, image: Path | None) -> None:
        if image:
            await self.send_file(image, "Tangkapan layar untuk review")
        name = req.tool.replace("mcp__chunai__", "")
        buttons = [{"text": "✅ Setuju", "callback_data": f"ap:{aid}:a"}, {"text": "❌ Tolak", "callback_data": f"ap:{aid}:d"}]
        rows = [buttons]
        if req.tool not in WEB_FINAL_TOOLS:
            rows.append([{"text": "♾ Selalu izinkan (sesi ini)", "callback_data": f"ap:{aid}:s"}])
        body = f"🔒 PERMINTAAN IZIN: {name}\n\n{req.summary}"[:MAX_MSG]
        await self.bot.api("sendMessage", {"chat_id": self.chat_id, "text": body,
                                           "reply_markup": {"inline_keyboard": rows}})


class TelegramBot:
    def __init__(self, token: str, allowed_ids: set[int], manager: SessionManager,
                 base_url: str = "https://api.telegram.org", client: httpx.AsyncClient | None = None,
                 poll_timeout: int = 30):
        if not allowed_ids:
            raise ValueError("CHUNAI_TELEGRAM_USERS kosong: tentukan ID pengguna yang diizinkan.")
        self.token, self.allowed, self.mgr = token, set(allowed_ids), manager
        self.base = base_url.rstrip("/")
        self.client = client or httpx.AsyncClient(timeout=poll_timeout + 15)
        self.poll_timeout, self.offset, self._stop = poll_timeout, 0, False

    # ---------- API ----------
    async def api(self, method: str, data: dict | None = None, files: dict | None = None):
        url = f"{self.base}/bot{self.token}/{method}"
        if files:
            r = await self.client.post(url, data={k: v for k, v in (data or {}).items()}, files=files)
        else:
            r = await self.client.post(url, json=data or {})
        try:
            js = r.json()
        except ValueError:
            raise RuntimeError(f"Telegram {method}: respons bukan JSON (HTTP {r.status_code})") from None
        if not js.get("ok"):
            raise RuntimeError(f"Telegram {method} gagal: {js.get('description')}")
        return js["result"]

    async def download(self, file_id: str) -> tuple[str, bytes]:
        info = await self.api("getFile", {"file_id": file_id})
        if int(info.get("file_size", 0)) > MAX_UPLOAD_BYTES:
            raise ValueError("File terlalu besar (maks 20 MB).")
        r = await self.client.get(f"{self.base}/file/bot{self.token}/{info['file_path']}")
        r.raise_for_status()
        return Path(info["file_path"]).name, r.content

    # ---------- diagnosis & loop ----------
    async def check(self) -> dict:
        """Verifikasi token & keadaan bot. Mengembalikan info yang aman ditampilkan (tanpa token)."""
        me = await self.api("getMe")
        wh = await self.api("getWebhookInfo")
        return {"username": me.get("username"), "id": me.get("id"), "webhook_url": wh.get("url") or "",
                "pending_updates": wh.get("pending_update_count", 0), "allowed_ids": sorted(self.allowed)}

    async def prepare(self) -> dict:
        """Dipanggil sebelum polling: pastikan tidak ada webhook (webhook membuat getUpdates ditolak)."""
        info = await self.check()
        if info["webhook_url"]:
            log.warning("Webhook terdaftar (%s) dihapus agar long polling bisa jalan.", info["webhook_url"])
            await self.api("deleteWebhook", {"drop_pending_updates": False})
        return info

    async def run(self):
        info = await self.prepare()
        log.info("ChunAI Telegram berjalan sebagai @%s; pengguna diizinkan: %s", info["username"], sorted(self.allowed))
        await self.announce("✅ ChunAI aktif. Jika sebelumnya ada tugas atau tombol izin yang menggantung, "
                            "itu sudah dibatalkan karena ChunAI dimulai ulang; kirim ulang perintahnya.")
        backoff = 1
        while not self._stop:
            try:
                updates = await self.api("getUpdates", {"offset": self.offset, "timeout": self.poll_timeout,
                                                        "allowed_updates": ["message", "callback_query"]})
                backoff = 1
                for u in updates:
                    self.offset = max(self.offset, u["update_id"] + 1)
                    asyncio.create_task(self._safe(self.handle_update(u)))
            except asyncio.CancelledError:
                raise
            except Exception as e:
                msg = str(e)
                if "Conflict" in msg:
                    log.error("Konflik: instance bot lain memakai token yang sama. Hentikan yang lain; menunggu...")
                    backoff = 15
                elif "Unauthorized" in msg:
                    raise RuntimeError("Token Telegram ditolak (Unauthorized). Periksa CHUNAI_TELEGRAM_TOKEN.") from None
                else:
                    log.warning("polling gagal: %s", msg.replace(self.token, "***"))
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def announce(self, text: str):
        for uid in sorted(self.allowed):
            try:
                await self.api("sendMessage", {"chat_id": uid, "text": text})
            except Exception as e:           # pengguna belum pernah /start ke bot, dsb.
                log.info("pengumuman ke %s tidak terkirim: %s", uid, str(e).replace(self.token, "***"))

    def stop(self):
        self._stop = True

    async def _safe(self, coro):
        try:
            await coro
        except Exception as e:
            log.exception("handler gagal: %s", e)

    # ---------- penanganan ----------
    async def handle_update(self, u: dict):
        if "callback_query" in u:
            return await self.handle_callback(u["callback_query"])
        m = u.get("message")
        if not m:
            return
        chat, user = m["chat"], m.get("from", {})
        uid = int(user.get("id", 0))
        if chat.get("type") != "private":
            return                                     # abaikan grup/kanal
        if uid not in self.allowed:
            await self.api("sendMessage", {"chat_id": chat["id"],
                           "text": f"Akses ditolak. ID Telegram Anda: {uid}.\nPemilik ChunAI perlu menambahkan ID ini ke CHUNAI_TELEGRAM_USERS."})
            return
        key = f"tg{uid}"
        sess = self.mgr.get(key)
        sess.channel = TelegramChannel(self, chat["id"])
        text = (m.get("text") or m.get("caption") or "").strip()

        if "document" in m or "photo" in m:
            return await self._handle_upload(m, sess, text)
        if text.startswith("/"):
            return await self._command(text, uid, sess)
        if not text:
            return
        if not sess.start_turn(text):
            await sess.channel.send_text("Masih memproses tugas sebelumnya. Kirim /stop untuk membatalkan.")
            return
        await self.api("sendChatAction", {"chat_id": chat["id"], "action": "typing"})

    async def _handle_upload(self, m, sess, caption: str):
        try:
            if "document" in m:
                fid, name = m["document"]["file_id"], m["document"].get("file_name")
            else:
                fid, name = m["photo"][-1]["file_id"], None
            tg_name, data = await self.download(fid)
            path = save_upload(sess.workdir, name or tg_name, data)
        except Exception as e:
            return await sess.channel.send_text(f"Gagal menerima file: {e}")
        rel = str(path.relative_to(sess.workdir))
        sess.uploads.append(rel)
        if caption and not caption.startswith("/") and sess.start_turn(caption):
            return
        await sess.channel.send_text(f"File diterima: {rel}\nApa yang ingin Anda lakukan dengan file ini?")

    async def _command(self, text: str, uid: int, sess):
        cmd = text.split()[0].split("@")[0].lower()
        log.info("perintah %s dari %s", cmd, uid)
        ch = sess.channel
        if cmd in ("/start", "/help"):
            await ch.send_text(HELP)
        elif cmd == "/id":
            await ch.send_text(f"ID Telegram Anda: {uid}")
        elif cmd == "/stop":
            await sess.stop() if sess.busy or sess.broker.pending else await ch.send_text("Tidak ada tugas berjalan.")
        elif cmd == "/reset":
            ch_ = sess.channel
            await self.mgr.reset(f"tg{uid}")
            await ch_.send_text("Sesi baru dimulai.")
        elif cmd == "/status":
            await ch.send_text(f"Sesi: {'sibuk' if sess.busy else 'siap'}\nMenunggu izin: {len(sess.broker.pending)}\nWaktu: {describe()}")
        else:
            await ch.send_text("Perintah tidak dikenal. Ketik /help.")

    async def handle_callback(self, cq: dict):
        uid = int(cq.get("from", {}).get("id", 0))
        if uid not in self.allowed:
            return await self.api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": "Tidak diizinkan.", "show_alert": True})
        parts = (cq.get("data") or "").split(":")
        if len(parts) != 3 or parts[0] != "ap":
            return await self.api("answerCallbackQuery", {"callback_query_id": cq["id"]})
        _, aid, code = parts
        sess = self.mgr.get(f"tg{uid}")                # hanya sesi milik pengguna ini
        decision = {"a": "approve", "d": "deny", "s": "always"}.get(code, "deny")
        ok = sess.broker.resolve(aid, decision)
        log.info("tombol izin %s -> %s (%s)", aid, decision, "diterima" if ok else "kedaluwarsa")
        label = {"approve": "✅ Disetujui", "always": "♾ Disetujui (selalu)", "deny": "❌ Ditolak"}[decision]
        try:
            await self.api("answerCallbackQuery", {"callback_query_id": cq["id"], "text": label if ok else "Permintaan sudah kedaluwarsa."})
        except RuntimeError as e:          # tombol lama (mis. setelah restart): Telegram menolak jawaban; tidak fatal
            log.info("callback lama diabaikan: %s", e)
        msg = cq.get("message") or {}
        if not ok and msg:
            try:
                await self.api("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                                          "reply_markup": {"inline_keyboard": []}})
                await self.api("sendMessage", {"chat_id": msg["chat"]["id"], "text": "⌛ Permintaan izin itu sudah kedaluwarsa (ChunAI dimulai ulang). Kirim ulang perintahnya."})
            except RuntimeError:
                pass
        if ok and msg:
            await self.api("editMessageReplyMarkup", {"chat_id": msg["chat"]["id"], "message_id": msg["message_id"],
                                                      "reply_markup": {"inline_keyboard": []}})
            await self.api("sendMessage", {"chat_id": msg["chat"]["id"], "text": label})


def allowed_ids_from_env() -> set[int]:
    return {int(x) for x in os.environ.get("CHUNAI_TELEGRAM_USERS", "").replace(" ", "").split(",") if x.strip().isdigit()}
