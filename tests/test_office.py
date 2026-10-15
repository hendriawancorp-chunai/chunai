import json
from pathlib import Path

import pytest
from docx import Document
from pptx import Presentation

from chunai.office.deckbuild import build_pptx, fit_size
from chunai.office.docbuild import build_docx
from chunai.office.doccheck import lint_doc_spec
from chunai.office.theme import Theme, load_theme

EX = Path(__file__).parent.parent / "examples"
DOC = json.loads((EX / "contoh_artikel.json").read_text())
DECK = json.loads((EX / "contoh_deck.json").read_text())


def test_example_doc_passes_lint():
    assert lint_doc_spec(DOC) == []


def test_lint_catches_problems():
    bad = json.loads(json.dumps(DOC))
    bad["blocks"].append({"p": "Pendapatan tumbuh 11 persen dan mencapai Rp4 triliun pada tahun lalu menurut data internal."})
    bad["blocks"].append({"p": "Klaim lain (Tidakada, 2020)."})
    bad["blocks"].append({"table": {"header": ["a"], "rows": [["x"]]}})
    issues = "\n".join(lint_doc_spec(bad))
    assert "tanpa sitasi" in issues and "Tidakada" in issues and "tanpa keterangan" in issues


def test_docx_structure(tmp_path):
    out = build_docx(DOC, tmp_path / "a.docx", Theme(), Path("."))
    d = Document(str(out))
    heads = [p.text for p in d.paragraphs if p.style.name.startswith("Heading")]
    assert heads[0].startswith("1.") and any(h.startswith("2.2.1.") for h in heads)
    assert any(p.text.startswith("Tabel 1.") for p in d.paragraphs)
    assert len(d.tables) == 1 and d.tables[0].rows[0].cells[0].text == "Dimensi"


def test_pptx_structure_and_native_chart(tmp_path):
    out, warns = build_pptx(DECK, tmp_path / "d.pptx", Theme(), Path("."))
    prs = Presentation(str(out))
    assert len(prs.slides) == len(DECK["slides"])
    assert any(sh.has_chart for sl in prs.slides for sh in sl.shapes)       # chart bisa diedit
    assert any(sh.has_table for sl in prs.slides for sh in sl.shapes)


def test_unknown_slide_kind_rejected(tmp_path):
    with pytest.raises(ValueError, match="tidak dikenal"):
        build_pptx({"slides": [{"kind": "ngawur"}]}, tmp_path / "x.pptx", Theme(), Path("."))


def test_fit_size_shrinks_long_text():
    assert fit_size("kata " * 200, 3, 1, 20) < 20
    assert fit_size("pendek", 5, 1, 20) == 20


def test_custom_theme_loads(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"primary": "AA0000", "font_slide": "Poppins", "bukan_field": 1}))
    t = load_theme("x", tmp_path)
    assert t.primary == "AA0000" and t.font_slide == "Poppins"
    with pytest.raises(FileNotFoundError):
        load_theme("tidak-ada", tmp_path)


def test_ringkasan_and_penutup_adapt_without_optional_parts(tmp_path):
    spec = {"slides": [
        {"kind": "ringkasan", "title": "R", "cards": [{"h": "A", "t": "x"}, {"h": "B", "t": "y"}]},
        {"kind": "penutup", "title": "P", "bullets": ["satu", "dua"]}]}
    out, _ = build_pptx(spec, tmp_path / "s.pptx", Theme(), Path("."))
    prs = Presentation(str(out))
    widest = max(sh.width for sh in prs.slides[0].shapes if sh.shape_type == 1)       # kartu melebar penuh
    assert widest > 11_000_000
    assert len(prs.slides) == 2


def test_unknown_theme_error_lists_available(tmp_path):
    (tmp_path / "asdp.json").write_text("{}")
    with pytest.raises(FileNotFoundError, match="asdp"):
        load_theme("biru", tmp_path)
