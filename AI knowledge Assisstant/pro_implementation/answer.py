import re
from typing import Iterator
from dotenv import load_dotenv
from chromadb import PersistentClient
from litellm import completion
from pydantic import BaseModel
from pathlib import Path
from functools import lru_cache
from sentence_transformers import CrossEncoder
from rank_bm25 import BM25Okapi
from tenacity import retry, stop_after_attempt, wait_exponential

from pro_implementation.embeddings import embed_query


load_dotenv(override=True)

# MODEL = "openai/gpt-4.1-nano"
MODEL = "groq/openai/gpt-oss-120b"
REWRITE_MODEL = "groq/openai/gpt-oss-20b"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
DB_NAME = str(Path(__file__).parent.parent / "preprocessed_db")
KNOWLEDGE_BASE_PATH = Path(__file__).parent.parent / "knowledge-base"
SUMMARIES_PATH = Path(__file__).parent.parent / "summaries"

collection_name = "docs"
wait = wait_exponential(multiplier=1, min=10, max=240)
stop = stop_after_attempt(4)

chroma = PersistentClient(path=DB_NAME)
collection = chroma.get_or_create_collection(collection_name)

RETRIEVAL_K = 20
FINAL_K = 10
MAX_HISTORY_MESSAGES = 6

SYSTEM_PROMPT = """
You are a knowledgeable, friendly assistant representing the company Insurellm.
You are chatting with a user about Insurellm.
Your answer will be evaluated for accuracy, relevance and completeness, so make sure it only answers the question and fully answers it.
If you don't know the answer, say so.
For context, here are specific extracts from the Knowledge Base that might be directly relevant to the user's question:
{context}

With this context, please answer the user's question. Be accurate, relevant and complete.
"""


class Result(BaseModel):
    page_content: str
    metadata: dict


@lru_cache(maxsize=1)
def _reranker() -> CrossEncoder:
    return CrossEncoder(RERANK_MODEL)


def rerank(question, chunks):
    """Order chunks by local cross-encoder relevance score, most relevant first."""
    if not chunks:
        return []
    scores = _reranker().predict([(question, chunk.page_content) for chunk in chunks])
    ranked = sorted(zip(scores, range(len(chunks))), key=lambda pair: pair[0], reverse=True)
    return [chunks[i] for _, i in ranked]


def make_rag_messages(question, history, chunks):
    context = "\n\n".join(
        f"Extract from {chunk.metadata['source']}:\n{chunk.page_content}" for chunk in chunks
    )
    system_prompt = SYSTEM_PROMPT.format(context=context)
    # Keep only role/content (Gradio adds extra keys) and cap the history length
    recent = [{"role": m["role"], "content": m["content"]} for m in history[-MAX_HISTORY_MESSAGES:]]
    return (
        [{"role": "system", "content": system_prompt}]
        + recent
        + [{"role": "user", "content": question}]
    )


def format_history(history):
    return "\n".join(f"{turn['role']}: {turn['content']}" for turn in history) or "(no prior conversation)"


@retry(wait=wait, stop=stop, reraise=True)
def _rewrite_query(question, history):
    """Rewrite the user's question to be a more specific question that is more likely to surface relevant content in the Knowledge Base."""
    message = f"""
You are in a conversation with a user, answering questions about the company Insurellm.
You are about to look up information in a Knowledge Base to answer the user's question.

This is the history of your conversation so far with the user:
{format_history(history)}

And this is the user's current question:
{question}

Respond only with a short, refined question that you will use to search the Knowledge Base.
It should be a VERY short specific question most likely to surface content. Focus on the question details.
IMPORTANT: Respond ONLY with the precise knowledgebase query, nothing else.
"""
    response = completion(model=REWRITE_MODEL, messages=[{"role": "system", "content": message}])
    return response.choices[0].message.content.strip()


def rewrite_query(question, history=[]):
    """Rewrite the question using the chat history; fall back to the original question if the LLM fails."""
    try:
        return _rewrite_query(question, history) or question
    except Exception as e:
        print(f"rewrite_query failed, using original question: {type(e).__name__}: {str(e)[:200]}")
        return question


def merge_chunks(*chunk_lists):
    """Concatenate chunk lists, dropping duplicates by content."""
    merged, existing = [], set()
    for chunks in chunk_lists:
        for chunk in chunks:
            if chunk.page_content not in existing:
                existing.add(chunk.page_content)
                merged.append(chunk)
    return merged


def tokenize(text):
    return re.findall(r"\w+", text.lower())


@lru_cache(maxsize=1)
def _bm25_index():
    """BM25 keyword index over every chunk in the collection, built on first use."""
    data = collection.get(include=["documents", "metadatas"])
    chunks = [Result(page_content=d, metadata=m) for d, m in zip(data["documents"], data["metadatas"])]
    return BM25Okapi([tokenize(c.page_content) for c in chunks]), chunks


def keyword_search(question):
    bm25, chunks = _bm25_index()
    if not chunks:
        return []
    scores = bm25.get_scores(tokenize(question))
    top = sorted(range(len(chunks)), key=lambda i: scores[i], reverse=True)[:RETRIEVAL_K]
    return [chunks[i] for i in top if scores[i] > 0]


def fetch_context_unranked(question):
    query = embed_query(question)
    results = collection.query(query_embeddings=[query], n_results=RETRIEVAL_K)
    chunks = []
    for result in zip(results["documents"][0], results["metadatas"][0]):
        chunks.append(Result(page_content=result[0], metadata=result[1]))
    return chunks


def fetch_context(original_question, history=[]):
    rewritten_question = rewrite_query(original_question, history)
    chunks = merge_chunks(
        fetch_context_unranked(original_question),
        fetch_context_unranked(rewritten_question),
        keyword_search(f"{original_question} {rewritten_question}"),
    )
    # A follow-up like "who leads it?" only makes sense to the reranker after the rewrite
    rerank_query = rewritten_question if history else original_question
    reranked = rerank(rerank_query, chunks)
    return reranked[:FINAL_K]


def llm(messages: list[dict], **kwargs):
    return completion(model=MODEL, messages=messages, temperature=0, **kwargs)


def answer_question(question: str, history: list[dict] = []) -> tuple[str, list]:
    """
    Answer a question using RAG and return the answer and the retrieved context
    """
    chunks = fetch_context(question, history)
    messages = make_rag_messages(question, history, chunks)
    response = llm(messages)
    return response.choices[0].message.content, chunks


def stream_answer(question: str, history: list[dict] = []) -> Iterator[tuple[str, list]]:
    """
    Like answer_question, but yields (answer_so_far, docs) as tokens arrive.
    """
    chunks = fetch_context(question, history)
    answer = ""
    yield answer, chunks
    for chunk in llm(make_rag_messages(question, history, chunks), stream=True):
        answer += chunk.choices[0].delta.content or ""
        yield answer, chunks
