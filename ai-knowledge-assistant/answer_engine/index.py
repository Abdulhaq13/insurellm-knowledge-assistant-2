"""Per-client document index: a Chroma vector collection plus an in-memory BM25 keyword index. Owner: Terminal D.

Every client has its own Chroma database under DATA_DIR/<client_id>, so one client's search can never
return another client's chunks. Adding or removing a document only touches that document's chunks.
"""
import math
import re
from functools import lru_cache
from pathlib import Path

import chromadb
from chromadb.config import Settings
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer

from answer_engine.chunking import chunk_document
from answer_engine.config import DATA_DIR, EMBEDDING_MODEL, EMBEDDING_QUERY_PROMPT
from answer_engine.schema import Chunk, LoadedDocument

COLLECTION = "docs"
CLIENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
# Words, plus numbers with their separators kept together ("10,000", "2.5", "q2")
TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)*")
# Common English words left out of keyword search. In short, terse documents words like "which" or "their"
# are rare, so BM25 would treat them as important and rank prose pages above the chunk with the real keyword.
STOP_WORDS = frozenset(
    """a an and are as at be been being but by can could did do does for from had has have he her his how i if
    in into is it its may me might my of on or our she should so such than that the their them then there these
    they this to was we were what when where which who whom whose why will with would you your""".split()
)


@lru_cache(maxsize=1)
def embedder() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return embedder().encode(texts, normalize_embeddings=True, batch_size=32).tolist()


def embed_query(query: str) -> list[float]:
    return embedder().encode([EMBEDDING_QUERY_PROMPT + query], normalize_embeddings=True)[0].tolist()


def tokenize(text: str) -> list[str]:
    """Keyword-search tokens without stop words (all tokens if the text is nothing but stop words)."""
    tokens = TOKEN_PATTERN.findall(text.lower())
    return [t for t in tokens if t not in STOP_WORDS] or tokens


class BM25(BM25Okapi):
    """BM25 with Lucene's always-positive IDF. Okapi's IDF is zero or negative for words in half or
    more of the chunks, which makes keyword search find nothing in a small client's collection."""

    def _calc_idf(self, nd):
        self.idf = {word: math.log(1 + (self.corpus_size - freq + 0.5) / (freq + 0.5)) for word, freq in nd.items()}


class ClientIndex:
    def __init__(self, client_id: str, data_dir: Path = DATA_DIR):
        # client_id becomes a folder name, so only allow safe characters (no "../" escapes)
        if not CLIENT_ID_PATTERN.match(client_id):
            raise ValueError(f"Invalid client_id: {client_id!r}")
        self.client_id = client_id
        self.path = Path(data_dir) / client_id
        self.path.mkdir(parents=True, exist_ok=True)
        self._db = chromadb.PersistentClient(path=str(self.path), settings=Settings(anonymized_telemetry=False))
        self.collection = self._db.get_or_create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        self._bm25: tuple[BM25, list[Chunk]] | None = None

    def upsert_document(self, doc: LoadedDocument) -> int:
        """Index a document, replacing its old chunks. Returns the chunk count, or 0 if the file is unchanged."""
        existing = self.collection.get(where={"doc_id": doc.doc_id}, limit=1, include=["metadatas"])
        if existing["metadatas"] and existing["metadatas"][0].get("content_hash") == doc.content_hash:
            return 0
        chunks = chunk_document(doc, self.client_id)
        self.remove_document(doc.doc_id)
        if chunks:
            self.collection.add(
                ids=[f"{doc.doc_id}::{c.metadata['chunk_index']}" for c in chunks],
                documents=[c.page_content for c in chunks],
                embeddings=embed_documents([c.page_content for c in chunks]),
                metadatas=[c.metadata for c in chunks],
            )
        self._bm25 = None
        return len(chunks)

    def remove_document(self, doc_id: str) -> None:
        self.collection.delete(where={"doc_id": doc_id})
        self._bm25 = None

    def list_documents(self) -> list[dict]:
        documents: dict[str, dict] = {}
        for meta in self.collection.get(include=["metadatas"])["metadatas"]:
            entry = documents.setdefault(meta["doc_id"], {
                "doc_id": meta["doc_id"],
                "title": meta.get("title"),
                "source": meta.get("source"),
                "file_type": meta.get("file_type"),
                "content_hash": meta.get("content_hash"),
                "chunks": 0,
            })
            entry["chunks"] += 1
        return sorted(documents.values(), key=lambda d: d["doc_id"])

    def document_chunks(self, doc_id: str) -> list[Chunk]:
        """All chunks of one document, in reading order."""
        data = self.collection.get(where={"doc_id": doc_id}, include=["documents", "metadatas"])
        chunks = [Chunk(page_content=d, metadata=m) for d, m in zip(data["documents"], data["metadatas"])]
        return sorted(chunks, key=lambda c: c.metadata["chunk_index"])

    def vector_search(self, query: str, k: int) -> list[Chunk]:
        count = self.collection.count()
        if not count:
            return []
        results = self.collection.query(
            query_embeddings=[embed_query(query)], n_results=min(k, count), include=["documents", "metadatas"]
        )
        return [Chunk(page_content=d, metadata=m) for d, m in zip(results["documents"][0], results["metadatas"][0])]

    def keyword_search(self, query: str, k: int) -> list[Chunk]:
        bm25, chunks = self._keyword_index()
        tokens = tokenize(query)
        if not chunks or not tokens:
            return []
        scores = bm25.get_scores(tokens)
        top = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:k]
        return [chunks[i] for i in top if scores[i] > 0]

    def rare_terms(self, query: str, n: int) -> list[str]:
        """The query's n rarest words that appear in this index (highest IDF first)."""
        bm25, _ = self._keyword_index()
        if bm25 is None:
            return []
        tokens = {t for t in tokenize(query) if bm25.idf.get(t, 0) > 0}
        return sorted(tokens, key=lambda t: (-bm25.idf[t], t))[:n]

    def _keyword_index(self) -> tuple[BM25 | None, list[Chunk]]:
        # Rebuilt lazily from the stored chunk texts after any change; nothing is re-embedded
        if self._bm25 is None:
            data = self.collection.get(include=["documents", "metadatas"])
            chunks = [Chunk(page_content=d, metadata=m) for d, m in zip(data["documents"], data["metadatas"])]
            bm25 = BM25([tokenize(c.page_content) for c in chunks]) if chunks else None
            self._bm25 = (bm25, chunks)
        return self._bm25
