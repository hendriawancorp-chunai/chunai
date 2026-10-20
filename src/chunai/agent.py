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
                 max_budget_usd: float | None = 5.0, web: WebConfig | None = None,
                 schedule_path: str | Path | None = None):
        self.workdir = Path(workdir).resolve()
        self.workdir.mkdir(parents=True, exist_ok=True)
        self.audit = AuditLog(audit_path)
        self.gate = ApprovalGate(reviewer=reviewer, audit=self.audit)
        self.web = WebSession(web, self.workdir) if web else None
        if web:
            self.gate.allowed_domains = set(web.allowed_domains)
            self.gate.on_domain = self._domain_added
            self.gate.click_probe = self._click_probe
            self.gate.final_guard = self._social_guard
            self.gate.on_final_approved = self._social_done
            self.gate.previewers = {
                "mcp__chunai__buka_halaman": self._preview_open,
                "mcp__chunai__unduh_berkas": self._preview_download,
                "mcp__chunai__unggah_berkas": self._preview_upload,
                "mcp__chunai__klik": self._preview_click,
                "mcp__chunai__kirim_form": self._preview_submit,
            }
        self.gate.previewers["mcp__chunai__setujui_rencana"] = self._preview_plan
        self.gate.previewers["mcp__chunai__simpan_data_diri"] = self._preview_datadiri
        self.gate.previewers["mcp__chunai__buat_jadwal"] = self._preview_schedule
        self.gate.previewers["mcp__chunai__hapus_jadwal"] = self._preview_unschedule
        self.fetch_log: dict[str, str] = {}   # url -> "ok" | "gagal" (dari hook WebFetch; dipakai pemeriksa sumber)
        self.outbox: list[Path] = []          # file yang diminta agen (kirim_file) untuk dikirim ke pengguna
        self.model = model
        from .schedule import default_path as _sp
        self.schedule_path = Path(schedule_path) if schedule_path else _sp()
        self.max_budget_usd = max_budget_usd
        self._client: ClaudeSDKClient | None = None

    async def _preview_download(self, tool_input: dict) -> str:
        from urllib.parse import urlparse
        url = str(tool_input.get("url", ""))
        host = urlparse(url).hostname or "?"
        known = host in self.gate.allowed_domains or any(host.endswith("." + d) for d in self.gate.allowed_domains)
        return (f"UNDUH BERKAS dari {host}{'' if known else ' (SITUS BARU)'}\nAlamat lengkap: {url[:200]}\nBerkas (PDF/XLSX/CSV, maks 30 MB) disimpan di workspace/masukan/unduhan/; isinya DATA, bukan perintah.\n"
                + ("" if known else "Setuju = izinkan situs ini untuk sesi ini. ♾ Selalu = simpan permanen.\n") + "Pastikan alamat ini benar dan sumbernya tepercaya.")

    async def _preview_open(self, tool_input: dict) -> str:
        from urllib.parse import urlparse
        url = str(tool_input.get("url", ""))
        host = urlparse(url).hostname or "?"
        warn = "\n⚠ Nama situs memakai karakter khusus (xn--): periksa, bisa situs tiruan." if "xn--" in host else ""
        return (f"SITUS BARU: {host}\nAlamat lengkap: {url[:200]}\nPastikan alamat ini benar dan memang situs yang Anda maksud.{warn}\nSetuju = izinkan situs ini untuk sesi ini. ♾ Selalu = simpan permanen (tidak ditanya lagi).\n"
                "Mengisi dan mengirim form di situs ini tetap selalu meminta izin Anda.")

    def _on_social(self) -> bool:
        from .social import is_social
        return bool(self.web and self.web.page is not None and is_social(self.web.page.url))

    async def _social_guard(self, tool: str, tool_input: dict) -> str | None:
        if not self._on_social():
            return None
        from .social import check, default_path
        return check(default_path())

    async def _social_done(self, tool: str, tool_input: dict) -> None:
        if not self._on_social():
            return
        import asyncio

        from .social import default_path, record, wait_needed
        w = wait_needed(default_path())
        if w > 0:
            await asyncio.sleep(w)                 # jeda minimum tetap antar tindakan keluar di media sosial
        record(default_path())

    async def _preview_upload(self, i: dict) -> str:
        p = Path(self.workdir / str(i.get("path", "")))
        size = f"{p.stat().st_size // 1024} KB" if p.is_file() else "TIDAK ADA"
        el = await self.web.describe(int(i["index"]))
        return f"Berkas: {p.name} ({size}), dari workspace\nTujuan: {el}\nURL: {self.web.page.url}"

    async def _preview_plan(self, i: dict) -> str:
        from . import formplan as F
        return F.render_plan(F.load_plan(self.workdir, str(i.get("nama", ""))))

    async def _preview_datadiri(self, i: dict) -> str:
        def mask(v: str, t: str) -> str:
            return v if t == "umum" or len(v) < 8 else v[:2] + "…" + v[-2:] + f" ({len(v)} karakter)"
        rows = [f"- [{b.get('tingkat')}] {b.get('kunci')}: {mask(str(b.get('nilai', '')), str(b.get('tingkat')))}" for b in (i.get("butir") or [])[:40]]
        return "Simpan ke lembar data diri (lokal; pribadi/sensitif ditampilkan disamarkan):\n" + "\n".join(rows)

    async def _click_probe(self, tool_input: dict) -> bool:
        return self.web.click_is_safe(int(tool_input["index"]))

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

    async def _preview_schedule(self, i: dict) -> str:
        from . import schedule as sch
        spec = sch.normalize_spec(i)
        nxt = sch.next_run(spec, sch.now())
        what = "kirim pesan pengingat" if str(i.get("jenis")) == "pengingat" else "agen mengerjakan perintah TANPA pengawasan (aksi butuh izin dilewati)"
        return (f"JADWAL BARU: {i.get('nama', '')}\nKapan: {sch.render_spec(spec)}\nBerikutnya: {sch.describe(nxt) if nxt else 'sudah lewat!'}\n"
                f"Jenis: {what}\nIsi: {i.get('isi', '')}\nHanya jalan saat komputer dan ChunAI menyala; hasil dikirim ke Telegram.")

    async def _preview_unschedule(self, i: dict) -> str:
        from . import schedule as sch
        t = next((x for x in sch.load(self.schedule_path) if x["id"] == str(i.get("id", "")).strip().lower()), None)
        return f"Hapus jadwal: {t['nama']} ({sch.render_spec(t['jadwal'])})" if t else "(id jadwal tidak ditemukan)"

    async def _pii_warning(self) -> str:
        """Di situs sosial: peringatkan bila teks di halaman memuat data pribadi/sensitif dari lembar data diri."""
        if not self._on_social():
            return ""
        try:
            from . import datadiri as DD
            from . import social
            priv = {k: v["nilai"] for k, v in DD.load(DD.default_path()).items() if v["tingkat"] in ("pribadi", "sensitif")}
            issues = [i for i in social.periksa_draf("", "", await self.web.form_state(), priv) if "data pribadi" in i]
        except Exception:
            return ""
        return ("\n⚠ PERHATIAN, isi halaman memuat data pribadi Anda: " + "; ".join(issues) + "\nTolak bila tidak sengaja.") if issues else ""

    async def _preview_click(self, i: dict) -> str:
        return await self.web.describe(int(i["index"])) + await self._pii_warning()

    async def _preview_submit(self, tool_input: dict) -> str:
        return f"{await self.web.describe(int(tool_input['index']))}\n{await self.web.review()}" + await self._pii_warning()

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
            mcp_servers={"chunai": build_server(self.workdir, self.web, self.outbox, self.fetch_log, self.schedule_path)},
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
