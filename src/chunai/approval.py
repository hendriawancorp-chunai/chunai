"""Approval Gate: aksi berdampak harus disetujui pengguna sebelum dieksekusi."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .audit import AuditLog
from .policy import Decision, classify


@dataclass
class ApprovalRequest:
    tool: str
    input: dict
    summary: str = ""


@dataclass
class ApprovalResult:
    approved: bool
    note: str = ""                      # alasan/edit dari pengguna
    updated_input: dict | None = None   # pengguna boleh mengedit parameter


Reviewer = Callable[[ApprovalRequest], Awaitable[ApprovalResult]]


def summarize(tool: str, tool_input: dict, limit: int = 600) -> str:
    text = json.dumps(tool_input, ensure_ascii=False, indent=2)
    return text if len(text) <= limit else text[:limit] + " ...(dipotong)"


@dataclass
class ApprovalGate:
    reviewer: Reviewer
    audit: AuditLog
    auto_approve: set[str] = field(default_factory=set)  # tool yang sudah "selalu izinkan" di sesi ini

    async def check(self, tool: str, tool_input: dict) -> ApprovalResult:
        decision = classify(tool, tool_input)
        if decision is Decision.DENY:
            self.audit.record("denied_by_policy", tool=tool, input=tool_input)
            return ApprovalResult(False, "Diblokir oleh kebijakan keamanan ChunAI.")
        if decision is Decision.AUTO or tool in self.auto_approve:
            self.audit.record("auto_allowed", tool=tool)
            return ApprovalResult(True)

        req = ApprovalRequest(tool, tool_input, summarize(tool, tool_input))
        self.audit.record("approval_requested", tool=tool, input=tool_input)
        result = await self.reviewer(req)
        self.audit.record("approval_decision", tool=tool, approved=result.approved, note=result.note)
        if result.approved and result.note == "always":
            self.auto_approve.add(tool)
        return result
