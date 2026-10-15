"""Kebijakan izin: tool mana yang jalan otomatis, mana yang wajib persetujuan.

Prinsip: baca bebas, tulis harus izin. Default untuk tool tak dikenal = MINTA IZIN (fail-safe).
"""
from __future__ import annotations

import re
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
    "mcp__chunai__buat_grafik",   # hanya menulis PNG baru ke workspace/grafik/ (tidak menimpa)
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


def classify(tool_name: str, tool_input: dict | None = None, allowed_domains: set[str] | None = None) -> Decision:
    tool_input = tool_input or {}
    if tool_name == WEB_OPEN_TOOL:
        return Decision.AUTO if host_allowed(str(tool_input.get("url", "")), allowed_domains) else Decision.ASK
    if tool_name in WEB_DRAFT_TOOLS:
        return Decision.AUTO
    if tool_name in WEB_FINAL_TOOLS:
        return Decision.ASK
    if tool_name == "Bash" and _DENY_BASH.search(str(tool_input.get("command", ""))):
        return Decision.DENY
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
