"""Public entry point of the answer engine. Owner: Terminal A.

Agreed module interfaces (implemented by their owners):
  loaders.load_file(path: Path, doc_id: str) -> LoadedDocument          (Terminal C)
  loaders.SUPPORTED_EXTENSIONS: set[str]                                  (Terminal C)
  chunking.chunk_document(doc: LoadedDocument, client_id: str) -> list[Chunk]  (Terminal D)
  index.ClientIndex(client_id)                                            (Terminal D)
      .upsert_document(doc: LoadedDocument) -> int   # re-chunks + replaces; skips if hash unchanged
      .remove_document(doc_id: str) -> None
      .list_documents() -> list[dict]
      .vector_search(query: str, k: int) -> list[Chunk]
      .keyword_search(query: str, k: int) -> list[Chunk]
  retrieval.retrieve(index: ClientIndex, question: str, history: list[dict]) -> list[Chunk]  (Terminal D)
  generation.make_messages / generate / stream_generate                   (Terminal A)

CLI:
  python -m answer_engine.pipeline ingest <folder> [--client ID]
  python -m answer_engine.pipeline ask "<question>" [--client ID]
"""
import argparse
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from dotenv import load_dotenv

from answer_engine import generation
from answer_engine.config import CLIENT_NAMES, DEFAULT_CLIENT_ID
from answer_engine.schema import Chunk

load_dotenv(override=True)


@lru_cache(maxsize=None)
def _index(client_id: str):
    from answer_engine.index import ClientIndex

    return ClientIndex(client_id)


def organization_name(client_id: str) -> str:
    return CLIENT_NAMES.get(client_id, client_id)


def add_file(path: Path, doc_id: str, client_id: str = DEFAULT_CLIENT_ID) -> int:
    """Load, chunk and index one file; returns the number of chunks written (0 if unchanged)."""
    from answer_engine.loaders import load_file

    return _index(client_id).upsert_document(load_file(Path(path), doc_id))


def add_folder(folder: Path, client_id: str = DEFAULT_CLIENT_ID) -> dict[str, int]:
    """Index every supported file under folder; doc_id is the path relative to folder."""
    from answer_engine.loaders import SUPPORTED_EXTENSIONS

    folder = Path(folder)
    results = {}
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            doc_id = path.relative_to(folder).as_posix()
            results[doc_id] = add_file(path, doc_id, client_id)
    return results


def remove_document(doc_id: str, client_id: str = DEFAULT_CLIENT_ID) -> None:
    _index(client_id).remove_document(doc_id)


def list_documents(client_id: str = DEFAULT_CLIENT_ID) -> list[dict]:
    return _index(client_id).list_documents()


def fetch_context(question: str, history: list[dict] = [], client_id: str = DEFAULT_CLIENT_ID) -> list[Chunk]:
    from answer_engine.retrieval import retrieve

    return retrieve(_index(client_id), question, history)


def answer_question(question: str, history: list[dict] = [], client_id: str = DEFAULT_CLIENT_ID) -> tuple[str, list[Chunk]]:
    chunks = fetch_context(question, history, client_id)
    messages = generation.make_messages(question, history, chunks, organization_name(client_id))
    return generation.generate(messages), chunks


def stream_answer(question: str, history: list[dict] = [], client_id: str = DEFAULT_CLIENT_ID) -> Iterator[tuple[str, list[Chunk]]]:
    chunks = fetch_context(question, history, client_id)
    yield "", chunks
    messages = generation.make_messages(question, history, chunks, organization_name(client_id))
    for answer in generation.stream_generate(messages):
        yield answer, chunks


def main():
    parser = argparse.ArgumentParser(description="Answer engine CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", help="index every supported file in a folder")
    ingest.add_argument("folder")
    ask = sub.add_parser("ask", help="answer one question")
    ask.add_argument("question")
    for p in (ingest, ask):
        p.add_argument("--client", default=DEFAULT_CLIENT_ID)
    args = parser.parse_args()

    if args.command == "ingest":
        results = add_folder(Path(args.folder), args.client)
        changed = sum(1 for n in results.values() if n)
        print(f"{len(results)} files scanned, {changed} (re)indexed, {sum(results.values())} chunks written")
    else:
        answer, chunks = answer_question(args.question, client_id=args.client)
        print(answer)
        print("\nSources:", *sorted({c.metadata.get("source") for c in chunks}), sep="\n  ")


if __name__ == "__main__":
    main()
