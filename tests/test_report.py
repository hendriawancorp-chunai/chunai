from chunai.report import lint_report

GOOD = """# Judul
## Temuan
MCP dirilis pada November 2024 [1]. Spesifikasi memakai JSON-RPC 2.0 [2].
## Sumber
1. Pengumuman MCP — https://www.anthropic.com/news/model-context-protocol (diakses 2026-10-15)
2. Spesifikasi — https://modelcontextprotocol.io/specification (diakses 2026-10-15)
## Catatan keterbatasan
Satu halaman gagal dibuka.
"""


def test_good_report_passes():
    assert lint_report(GOOD) == []


def test_missing_sources():
    assert "Tidak ada bagian '## Sumber'." in lint_report("# x\n## Temuan\nhalo 2024")


def test_uncited_numeric_claim():
    bad = GOOD.replace("MCP dirilis pada November 2024 [1]. Spesifikasi memakai JSON-RPC 2.0 [2].",
                       "MCP dirilis pada November 2024.")
    assert any("tanpa sitasi" in i for i in lint_report(bad))


def test_dangling_citation():
    bad = GOOD.replace("[2]", "[9]")
    assert any("[9]" in i for i in lint_report(bad))


def test_source_without_url_and_no_notes():
    bad = GOOD.replace(" — https://www.anthropic.com/news/model-context-protocol", "")
    bad = bad.replace("## Catatan keterbatasan\nSatu halaman gagal dibuka.\n", "")
    issues = lint_report(bad)
    assert any("tidak punya URL" in i for i in issues)
    assert any("Catatan" in i for i in issues)
