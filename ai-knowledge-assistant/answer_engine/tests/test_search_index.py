"""ClientIndex tests (local embeddings, no API calls). Run: python -m answer_engine.tests.test_search_index"""
import shutil
import tempfile
from pathlib import Path

from answer_engine.index import ClientIndex, tokenize
from answer_engine.schema import LoadedDocument, Section


def make_doc(doc_id: str, text: str, content_hash: str) -> LoadedDocument:
    return LoadedDocument(
        doc_id=doc_id, title=Path(doc_id).stem, source=doc_id, file_type="md",
        sections=[Section(heading_path=["Body"], text=text)], content_hash=content_hash,
    )


def test_upsert_skip_replace_remove_and_isolation():
    data_dir = Path(tempfile.mkdtemp())
    try:
        index = ClientIndex("acme", data_dir)
        assert index.upsert_document(make_doc("a.md", "The zebra project costs $10,000 per month.", "h1")) == 1
        assert index.upsert_document(make_doc("b.md", "Penguins live in Antarctica.", "h2")) == 1
        assert index.upsert_document(make_doc("a.md", "changed text is ignored when hash is equal", "h1")) == 0

        assert index.keyword_search("zebra cost", 5)[0].metadata["doc_id"] == "a.md"
        assert index.vector_search("Where do penguins live?", 1)[0].metadata["doc_id"] == "b.md"

        index.upsert_document(make_doc("a.md", "The giraffe project replaced it.", "h3"))
        assert not index.keyword_search("zebra", 5)
        assert index.keyword_search("giraffe", 5)[0].metadata["doc_id"] == "a.md"

        index.remove_document("a.md")
        assert [d["doc_id"] for d in index.list_documents()] == ["b.md"]

        other = ClientIndex("other", data_dir)
        assert other.list_documents() == [] and other.vector_search("penguins", 3) == []
    finally:
        shutil.rmtree(data_dir, ignore_errors=True)


def test_tokenize_drops_stop_words_but_keeps_numbers():
    assert tokenize("Which employees are based in Chicago, and what are their jobs?") == ["employees", "based", "chicago", "jobs"]
    assert tokenize("It costs $10,000 in Q2") == ["costs", "10,000", "q2"]
    assert tokenize("What is it?") == ["what", "is", "it"]  # only stop words: keep them rather than search nothing


def test_rejects_unsafe_client_id():
    try:
        ClientIndex("../escape", Path(tempfile.gettempdir()))
    except ValueError:
        return
    raise AssertionError("unsafe client_id accepted")


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
