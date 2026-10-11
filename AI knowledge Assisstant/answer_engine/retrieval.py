"""Find the chunks that answer a question. Owner: Terminal D.

hybrid search (vector + BM25, CANDIDATES_K each) -> merge -> local cross-encoder rerank
-> FINAL_K chunks, plus extra chunks from other documents for "how many / which / list all" questions.
Optional: an LLM splits multi-part questions into sub-questions (off by default; costs Groq quota).
"""
import json
import re
from functools import lru_cache

import litellm
from litellm import completion
from sentence_transformers import CrossEncoder
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from answer_engine.config import CANDIDATES_K, FINAL_K, HELPER_MODEL, RERANK_MODEL
from answer_engine.index import ClientIndex
from answer_engine.schema import Chunk

litellm.suppress_debug_info = True

DECOMPOSE = False  # LLM sub-question step; keep off unless the HELPER_MODEL quota is free
LIST_EXTRA_K = FINAL_K  # extra chunks, each from a new document, for list-style questions (0 = off)
HISTORY_TURNS = 1  # prior user turns added to the search query for follow-up questions

LIST_QUESTION = re.compile(
    r"\b(how many|which|list|all|every|each|total|average|combined|across|most|least|fewest|compare|both)\b",
    re.IGNORECASE,
)


def retrieve(index: ClientIndex, question: str, history: list[dict] = []) -> list[Chunk]:
    query = search_query(question, history)
    queries = [query] + (decompose_question(query) if DECOMPOSE else [])
    candidates = merge(*[r for q in queries for r in (index.vector_search(q, CANDIDATES_K), index.keyword_search(q, CANDIDATES_K))])
    ranked = Reranker(queries).rank(candidates)
    selected = ranked[:FINAL_K]
    if LIST_EXTRA_K and is_list_question(question):
        selected += diverse_extra(ranked[FINAL_K:], selected, LIST_EXTRA_K)
    return selected


def search_query(question: str, history: list[dict]) -> str:
    """The question first, then the latest user turns so follow-ups like "who leads it?" still find their topic."""
    prior = [m["content"] for m in history if m.get("role") == "user" and isinstance(m.get("content"), str)]
    return "\n".join([question, *reversed(prior[-HISTORY_TURNS:])]) if HISTORY_TURNS else question


def is_list_question(question: str) -> bool:
    return bool(LIST_QUESTION.search(question))


def diverse_extra(ranked: list[Chunk], selected: list[Chunk], k: int) -> list[Chunk]:
    """Up to k more chunks in rank order, at most one per document not already selected."""
    seen = {c.metadata["doc_id"] for c in selected}
    extra = []
    for chunk in ranked:
        if len(extra) >= k:
            break
        if chunk.metadata["doc_id"] not in seen:
            seen.add(chunk.metadata["doc_id"])
            extra.append(chunk)
    return extra


def merge(*chunk_lists: list[Chunk]) -> list[Chunk]:
    merged, seen = [], set()
    for chunks in chunk_lists:
        for chunk in chunks:
            key = (chunk.metadata.get("doc_id"), chunk.metadata.get("chunk_index"))
            if key not in seen:
                seen.add(key)
                merged.append(chunk)
    return merged


@lru_cache(maxsize=1)
def cross_encoder() -> CrossEncoder:
    return CrossEncoder(RERANK_MODEL)


class Reranker:
    """Cross-encoder scores, cached per chunk. With sub-questions, a chunk scores its best match to any query."""

    def __init__(self, queries: list[str]):
        self.queries = queries
        self.scores: dict[tuple, float] = {}

    def rank(self, chunks: list[Chunk]) -> list[Chunk]:
        new = [c for c in chunks if self._key(c) not in self.scores]
        if new:
            pairs = [(q, c.page_content) for c in new for q in self.queries]
            flat = cross_encoder().predict(pairs)
            n = len(self.queries)
            for i, chunk in enumerate(new):
                self.scores[self._key(chunk)] = max(flat[i * n : (i + 1) * n])
        return sorted(chunks, key=lambda c: self.scores[self._key(c)], reverse=True)

    @staticmethod
    def _key(chunk: Chunk) -> tuple:
        return chunk.metadata.get("doc_id"), chunk.metadata.get("chunk_index")


DECOMPOSE_PROMPT = """Split the user's question into the separate lookups needed to answer it from a document collection.
If the question needs one fact found first to look up another (e.g. "the X who did Y"), make one lookup per fact.
If it is already a single simple lookup, return it unchanged as the only item.
Reply with JSON only: {"questions": ["...", "..."]} with at most 4 short questions."""


@retry(
    retry=retry_if_exception_type((litellm.RateLimitError, litellm.APIConnectionError, litellm.InternalServerError)),
    wait=wait_exponential(multiplier=2, min=2, max=30),
    stop=stop_after_attempt(4),
    reraise=True,
)
def _decompose(question: str) -> list[str]:
    response = completion(
        model=HELPER_MODEL,
        messages=[{"role": "system", "content": DECOMPOSE_PROMPT}, {"role": "user", "content": question}],
        response_format={"type": "json_object"},
        temperature=0,
    )
    questions = json.loads(response.choices[0].message.content).get("questions", [])
    return [q.strip() for q in questions if isinstance(q, str) and q.strip()][:4]


def decompose_question(question: str) -> list[str]:
    """Sub-questions for a multi-part question ([] for simple ones or if the LLM call fails)."""
    try:
        subs = _decompose(question)
    except Exception as e:
        print(f"decompose_question failed, searching the original question only: {type(e).__name__}: {str(e)[:200]}")
        return []
    return [] if len(subs) <= 1 else subs
