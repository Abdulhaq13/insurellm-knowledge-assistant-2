"""Chunking tests. Run: python -m answer_engine.tests.test_search_chunking (pytest also works)."""
from answer_engine.chunking import chunk_document
from answer_engine.config import CHUNK_SIZE
from answer_engine.schema import LoadedDocument, Section

REQUIRED = {"client_id", "doc_id", "source", "title", "section", "chunk_index"}


def make_doc(sections: list[Section]) -> LoadedDocument:
    return LoadedDocument(
        doc_id="folder/Guide.md", title="Guide", source="folder/Guide.md", file_type="md",
        sections=sections, content_hash="abc",
    )


def test_sections_never_mix_and_headers():
    doc = make_doc([
        Section(heading_path=["Guide", "Intro"], text="Alpha paragraph."),
        Section(heading_path=["Guide", "Pricing", "Basic"], text="Beta paragraph."),
    ])
    chunks = chunk_document(doc, "acme")
    assert len(chunks) == 2
    assert chunks[0].page_content == "Guide > Intro\n\nAlpha paragraph."
    assert chunks[1].page_content.startswith("Guide > Pricing > Basic\n\n")
    assert "Alpha" not in chunks[1].page_content


def test_long_text_split_with_size_limit_and_overlap():
    text = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(30))
    chunks = chunk_document(make_doc([Section(heading_path=["Body"], text=text)]), "acme")
    assert len(chunks) > 1
    assert all(len(c.page_content) <= CHUNK_SIZE for c in chunks)
    for c in chunks:
        assert c.page_content.startswith("Guide > Body\n\n")
    # consecutive chunks share text (overlap)
    for a, b in zip(chunks, chunks[1:]):
        assert a.page_content[-40:].strip() in b.page_content
    # nothing lost
    for i in range(30):
        assert any(f"Paragraph {i} " in c.page_content for c in chunks)


def test_table_rows_whole_and_header_repeated():
    header = "| Name | Role | Notes |\n|---|---|---|"
    rows = [f"| Person {i} | Role {i} | " + "x" * 80 + " |" for i in range(60)]
    doc = make_doc([Section(heading_path=["Staff"], text=header + "\n" + "\n".join(rows), kind="table")])
    chunks = chunk_document(doc, "acme")
    assert len(chunks) > 1
    seen = []
    for c in chunks:
        body = c.page_content.split("\n\n", 1)[1]
        lines = body.splitlines()
        assert "\n".join(lines[:2]) == header
        assert all(line in rows for line in lines[2:])
        seen += lines[2:]
    assert seen == rows


def test_metadata_and_empty_sections():
    doc = make_doc([Section(heading_path=["A"], text="   "), Section(heading_path=["B"], text="Text.")])
    chunks = chunk_document(doc, "acme")
    assert len(chunks) == 1
    meta = chunks[0].metadata
    assert REQUIRED <= meta.keys()
    assert meta["client_id"] == "acme" and meta["doc_id"] == "folder/Guide.md"
    assert meta["section"] == "B" and meta["chunk_index"] == 0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
