"""Orkestrator ChunAI di atas Claude Agent SDK, dengan Approval Gate."""
from __future__ import annotations

from pathlib import Path
from typing import AsyncIterator

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher, PermissionResultAllow,
    PermissionResultDeny, ResultMessage, TextBlock, ToolUseBlock,
)

from .agents import SUBAGENTS
from .approval import ApprovalGate, Reviewer
from .audit import AuditLog
from .browser import WebConfig, WebSession
from .prompts import SYSTEM_PROMPT
from .timeutil import describe
from .tools import build_server


class ChunAI:
    def __init__(self, reviewer: Reviewer, workdir: str | Path = "data/workspace",
                 audit_path: str | Path = "data/audit.jsonl", model: str | None = None,
                 max_budget_usd: float | None = 5.0, web: WebConfig | None = None):
        self.workdir = Path(workdir).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(audit_path)
        self.gate = ApprovalGate(reviewer=reviewer, audit=self.audit)
        self.web = WebSession(web, self.workdir) if web else None
        if web:
            self.gate.allowed_domains = set(web.allowed_domains)
            self.gate.on_domain = self._domain_added
            self.gate.previewers = {
                "mcp__chunai__buka_halaman": self._preview_open,
                "mcp__chunai__klik": lambda i: self.web.describe(int(i["index"])),
                "mcp__chunai__kirim_form": self._preview_submit,
            }
        self.fetch_log: dict[str, str] = {}   # url -> "ok" | "gagal" (dari hook WebFetch; dipakai pemeriksa sumber)
        self.outbox: list[Path] = []          # file yang diminta agen (kirim_file) untuk dikirim ke pengguna
        self.model = model
        self.max_budget_usd = max_budget_usd
        self._client: ClaudeSDKClient | None = None

    async def _preview_open(self, tool_input: dict) -> str:
        from urllib.parse import urlparse
        host = urlparse(str(tool_input.get("url", ""))).hostname or "?"
        return (f"SITUS BARU: {host}\nSetuju = izinkan situs ini untuk sesi ini. ♾ Selalu = simpan permanen (tidak ditanya lagi).\n"
                "Mengisi dan mengirim form di situs ini tetap selalu meminta izin Anda.")

    def _domain_added(self, host: str, permanent: bool):
        self.web.cfg.allowed_domains.add(host)
        if permanent:
            f = Path(self.web.cfg.allowlist_file)
            try:
                f.parent.mkdir(parents=True, exist_ok=True)
                old = f.read_text(encoding="utf-8") if f.exists() else ""
                if host not in {l.strip().lower() for l in old.splitlines()}:
                    with f.open("a", encoding="utf-8") as fh:
                        fh.write(("" if not old or old.endswith("\n") else "\n") + host + "\n")
            except OSError:
                pass

    async def _preview_submit(self, tool_input: dict) -> str:
        return f"{await self.web.describe(int(tool_input['index']))}\n{await self.web.review()}"

    async def _can_use_tool(self, tool_name, tool_input, context):
        result = await self.gate.check(tool_name, tool_input)
        if result.approved:
            return PermissionResultAllow(updated_input=result.updated_input)
        return PermissionResultDeny(message=result.note or "Ditolak oleh pengguna.")

    async def _pre_tool_hook(self, input_data, tool_use_id, context):
        """Gate untuk SEMUA tool, termasuk yang biasanya disetujui otomatis oleh CLI."""
        result = await self.gate.check(input_data["tool_name"], input_data.get("tool_input", {}))
        out = {"hookEventName": "PreToolUse"}
        if result.approved:
            out["permissionDecision"] = "allow"
            new_input = dict(result.updated_input or input_data.get("tool_input", {}))
            if input_data["tool_name"] in ("Agent", "Task"):
                new_input["run_in_background"] = False  # tunggu hasil subagen dalam giliran yang sama
            if new_input != input_data.get("tool_input", {}):
                out["updatedInput"] = new_input
        else:
            out["permissionDecision"] = "deny"
            out["permissionDecisionReason"] = result.note or "Ditolak oleh pengguna."
        return {"hookSpecificOutput": out}

    async def _post_fetch_hook(self, input_data, tool_use_id, context):
        url = str((input_data.get("tool_input") or {}).get("url", ""))
        if url:
            self.fetch_log[url] = "ok"
            self.audit.record("source_opened", url=url[:200])
        return {}

    async def _post_fetch_fail_hook(self, input_data, tool_use_id, context):
        url = str((input_data.get("tool_input") or {}).get("url", ""))
        if url:
            self.fetch_log[url] = "gagal"
            self.audit.record("source_failed", url=url[:200], error=str(input_data.get("error", ""))[:120])
        return {}

    def _options(self) -> ClaudeAgentOptions:
        return ClaudeAgentOptions(
            system_prompt=SYSTEM_PROMPT,
            agents=SUBAGENTS,
            cwd=str(self.workdir),
            mcp_servers={"chunai": build_server(self.workdir, self.web, self.outbox, self.fetch_log)},
            hooks={"PreToolUse": [HookMatcher(hooks=[self._pre_tool_hook])],
                   "PostToolUse": [HookMatcher(matcher="WebFetch", hooks=[self._post_fetch_hook])],
                   "PostToolUseFailure": [HookMatcher(matcher="WebFetch", hooks=[self._post_fetch_fail_hook])]},
            can_use_tool=self._can_use_tool,
            permission_mode="default",
            model=self.model,
            max_budget_usd=self.max_budget_usd,
        )

    async def __aenter__(self):
        self._client = ClaudeSDKClient(self._options())
        await self._client.connect()
        return self

    async def __aexit__(self, *exc):
        if self._client:
            await self._client.disconnect()
        if self.web:
            await self.web.close()

    async def interrupt(self):
        """Hentikan giliran yang sedang berjalan."""
        if self._client:
            await self._client.interrupt()

    async def ask(self, prompt: str) -> AsyncIterator[str]:
        """Kirim perintah, hasilkan potongan teks balasan."""
        assert self._client, "Gunakan 'async with ChunAI(...)'"
        self.audit.record("user_prompt", prompt=prompt)
        await self._client.query(f"[Konteks waktu: {describe()}]\n{prompt}")
        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        yield block.text
                    elif isinstance(block, ToolUseBlock):
                        extra = {"path": str(block.input.get("path", ""))[:200]} if block.name.endswith("kirim_file") else \
                            {"query": str(block.input.get("query", ""))[:120]} if block.name == "WebSearch" else {}
                        self.audit.record("tool_use", tool=block.name, **extra)
            elif isinstance(msg, ResultMessage):
                self.audit.record("turn_done", cost_usd=getattr(msg, "total_cost_usd", None))
