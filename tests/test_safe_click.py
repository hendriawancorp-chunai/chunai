from chunai.approval import ApprovalGate, ApprovalResult
from chunai.audit import AuditLog
from chunai.policy import click_is_safe

KLIK = "mcp__chunai__klik"


def el(tag, label="", type="", role="", href=""):
    return {"tag": tag, "type": type, "role": role, "label": label, "href": href}


def test_safe_navigation_and_choices():
    assert click_is_safe(el("input", "A. Puas", type="radio"))
    assert click_is_safe(el("input", "Saya setuju", type="checkbox")) is False      # kata "setuju" = pernyataan, tetap tanya
    assert click_is_safe(el("input", "Newsletter", type="checkbox"))
    assert click_is_safe(el("div", "Unit A", role="option"))
    assert click_is_safe(el("a", "Bantuan", href="https://x.example/help"))
    for t in ("Lanjut", "Next", "Berikutnya", "Sebelumnya", "Kembali", "Lanjut ke Langkah 2", "Next step"):
        assert click_is_safe(el("button", t, type="submit")), t


def test_final_or_unknown_clicks_still_ask():
    for t in ("Kirim Formulir", "Submit", "Selesai", "Bayar sekarang", "Hapus kuis", "Simpan", "Keluar", "Log out", "Publish", "Kumpulkan", "Mulai", "Lanjut ke pembayaran", "Continue to checkout"):
        assert not click_is_safe(el("button", t, type="submit")), t
    assert not click_is_safe(el("a", "Hapus akun", href="https://x.example/delete"))
    assert not click_is_safe(el("a", "x", href="javascript:alert(1)"))
    assert not click_is_safe(el("div", "klik", role="switch"))
    assert not click_is_safe(el("span", "apa saja"))


async def _gate(tmp_path, safe):
    asked = []

    async def reviewer(req):
        asked.append(req.tool)
        return ApprovalResult(True)

    async def probe(i):
        if safe is None:
            raise RuntimeError("elemen hilang")
        return safe
    g = ApprovalGate(reviewer=reviewer, audit=AuditLog(tmp_path / "a.jsonl"))
    g.click_probe = probe
    return g, asked


async def test_gate_skips_card_only_for_safe_click(tmp_path):
    g, asked = await _gate(tmp_path, True)
    assert (await g.check(KLIK, {"index": 1})).approved and asked == []
    g, asked = await _gate(tmp_path, False)
    await g.check(KLIK, {"index": 1})
    assert asked == [KLIK]


async def test_probe_error_fails_closed_and_submit_form_always_asks(tmp_path):
    g, asked = await _gate(tmp_path, None)
    await g.check(KLIK, {"index": 1})
    assert asked == [KLIK]
    g, asked = await _gate(tmp_path, True)
    await g.check("mcp__chunai__kirim_form", {"index": 2})
    assert asked == ["mcp__chunai__kirim_form"]
