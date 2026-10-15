"""Kebijakan izin: tool mana yang jalan otomatis, mana yang wajib persetujuan.

Prinsip: baca bebas, tulis harus izin. Default untuk tool tak dikenal = MINTA IZIN (fail-safe).
"""
from __future__ import annotations

import re
from enum import Enum


class Decision(str, Enum):
    AUTO = "auto"      # jalan otomatis
    ASK = "ask"        # wajib persetujuan pengguna
    DENY = "deny"      # selalu ditolak


# Tool bawaan yang hanya membaca / tidak mengubah apa pun di luar sesi.
READ_ONLY_TOOLS = {
    "Read", "Glob", "Grep", "WebSearch", "WebFetch",
    "TodoWrite", "Task", "Agent", "ListMcpResources", "ReadMcpResource", "ToolSearch",
    "mcp__chunai__periksa_laporan",
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


def classify(tool_name: str, tool_input: dict | None = None) -> Decision:
    tool_input = tool_input or {}
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
