from chunai.approval import ApprovalGate, ApprovalResult
from chunai.audit import AuditLog
from chunai.policy import Decision, classify, is_public_host

OPEN = "mcp__chunai__buka_halaman"


def test_public_vs_private_hosts():
    for u in ("https://wayground.com/x", "https://app.example.co.id", "http://8.8.8.8"):
        assert is_public_host(u), u
    for u in ("http://localhost:8080", "http://127.0.0.1", "http://192.168.1.1", "http://10.0.0.5", "http://169.254.169.254/latest",
              "http://router", "http://nas.local", "http://[::1]/", "file:///etc/passwd", "javascript:alert(1)"):
        assert not is_public_host(u), u


def test_classify_open_new_site():
    assert classify(OPEN, {"url": "https://wayground.com"}, set()) is Decision.ASK
    assert classify(OPEN, {"url": "http://169.254.169.254/"}, set()) is Decision.DENY
    assert classify(OPEN, {"url": "http://localhost:3000"}, set()) is Decision.DENY
    assert classify(OPEN, {"url": "https://wayground.com/admin"}, {"wayground.com"}) is Decision.AUTO
    assert classify(OPEN, {"url": "http://127.0.0.1:5000"}, {"127.0.0.1"}) is Decision.AUTO      # eksplisit di allowlist


async def _gate(tmp_path, note):
    asked, added = [], []

    async def reviewer(req):
        asked.append(req.tool)
        return ApprovalResult(True, note)
    g = ApprovalGate(reviewer=reviewer, audit=AuditLog(tmp_path / "a.jsonl"))
    g.on_domain = lambda h, p: added.append((h, p))
    return g, asked, added


async def test_once_approval_allows_domain_for_session_only(tmp_path):
    g, asked, added = await _gate(tmp_path, "")
    await g.check(OPEN, {"url": "https://www.wayground.com/a"})
    assert added == [("wayground.com", False)] and "wayground.com" in g.allowed_domains
    await g.check(OPEN, {"url": "https://wayground.com/b"})
    assert len(asked) == 1                                    # situs yang sama tidak ditanya lagi
    await g.check(OPEN, {"url": "https://lain.example"})
    assert len(asked) == 2


async def test_always_is_per_domain_not_per_tool(tmp_path):
    g, asked, added = await _gate(tmp_path, "always")
    await g.check(OPEN, {"url": "https://a.example"})
    assert added == [("a.example", True)]
    await g.check(OPEN, {"url": "https://b.example"})
    assert len(asked) == 2 and OPEN not in g.auto_approve     # "selalu" TIDAK membuka semua situs


async def test_denied_open_adds_nothing(tmp_path):
    async def reviewer(req):
        return ApprovalResult(False, "tidak")
    g = ApprovalGate(reviewer=reviewer, audit=AuditLog(tmp_path / "a.jsonl"))
    r = await g.check(OPEN, {"url": "https://x.example"})
    assert not r.approved and not g.allowed_domains


def test_agent_persists_permanent_domain(tmp_path):
    from chunai.agent import ChunAI
    from chunai.browser import WebConfig
    f = tmp_path / "allow.txt"
    f.write_text("# komentar\nlama.example")
    a = ChunAI(None, workdir=tmp_path / "ws", audit_path=tmp_path / "au.jsonl", web=WebConfig(allowlist_file=str(f)))
    a._domain_added("baru.example", True)
    a._domain_added("baru.example", True)
    a._domain_added("sesi.example", False)
    assert f.read_text().splitlines() == ["# komentar", "lama.example", "baru.example"]
    assert {"baru.example", "sesi.example"} <= a.web.cfg.allowed_domains
