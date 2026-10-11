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
"""
from pathlib import Path
from typing import Iterator

from answer_engine.config import DEFAULT_CLIENT_ID
from answer_engine.schema import Chunk


def add_file(path: Path, doc_id: str, client_id: str = DEFAULT_CLIENT_ID) -> int:
    raise NotImplementedError


def remove_document(doc_id: str, client_id: str = DEFAULT_CLIENT_ID) -> None:
    raise NotImplementedError


def fetch_context(question: str, history: list[dict] = [], client_id: str = DEFAULT_CLIENT_ID) -> list[Chunk]:
    raise NotImplementedError


def answer_question(question: str, history: list[dict] = [], client_id: str = DEFAULT_CLIENT_ID) -> tuple[str, list[Chunk]]:
    raise NotImplementedError


def stream_answer(question: str, history: list[dict] = [], client_id: str = DEFAULT_CLIENT_ID) -> Iterator[tuple[str, list[Chunk]]]:
    raise NotImplementedError
