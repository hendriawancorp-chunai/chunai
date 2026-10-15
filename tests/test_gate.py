import pytest
from chunai.approval import ApprovalGate, ApprovalResult
from chunai.audit import AuditLog
from chunai.policy import Decision, classify


def test_policy_read_auto():
    assert classify("WebSearch") is Decision.AUTO
    assert classify("Read", {"file_path": "x"}) is Decision.AUTO


def test_policy_write_ask():
    assert classify("Write") is Decision.ASK
    assert classify("Bash", {"command": "python x.py"}) is Decision.ASK


def test_policy_unknown_fail_safe():
    assert classify("SomethingNew") is Decision.ASK
    assert classify("mcp__x__mystery") is Decision.ASK


def test_policy_mcp_browser():
    assert classify("mcp__browser__submit_form") is Decision.ASK
    assert classify("mcp__browser__click") is Decision.ASK
    assert classify("mcp__browser__get_page_text") is Decision.AUTO


def test_policy_deny_dangerous_bash():
    assert classify("Bash", {"command": "rm -rf /"}) is Decision.DENY


def make_gate(tmp_path, approve, note=""):
    calls = []

    async def reviewer(req):
        calls.append(req)
        return ApprovalResult(approve, note)

    return ApprovalGate(reviewer, AuditLog(tmp_path / "a.jsonl")), calls


async def test_read_does_not_ask(tmp_path):
    gate, calls = make_gate(tmp_path, False)
    assert (await gate.check("WebSearch", {"query": "x"})).approved
    assert calls == []


async def test_write_asks_and_rejection_blocks(tmp_path):
    gate, calls = make_gate(tmp_path, False, "jangan")
    r = await gate.check("Write", {"file_path": "a"})
    assert not r.approved and len(calls) == 1


async def test_deny_never_reaches_reviewer(tmp_path):
    gate, calls = make_gate(tmp_path, True)
    r = await gate.check("Bash", {"command": "rm -rf /"})
    assert not r.approved and calls == []


async def test_always_remembers(tmp_path):
    gate, calls = make_gate(tmp_path, True, "always")
    await gate.check("Write", {})
    await gate.check("Write", {})
    assert len(calls) == 1


async def test_audit_trail(tmp_path):
    gate, _ = make_gate(tmp_path, True)
    await gate.check("Write", {"file_path": "a"})
    events = [e["event"] for e in gate.audit.read()]
    assert events == ["approval_requested", "approval_decision"]


def test_chunai_tool_and_toolsearch_auto():
    assert classify("mcp__chunai__periksa_laporan") is Decision.AUTO
    assert classify("ToolSearch") is Decision.AUTO


def test_safe_readonly_bash_auto():
    from chunai.policy import is_safe_readonly_bash
    ok = ["ls -la masukan && head -5 masukan/penjualan.csv && wc -l masukan/penjualan.csv", "ls | wc -l",
          "cat output/a.md", "tail -n 20 masukan/x.csv", "pwd", "ls masukan/*.csv"]
    for c in ok:
        assert is_safe_readonly_bash(c), c
        assert classify("Bash", {"command": c}) is Decision.AUTO


def test_unsafe_bash_still_asks_or_denied():
    bad = ["cat /etc/passwd", "cat ../x", "ls; rm x", "head $(whoami)", "ls > a", "tail -f a", "cat a | sh",
           "ls && curl http://x", "cat ~/.ssh/id_rsa", "ls `id`", "head -n 5 a >> b", "python x.py", "ls -la /", "rm -rf x",
           "cat a || echo", "head -c 1 a\nrm b", ""]
    for c in bad:
        assert classify("Bash", {"command": c}) is not Decision.AUTO, c
    assert classify("Bash", {"command": "rm -rf /"}) is Decision.DENY
