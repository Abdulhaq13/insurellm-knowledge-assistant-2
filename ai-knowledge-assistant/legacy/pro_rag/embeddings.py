from functools import lru_cache

from sentence_transformers import SentenceTransformer

# Shared by ingest.py and answer.py: changing it requires re-running legacy/pro_rag/ingest.py
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
QUERY_PROMPT = "Represent this sentence for searching relevant passages: "


@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL)


def embed_documents(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True).tolist()


def embed_query(text: str) -> list[float]:
    return _model().encode(text, prompt=QUERY_PROMPT, normalize_embeddings=True).tolist()
