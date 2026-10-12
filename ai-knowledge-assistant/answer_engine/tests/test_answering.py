"""Retrieval helpers, answer prompt and index safety tests (no API calls).
Run: python -m answer_engine.tests.test_answering"""
import shutil
import tempfile
from pathlib import Path

from answer_engine import generation, index as index_module, retrieval
from answer_engine.config import MAX_HISTORY_MESSAGES
from answer_engine.index import ClientIndex
from answer_engine.schema import Chunk, LoadedDocument, Section


def chunk(doc_id: str, n: int = 0, text: str = "text", title: str | None = None) -> Chunk:
    return Chunk(page_content=text, metadata={"doc_id": doc_id, "chunk_index": n, "title": title or doc_id, "source": doc_id})


def test_search_query_adds_latest_user_turn_after_the_question():
    history = [
        {"role": "user", "content": "Tell me about Carllm"},
        {"role": "assistant", "content": "Carllm is a product."},
        {"role": "user", "content": "And Homellm?"},
    ]
    assert retrieval.search_query("Who leads it?", history) == "Who leads it?\nAnd Homellm?"
    assert retrieval.search_query("Who leads it?", []) == "Who leads it?"


def test_list_questions_are_detected():
    assert retrieval.is_list_question("Which employees work in Chicago?")
    assert retrieval.is_list_question("How many products are there?")
    assert not retrieval.is_list_question("Who is the CEO?")


def test_merge_drops_duplicate_chunks_and_keeps_order():
    merged = retrieval.merge([chunk("a", 0), chunk("b", 0)], [chunk("a", 0), chunk("a", 1)])
    assert [(c.metadata["doc_id"], c.metadata["chunk_index"]) for c in merged] == [("a", 0), ("b", 0), ("a", 1)]


def test_diverse_extra_takes_one_chunk_per_new_document():
    ranked = [chunk("a", 1), chunk("b", 0), chunk("b", 1), chunk("c", 0), chunk("d", 0)]
    extra = retrieval.diverse_extra(ranked, selected=[chunk("a", 0)], k=2)
    assert [c.metadata["doc_id"] for c in extra] == ["b", "c"]


def test_top_titles_are_distinct_documents_in_rank_order():
    ranked = [chunk("a", 0, title="Alpha"), chunk("a", 1, title="Alpha"), chunk("b", 0, title="Beta"), chunk("c", 0)]
    assert retrieval.top_titles(ranked, 2) == ["Alpha", "Beta"]


def test_citations_are_normalised_to_square_brackets():
    assert generation.normalize_citations("Costs $5 【1】 and 【2†L3】.") == "Costs $5 [1] and [2]."


def test_messages_number_excerpts_and_cap_history():
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(10)]
    messages = generation.make_messages("Q?", history, [chunk("a.md", text="Alpha text")], "Acme")
    system = messages[0]["content"]
    assert "[1] Source: a.md\nAlpha text" in system and "Acme" in system
    assert len(messages) == 1 + MAX_HISTORY_MESSAGES + 1
    assert messages[-1] == {"role": "user", "content": "Q?"}
    assert "(no relevant excerpts found)" in generation.make_messages("Q?", [], [], "Acme")[0]["content"]


def test_failed_replace_keeps_the_old_version():
    def doc(text: str, content_hash: str) -> LoadedDocument:
        return LoadedDocument(doc_id="a.md", title="A", source="a.md", file_type="md",
                              sections=[Section(heading_path=["Body"], text=text)], content_hash=content_hash)

    def broken_embedder(texts):
        raise MemoryError("simulated failure while embedding")

    data_dir = Path(tempfile.mkdtemp())
    real_embedder = index_module.embed_documents
    try:
        index = ClientIndex("acme", data_dir)
        index.upsert_document(doc("The zebra project costs $10,000.", "h1"))
        index_module.embed_documents = broken_embedder
        try:
            index.upsert_document(doc("The giraffe project replaced it.", "h2"))
        except MemoryError:
            pass
        else:
            raise AssertionError("the simulated failure did not happen")
        index_module.embed_documents = real_embedder
        assert index.keyword_search("zebra", 5)[0].metadata["doc_id"] == "a.md"
    finally:
        index_module.embed_documents = real_embedder
        shutil.rmtree(data_dir, ignore_errors=True)


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
