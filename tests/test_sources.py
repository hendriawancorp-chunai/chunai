from chunai.office.doccheck import attention_text, reference_urls, source_attention

SPEC = {"references": ["Anthropic. (2024). Pengumuman. https://www.anthropic.com/news/model-context-protocol",
                       "MCP. (2025). Arsitektur. https://modelcontextprotocol.io/docs/learn/architecture",
                       "Pengguna. (2026). Survei. https://contoh.example/survei"]}


def test_reference_urls():
    assert len(reference_urls(SPEC)) == 3


def test_none_log_means_no_tracking():
    assert source_attention(SPEC, None) == []


def test_opened_failed_and_never_opened_are_distinguished():
    log = {"https://www.anthropic.com/news/model-context-protocol": "ok",
           "https://modelcontextprotocol.io/docs/learn/architecture": "gagal"}
    notes = source_attention(SPEC, log)
    assert any("GAGAL dibuka: https://modelcontextprotocol.io" in n for n in notes)
    assert any("tidak pernah dibuka: https://contoh.example" in n for n in notes)
    assert not any("anthropic.com" in n for n in notes)


def test_url_matching_ignores_scheme_www_trailing_slash_and_fragment():
    log = {"http://anthropic.com/news/model-context-protocol/#intro": "ok"}
    assert not any("anthropic.com" in n for n in source_attention(SPEC, log))


def test_attention_text_gives_actionable_rule():
    t = attention_text(["Sumber GAGAL dibuka: https://x.example"])
    assert "PERHATIAN SUMBER" in t and "belum terverifikasi" in t and "Keterbatasan" in t
    assert attention_text([]) == ""


async def test_agent_hooks_record_fetch_results(tmp_path):
    from chunai.agent import ChunAI
    from chunai.approval import ApprovalResult

    async def rev(r): return ApprovalResult(False)
    a = ChunAI(rev, workdir=tmp_path / "w", audit_path=tmp_path / "a.jsonl")
    await a._post_fetch_hook({"tool_input": {"url": "https://ok.example/a"}}, "1", None)
    await a._post_fetch_fail_hook({"tool_input": {"url": "https://gagal.example/b"}, "error": "ENOTFOUND"}, "2", None)
    assert a.fetch_log == {"https://ok.example/a": "ok", "https://gagal.example/b": "gagal"}
    ev = [e["event"] for e in a.audit.read()]
    assert ev == ["source_opened", "source_failed"]


def test_reference_objects_are_normalised_to_apa_strings():
    from chunai.office.doccheck import lint_doc_spec, normalize_spec, reference_to_text
    r = {"authors": ["Anthropic"], "year": 2024, "title": "Introducing the Model Context Protocol",
         "source": "Anthropic", "url": "https://www.anthropic.com/news/model-context-protocol"}
    assert reference_to_text(r) == ("Anthropic. (2024). Introducing the Model Context Protocol. Anthropic. "
                                    "https://www.anthropic.com/news/model-context-protocol")
    spec = normalize_spec({"blocks": [{"p": "MCP dirilis pada 2024 (Anthropic, 2024)."}], "references": [r, "Teks, A. (2020). Biasa. https://x.example"]})
    assert all(isinstance(x, str) for x in spec["references"])
    assert not any("tidak ada di Daftar Pustaka" in i for i in lint_doc_spec(spec))


def test_docx_builds_even_when_agent_passes_reference_objects(tmp_path):
    from pathlib import Path

    from docx import Document

    from chunai.office.docbuild import build_docx
    from chunai.office.doccheck import normalize_spec
    from chunai.office.theme import Theme
    spec = normalize_spec({"title": "T", "blocks": [{"p": "x"}], "references": [{"author": "Budi", "year": 2025, "title": "Judul", "url": "https://a.example"}]})
    d = Document(str(build_docx(spec, tmp_path / "a.docx", Theme(), Path("."))))
    assert any("Budi. (2025). Judul." in p.text for p in d.paragraphs)
