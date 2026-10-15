"""chunai setup-telegram: tempel token bot -> divalidasi -> ID pemilik terdeteksi dari pesan pertama -> disimpan ke .env."""
from __future__ import annotations

import re
import time
from dataclasses import dataclass

import httpx

_TOKEN_RE = re.compile(r"^\d{6,}:[A-Za-z0-9_\-]{30,}$")
API = "https://api.telegram.org"


def valid_token_format(tok: str) -> bool:
    return bool(_TOKEN_RE.match(tok))


@dataclass
class Candidate:
    user_id: int
    name: str
    username: str
    update_id: int


class SetupError(Exception):
    pass


def _call(client: httpx.Client, base: str, token: str, method: str, **params):
    try:
        r = client.post(f"{base}/bot{token}/{method}", json=params, timeout=params.get("timeout", 10) + 15)
        js = r.json()
    except httpx.HTTPError as e:
        raise SetupError(f"Tidak bisa menjangkau Telegram ({type(e).__name__}). Periksa koneksi internet.") from None
    except ValueError:
        raise SetupError("Balasan Telegram tidak dikenali.") from None
    if not js.get("ok"):
        desc = str(js.get("description", "")).replace(token, "***")
        raise SetupError("Token ditolak Telegram (Unauthorized). Salin ulang dari @BotFather." if r.status_code == 401 else f"Telegram: {desc}")
    return js["result"]


def get_bot(client: httpx.Client, token: str, base: str = API) -> dict:
    me = _call(client, base, token, "getMe")
    wh = _call(client, base, token, "getWebhookInfo")
    if wh.get("url"):
        _call(client, base, token, "deleteWebhook", drop_pending_updates=False)   # webhook lama menghalangi getUpdates
    return me


def wait_for_owner(client: httpx.Client, token: str, seconds: int = 120, base: str = API, now=time.monotonic) -> Candidate | None:
    """Tunggu pesan PRIBADI pertama ke bot; kembalikan pengirimnya. Grup/kanal diabaikan."""
    end, offset = now() + seconds, 0
    while now() < end:
        remain = max(1, int(end - now()))
        updates = _call(client, base, token, "getUpdates", offset=offset, timeout=min(10, remain), allowed_updates=["message"])
        for u in updates:
            offset = max(offset, u["update_id"] + 1)
            m = u.get("message") or {}
            if (m.get("chat") or {}).get("type") != "private" or not m.get("from") or m["from"].get("is_bot"):
                continue
            f = m["from"]
            name = " ".join(x for x in (f.get("first_name"), f.get("last_name")) if x) or "(tanpa nama)"
            return Candidate(int(f["id"]), name, f.get("username") or "", u["update_id"])
        if not updates and now() >= end:
            break
    return None


def acknowledge(client: httpx.Client, token: str, upto_update_id: int, base: str = API) -> None:
    _call(client, base, token, "getUpdates", offset=upto_update_id + 1, timeout=0)


def run_setup(ask_secret, ask_yes, say, client: httpx.Client, save, base: str = API, wait_seconds: int = 120) -> bool:
    """Alur interaktif. ask_secret/ask_yes/say/save disuntik agar bisa diuji. Kembalikan True bila tersimpan."""
    say("Hubungkan bot Telegram ke ChunAI.\n"
        "Siapkan token bot: Telegram > @BotFather > /mybots > pilih bot Anda > API Token.\n")
    token = ask_secret("Tempel token bot (tidak ditampilkan), lalu Enter: ").strip().strip("\"'")
    if not valid_token_format(token):
        say("Bentuk token tidak sesuai (contoh: 123456789:AAxxxxxxxx...). Pastikan tertempel utuh, satu baris.")
        return False
    try:
        me = get_bot(client, token, base)
    except SetupError as e:
        say(f"❌ {e}")
        return False
    uname = me.get("username", "?")
    say(f"✅ Bot ditemukan: @{uname}\n\n"
        f"Sekarang buka Telegram, cari @{uname}, lalu kirim pesan apa saja (mis. 'halo').\n"
        f"Saya menunggu sampai {wait_seconds} detik...")
    try:
        cand = wait_for_owner(client, token, wait_seconds, base)
    except SetupError as e:
        say(f"❌ {e}")
        return False
    if cand is None:
        say("Tidak ada pesan masuk. Ulangi: chunai setup-telegram")
        return False
    label = f"{cand.name}" + (f" (@{cand.username})" if cand.username else "")
    say(f"\nPesan diterima dari: {label}, ID {cand.user_id}")
    if not ask_yes(f"Jadikan {label} satu-satunya pemilik yang dilayani ChunAI? [y/T]: "):
        say("Dibatalkan. Tidak ada yang disimpan.")
        return False
    save("CHUNAI_TELEGRAM_TOKEN", token)
    save("CHUNAI_TELEGRAM_USERS", str(cand.user_id))
    try:
        acknowledge(client, token, cand.update_id, base)
        _call(client, base, token, "sendMessage", chat_id=cand.user_id,
              text="✅ ChunAI terhubung ke akun ini. Jalankan ChunAI di komputer Anda, lalu kirim /start.")
    except SetupError:
        pass
    say(f"\n✅ Tersimpan di .env: token bot @{uname} dan ID pemilik {cand.user_id}.\nLangkah berikut: ./scripts/run.sh")
    return True
