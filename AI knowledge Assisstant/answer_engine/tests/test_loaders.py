"""Run from "AI knowledge Assisstant/": python -m pytest answer_engine/tests -q"""
import hashlib
from pathlib import Path

import pytest

from answer_engine.loaders import SUPPORTED_EXTENSIONS, TABLE_HEADER_EVERY, ScannedPDFError, load_file

FIXTURES = Path(__file__).parent / "fixtures"
KNOWLEDGE_BASE = Path(__file__).parents[2] / "knowledge-base"


def load(name: str):
    return load_file(FIXTURES / name, name)


def paths(doc) -> list[str]:
    return [" > ".join(s.heading_path) for s in doc.sections]


def test_supported_extensions():
    assert {".md", ".txt", ".pdf", ".docx", ".xlsx", ".csv", ".html"} <= SUPPORTED_EXTENSIONS


def test_unknown_extension_lists_supported_types(tmp_path):
    path = tmp_path / "slides.pptx"
    path.write_bytes(b"x")
    with pytest.raises(ValueError) as error:
        load_file(path, "slides.pptx")
    assert ".pdf" in str(error.value) and ".docx" in str(error.value)


@pytest.mark.parametrize("name", ["sample.md", "sample.docx", "headings.pdf", "sample.xlsx"])
def test_common_fields(name):
    doc = load(name)
    assert doc.doc_id == name
    assert doc.source == name
    assert doc.content_hash == hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest()
    assert doc.metadata["file_name"] == name
    assert doc.sections and all(s.text.strip() for s in doc.sections)


def test_markdown_structure():
    doc = load("sample.md")
    assert doc.file_type == "md"
    assert doc.title == "Policy Handbook: Travel Policy"  # empty label heading joined with the next one
    root = "Policy Handbook: Travel Policy"
    assert paths(doc) == [
        root,
        f"{root} > Booking",
        f"{root} > Booking > Approval",
        f"{root} > Booking > Approval",
        f"{root} > Booking > Approval",
        f"{root} > Expenses",  # setext heading
    ]
    assert "# this is a comment, not a heading" in doc.sections[1].text  # code fences are not headings
    table = doc.sections[3]
    assert table.kind == "table" and table.text.startswith("| Grade | Daily limit |")
    assert doc.sections[4].text == "Text after the table."


def test_label_heading_only_joins_when_empty(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("# Part One\n\nSome text.\n\n# Part Two\n\nMore text.\n", encoding="utf-8")
    doc = load_file(path, "doc.md")
    assert doc.title == "Part One"
    assert paths(doc) == ["Part One", "Part Two"]


def test_text_file():
    doc = load("sample.txt")
    assert doc.file_type == "txt"
    assert doc.title == "sample"
    assert len(doc.sections) == 1 and doc.sections[0].heading_path == []
    assert "\n\n\n" not in doc.sections[0].text


def test_html_structure():
    doc = load("sample.html")
    assert doc.file_type == "html"
    assert doc.title == "Product Guide"
    assert paths(doc) == ["Product Guide", "Product Guide > Plans", "Product Guide > Plans", "Product Guide > Plans > Discounts"]
    assert doc.sections[0].text == "Welcome to the guide."
    assert doc.sections[1].text == "- Basic\n- Pro\n- Pro Plus"
    table = doc.sections[2]
    assert table.kind == "table"
    assert "| Pro | $20 \\| month |" in table.text  # pipes inside cells are escaped
    all_text = " ".join(s.text for s in doc.sections)
    assert "do not index" not in all_text and "Home | About" not in all_text


def test_html_falls_back_to_title_tag(tmp_path):
    path = tmp_path / "page.html"
    path.write_text("<html><head><title>Only Title</title></head><body><p>Body.</p></body></html>", encoding="utf-8")
    assert load_file(path, "page.html").title == "Only Title"


def test_docx_structure():
    doc = load("sample.docx")
    assert doc.file_type == "docx"
    assert doc.title == "Employee Guide"  # first heading wins over the core-properties title
    assert paths(doc) == [
        "Employee Guide",
        "Employee Guide > Leave",
        "Employee Guide > Leave > Sick Leave",
        "Employee Guide > Leave > Sick Leave",
        "Employee Guide > Benefits",
    ]
    assert "- Carry over up to 5 days" in doc.sections[1].text
    assert doc.sections[3].kind == "table"
    assert doc.sections[3].text == "| Years | Days |\n|---|---|\n| 0-2 | 25 |\n| 3+ | 28 |"


def test_pdf_detects_headings():
    doc = load("headings.pdf")
    assert doc.file_type == "pdf"
    assert doc.title == "Annual Report"
    assert doc.metadata["pages"] == 2
    assert paths(doc) == ["Annual Report > Revenue", "Annual Report > Revenue > Regional Detail", "Annual Report > Costs"]
    assert "grew by 12 percent" in doc.sections[0].text


def test_pdf_without_headings_uses_pages():
    doc = load("plain.pdf")
    assert doc.title == "plain"
    assert paths(doc) == ["Page 1", "Page 2"]


def test_scanned_pdf_raises_clear_error():
    with pytest.raises(ScannedPDFError, match="OCR"):
        load("scanned.pdf")


def test_xlsx_one_table_per_sheet():
    doc = load("sample.xlsx")
    assert doc.file_type == "xlsx"
    assert doc.title == "Quarterly Report"
    assert paths(doc) == ["Sales", "Staff"]  # the empty sheet is skipped
    assert all(s.kind == "table" for s in doc.sections)
    sales = doc.sections[0].text
    assert "| R0 | 2025-01-01 | 1000 |" in sales  # dates and whole numbers are rendered cleanly
    assert doc.sections[1].text == "| Name | Role |\n|---|---|\n| Ana | Engineer |"  # empty trailing column dropped


def test_big_tables_repeat_header():
    for name, header in [("sample.xlsx", "| Region | Month | Revenue |"), ("sample.csv", "| id | name | amount |")]:
        blocks = load(name).sections[0].text.split("\n\n")
        assert len(blocks) == 3  # 70 / 65 body rows
        for block in blocks:
            lines = block.splitlines()
            assert lines[0] == header and lines[1].startswith("|---")
            assert len(lines) - 2 <= TABLE_HEADER_EVERY


def test_csv_detects_delimiter():
    doc = load("semicolon.csv")
    assert doc.file_type == "csv"
    assert doc.sections[0].kind == "table"
    assert doc.sections[0].text == "| city | population |\n|---|---|\n| Oslo | 700000 |\n| Bergen | 290000 |"


KB_FILES = sorted(KNOWLEDGE_BASE.rglob("*.md"))


def test_knowledge_base_present():
    assert len(KB_FILES) == 76


@pytest.mark.parametrize("path", KB_FILES, ids=lambda p: p.relative_to(KNOWLEDGE_BASE).as_posix())
def test_knowledge_base_file_loads(path):
    doc_id = path.relative_to(KNOWLEDGE_BASE).as_posix()
    doc = load_file(path, doc_id)
    assert doc.title and doc.sections
    assert all(s.heading_path and s.heading_path[0] == doc.title for s in doc.sections)
    kept = sum(len(s.text) for s in doc.sections)
    assert kept >= 0.85 * len(path.read_text(encoding="utf-8"))  # only heading lines are moved out of the text


def test_knowledge_base_titles_are_unique():
    titles = [load_file(p, p.name).title for p in KB_FILES]
    assert len(set(titles)) == len(titles)
