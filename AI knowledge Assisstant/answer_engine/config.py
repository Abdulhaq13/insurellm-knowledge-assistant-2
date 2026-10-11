from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "engine_data"  # per-client Chroma DBs and indexes (gitignored)
DEFAULT_CLIENT_ID = "insurellm"

# Free tier now; switch to paid models here only once the product has real users
ANSWER_MODEL = "groq/openai/gpt-oss-120b"
HELPER_MODEL = "groq/openai/gpt-oss-20b"  # query rewriting / decomposition

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # changing it requires re-ingesting every client
EMBEDDING_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
CANDIDATES_K = 20  # per search method, before reranking
FINAL_K = 6  # chunks sent to the answer model
MAX_HISTORY_MESSAGES = 6
