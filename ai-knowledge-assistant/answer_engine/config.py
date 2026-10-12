from pathlib import Path

ROOT = Path(__file__).parent.parent
DATA_DIR = ROOT / "engine_data"  # per-client Chroma DBs and indexes (gitignored)
DEFAULT_CLIENT_ID = "insurellm"
# Display names per client; replaced by a client table once the multi-client platform exists
CLIENT_NAMES = {"insurellm": "Insurellm"}

# Answers use OpenAI (needs OPENAI_API_KEY in .env); the helper stays on the Groq free tier
ANSWER_MODEL = "openai/gpt-4.1-mini"
HELPER_MODEL = "groq/openai/gpt-oss-20b"  # query rewriting / decomposition
# Evaluation only (free Groq). The judge is a different model family from the answerer
JUDGE_MODEL = "groq/qwen/qwen3.8-27b"
TEST_GENERATOR_MODEL = "groq/openai/gpt-oss-20b"  # evaluation/generate_tests.py

EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # changing it requires re-ingesting every client
EMBEDDING_QUERY_PROMPT = "Represent this sentence for searching relevant passages: "
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 200
CANDIDATES_K = 20  # per search method, before reranking
FINAL_K = 6  # chunks sent to the answer model
MAX_HISTORY_MESSAGES = 6
CITE_SOURCES = True  # answers cite excerpt numbers like [1]
