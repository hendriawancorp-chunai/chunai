"""Approval Gate: aksi berdampak harus disetujui pengguna sebelum dieksekusi."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .audit import AuditLog
from urllib.parse import urlparse

from .policy import DOWNLOAD_TOOL, WEB_FINAL_TOOLS, WEB_OPEN_TOOL, Decision, classify


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
    allowed_domains: set[str] = field(default_factory=set)
    # pratinjau berbasis kondisi NYATA (mis. isi form dibaca dari halaman), bukan klaim agen
    previewers: dict[str, Callable[[dict], Awaitable[str]]] = field(default_factory=dict)
    click_probe: Callable[[dict], Awaitable[bool]] | None = None   # True = klik navigasi/pilihan aman (tanpa kartu)
    final_guard: Callable[[str, dict], Awaitable[str | None]] | None = None      # pesan penolakan (mis. batas harian media sosial)
    on_final_approved: Callable[[str, dict], Awaitable[None]] | None = None      # dicatat/ditunda setelah pengguna menyetujui aksi akhir
    on_domain: Callable[[str, bool], None] | None = None   # (host, permanen) saat pengguna mengizinkan situs baru

    async def check(self, tool: str, tool_input: dict) -> ApprovalResult:
        decision = classify(tool, tool_input, self.allowed_domains)
        if decision is Decision.DENY:
            self.audit.record("denied_by_policy", tool=tool, input=tool_input)
            return ApprovalResult(False, "Diblokir oleh kebijakan keamanan ChunAI.")
        # aksi final web tidak pernah masuk "selalu izinkan"
        always_ok = tool in self.auto_approve and tool not in WEB_FINAL_TOOLS and tool not in (WEB_OPEN_TOOL, DOWNLOAD_TOOL)
        if decision is Decision.AUTO or always_ok:
            self.audit.record("auto_allowed", tool=tool)
            return ApprovalResult(True)

        if tool in WEB_FINAL_TOOLS and tool != "mcp__chunai__unggah_berkas" and self.final_guard:
            try:
                msg = await self.final_guard(tool, tool_input)
            except Exception:
                msg = None
            if msg:
                self.audit.record("denied_by_guard", tool=tool, reason=msg[:120])
                return ApprovalResult(False, msg)
        if tool == "mcp__chunai__klik" and self.click_probe:
            try:
                if await self.click_probe(tool_input):
                    self.audit.record("auto_allowed", tool=tool, kind="navigasi/pilihan", input=tool_input)
                    return ApprovalResult(True)
            except Exception:
                pass          # ragu -> tanya pengguna

        summary = summarize(tool, tool_input)
        if tool in self.previewers:
            try:
                summary += "\n--- PRATINJAU NYATA ---\n" + await self.previewers[tool](tool_input)
            except Exception as e:  # pratinjau gagal -> tetap tanya, tapi beri tahu
                summary += f"\n(pratinjau gagal: {e})"
        req = ApprovalRequest(tool, tool_input, summary)
        self.audit.record("approval_requested", tool=tool, input=tool_input)
        result = await self.reviewer(req)
        self.audit.record("approval_decision", tool=tool, approved=result.approved, note=result.note)
        if result.approved and tool in WEB_FINAL_TOOLS and tool != "mcp__chunai__unggah_berkas" and self.on_final_approved:
            try:
                await self.on_final_approved(tool, tool_input)
            except Exception:
                pass
        if result.approved and tool in (WEB_OPEN_TOOL, DOWNLOAD_TOOL):
            host = (urlparse(str((result.updated_input or tool_input).get("url", ""))).hostname or "").lower()
            host = host[4:] if host.startswith("www.") else host
            if host:
                self.allowed_domains.add(host)
                self.audit.record("domain_allowed", host=host, permanent=result.note == "always")
                if self.on_domain:
                    self.on_domain(host, result.note == "always")
        elif result.approved and result.note == "always" and tool not in WEB_FINAL_TOOLS:
            self.auto_approve.add(tool)
        return result
