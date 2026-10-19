"""Kebijakan izin: tool mana yang jalan otomatis, mana yang wajib persetujuan.

Prinsip: baca bebas, tulis harus izin. Default untuk tool tak dikenal = MINTA IZIN (fail-safe).
"""
from __future__ import annotations

import ipaddress
import re
import shlex
from enum import Enum
from urllib.parse import urlparse


class Decision(str, Enum):
    AUTO = "auto"      # jalan otomatis
    ASK = "ask"        # wajib persetujuan pengguna
    DENY = "deny"      # selalu ditolak


# Tool bawaan yang hanya membaca / tidak mengubah apa pun di luar sesi.
READ_ONLY_TOOLS = {
    "Read", "Glob", "Grep", "WebSearch", "WebFetch",
    "TodoWrite", "Task", "Agent", "ListMcpResources", "ReadMcpResource", "ToolSearch",
    "mcp__chunai__periksa_laporan", "mcp__chunai__profil_data",
    "mcp__chunai__buat_dokumen", "mcp__chunai__buat_presentasi",    # hanya menulis file baru di workspace/output/
    "mcp__chunai__periksa_dokumen", "mcp__chunai__pratinjau_file",
    "mcp__chunai__baca_dokumen", "mcp__chunai__revisi_dokumen",       # revisi menulis SALINAN baru di output/, tidak menimpa   # tidak menimpa file
    "mcp__chunai__buat_grafik",
    "mcp__chunai__buat_gambar", "mcp__chunai__edit_gambar", "mcp__chunai__buat_video", "mcp__chunai__slide_ke_video",
    "mcp__chunai__kirim_file",        # mengirim file workspace ke pengguna sendiri (chat yang sama)
    "mcp__chunai__jalankan_python",   # sandbox: tanpa jaringan, tulis hanya di workspace (lihat sandbox.py)   # hanya menulis PNG baru ke workspace/grafik/ (tidak menimpa)
}

# Tool yang mengubah file / menjalankan perintah -> perlu izin.
WRITE_TOOLS = {"Write", "Edit", "NotebookEdit", "Bash"}

# Tool MCP: kata kunci aksi yang berdampak keluar (kirim, submit, bayar, hapus, ...).
_SIDE_EFFECT = re.compile(
    r"(submit|send|post|publish|pay|purchase|buy|delete|remove|click|fill|type|upload|"
    r"transfer|confirm|approve|book|order|reply|email)", re.I)
_READ_HINT = re.compile(r"(read|get|list|search|fetch|snapshot|screenshot|navigate|find|view)", re.I)

# Perintah Bash yang tidak pernah boleh jalan, bahkan dengan persetujuan.
_DENY_BASH = re.compile(r"(rm\s+-rf\s+/(\s|$)|mkfs|:\(\)\s*\{|dd\s+if=.*of=/dev/|shutdown|reboot)", re.I)


# Web Agent: draf (membaca/mengisi) otomatis; klik & kirim SELALU minta izin.
WEB_DRAFT_TOOLS = {"mcp__chunai__baca_halaman", "mcp__chunai__isi_field", "mcp__chunai__siapkan_review"}
WEB_OPEN_TOOL = "mcp__chunai__buka_halaman"
WEB_FINAL_TOOLS = {"mcp__chunai__klik", "mcp__chunai__kirim_form"}


def host_allowed(url: str, allowed: set[str] | None) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host or not allowed:
        return False
    return any(host == d or host.endswith("." + d) for d in (x.lower().lstrip(".") for x in allowed))


def is_public_host(url: str) -> bool:
    """True bila host tampak seperti situs publik. Menolak localhost, IP privat/loopback/link-local, nama tanpa titik,
    dan akhiran internal (.local/.internal/.lan). Pemeriksaan nama saja (tanpa DNS)."""
    host = (urlparse(url).hostname or "").lower().rstrip(".")
    if not host or ("." not in host and ":" not in host):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        pass
    return not host.endswith((".local", ".internal", ".lan", ".localhost", ".home", ".corp", ".intranet"))


_SAFE_CMDS = {"ls", "head", "tail", "wc", "cat", "pwd", "file", "stat", "du"}
_SAFE_FLAG = re.compile(r"^-[A-Za-z0-9]+$|^-n$|^--(lines|bytes|human-readable)=?\d*$")
_BAD_CHARS = re.compile(r"[;`$<>(){}\\\n\r~&|]")


def is_safe_readonly_bash(command: str) -> bool:
    """True hanya untuk perintah baca-saja sederhana pada path RELATIF (di workspace):
    ls/head/tail/wc/cat/pwd/file/stat/du, digabung dengan && atau |. Tanpa pengalihan, subshell, variabel, path absolut atau '..'."""
    command = (command or "").strip()
    if not command or len(command) > 400:
        return False
    for seg in re.split(r"&&|\|", command):
        if _BAD_CHARS.search(seg):
            return False
        try:
            toks = shlex.split(seg)
        except ValueError:
            return False
        if not toks or toks[0] not in _SAFE_CMDS:
            return False
        for t in toks[1:]:
            if t.startswith("-"):
                if not _SAFE_FLAG.match(t) or t in ("-f", "-F", "--follow"):
                    return False
            elif t.isdigit():
                continue
            elif t.startswith("/") or ".." in t.split("/") or t.startswith("~"):
                return False
    return True


_FINAL_TEXT = re.compile(
    r"(kirim|submit|selesai|finish|bayar|pay|checkout|hapus|delete|remove|konfirmasi|confirm|simpan|save|setuju|agree|daftar|register|sign ?up|"
    r"pesan|order|beli|buy|publish|terbitkan|send|post|ajukan|apply|log ?out|sign ?out|keluar|unggah|upload|donasi|donate|transfer|batalkan|cancel|akhiri|end|"
    r"serahkan|turn in|kumpulkan|masuk|login|sign ?in)", re.I)
_NAV_TEXT = re.compile(r"^\W*((lanjut(kan)?|next|continue)( ke| to)?[\w ]{0,30}|berikutnya|selanjutnya|sebelumnya|previous|prev|kembali|back)\W*$", re.I)
_SAFE_ROLES = {"option", "tab", "combobox", "menuitem", "radio", "checkbox"}


def click_is_safe(e: dict) -> bool:
    """Klik NAVIGASI/pemilihan yang tidak mengirim atau mengubah data (pilih opsi, tab, tautan biasa, Lanjut/Berikutnya).
    Gagal-tertutup: apa pun yang meragukan (tombol lain, teks Kirim/Selesai/Bayar/Hapus/Simpan/Keluar, dst.) tetap minta izin."""
    label = str(e.get("label", ""))
    tag, typ, role = e.get("tag", ""), e.get("type", ""), e.get("role", "")
    if _FINAL_TEXT.search(label):
        return False
    if tag == "input" and typ in ("radio", "checkbox"):
        return True
    if role in _SAFE_ROLES:
        return True
    if tag == "a" and str(e.get("href", "")).lower().startswith(("http://", "https://")):
        return True
    if tag == "button" or typ in ("button", "submit") or role == "button":
        return bool(_NAV_TEXT.match(label))
    return False


def classify(tool_name: str, tool_input: dict | None = None, allowed_domains: set[str] | None = None) -> Decision:
    tool_input = tool_input or {}
    if tool_name == WEB_OPEN_TOOL:
        url = str(tool_input.get("url", ""))
        if host_allowed(url, allowed_domains):
            return Decision.AUTO
        # situs baru: minta izin SEKALI (bisa disimpan permanen); alamat internal/privat tidak pernah boleh
        return Decision.ASK if is_public_host(url) else Decision.DENY
    if tool_name in WEB_DRAFT_TOOLS:
        return Decision.AUTO
    if tool_name in WEB_FINAL_TOOLS:
        return Decision.ASK
    if tool_name == "Bash" and _DENY_BASH.search(str(tool_input.get("command", ""))):
        return Decision.DENY
    if tool_name == "Bash" and is_safe_readonly_bash(str(tool_input.get("command", ""))):
        return Decision.AUTO
    if tool_name in READ_ONLY_TOOLS:
        return Decision.AUTO
    if tool_name in WRITE_TOOLS:
        return Decision.ASK
    if tool_name.startswith("mcp__"):
        action = tool_name.split("__")[-1]
        if _SIDE_EFFECT.search(action):
            return Decision.ASK
        if _READ_HINT.search(action):
            return Decision.AUTO
    return Decision.ASK  # tak dikenal -> tanya
