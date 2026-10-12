# CLAUDE.md

This file gives Claude Code guidance for working in this repository.

## What this is

A RAG (retrieval-augmented generation) assistant that answers questions from a set of documents. Today it answers about **Insurellm**, a fictional insurance-tech company whose knowledge base is a folder of Markdown files. It started from Week 5 of the "LLM Engineering" course and is the user's college project.

**Where it is heading** (the user's decision on 2026-10-11, in this order):
1. **Accuracy first.** Get answer accuracy above 90% using *general* techniques that work on any documents. Never hard-code anything about specific documents (no parsers for "the employee file format", no Insurellm-specific rules), because clients will upload their own files.
2. **Then a multi-client platform ("Option 1").** One codebase. Each client organisation gets its own assistant with a separate document collection, its own admins (who upload, replace and delete documents) and its own employees/users (who only ask questions). Clients must never see each other's data. The user is the platform owner.
3. **All file types** (PDF, Word, Excel, text, Markdown). Cost and latency must stay low.

Top-level folders:

- `ai-knowledge-assistant/` is the project: the engine, the app, the evaluation harness, demo documents, legacy pipelines and a local `.venv` (Python 3.13).
- `docs/` holds project documents (`solution-overview.md`).

Not deploying for now: the app runs locally (user decision 2026-10-11); the UI moves to a MERN stack later, calling the Python engine. The old Hugging Face copy and other students' course submissions were moved out of the repo to `D:\cllg\archive\old-huggingface-space\` and `D:\cllg\course-community-contributions\`.

## Cost rule

**Answers in `answer_engine` use paid OpenAI `openai/gpt-4.1-mini`** (user decision 2026-10-11; the user has a small credit, about $2). That's roughly $0.001–0.0015 per question, or about $0.20–0.25 for a 150-question eval. Don't switch answers back to Groq without asking. **Everything else stays free:** the query-decomposition helper (`groq/openai/gpt-oss-20b`), the eval judge (`groq/qwen/qwen3.8-27b`), and the local embeddings, reranker and OCR. The legacy `legacy/basic_rag/` and `legacy/pro_rag/` pipelines still answer with Groq `gpt-oss-120b`. Keep every model name in one constant (`answer_engine/config.py`) so model changes are one-line edits. Groq free limits are **per model, shared across the whole account**: about 8,000 tokens/minute and 1,000 requests/day. Two processes calling the same model slow each other down. Gemini's free tier is ~20 requests/day per model, which is unusable for evals.

## Layout (inside `ai-knowledge-assistant/`)

| Path | Role |
|---|---|
| `answer_engine/` | **The current engine**, which replaces both legacy pipelines: `loaders.py` (all file types plus OCR), `chunking.py`, `index.py` (one Chroma DB + BM25 per client under `engine_data/<client_id>/`), `retrieval.py` (hybrid search + cross-encoder rerank), `generation.py` (grounded answers with citations and a security rule against instructions inside documents), `pipeline.py` (public API and CLI), `config.py` (all models and settings). See `README.md`. |
| `answer_engine/tests/` | pytest tests and `fixtures/`; `benchmarks/` holds the free retrieval benchmarks (`python -m answer_engine.tests.benchmarks.bench_retrieval`). |
| `app.py` | Gradio UI on `answer_engine`: a Chat tab, plus a Documents tab to upload, replace, list and delete files. |
| `legacy/basic_app.py` | Legacy Gradio chat UI on the basic pipeline (`python -m legacy.basic_app`). |
| `legacy/basic_rag/ingest.py` | Basic ingestion, and the **single source of truth** for `EMBEDDING_MODEL` (`BAAI/bge-small-en-v1.5`, 384-dim, with a query prompt), `CHUNK_SIZE`/`CHUNK_OVERLAP` (1200/200) and `DB_NAME`. Writes Chroma at `legacy/vector_db/` (~330 chunks). Stores `source` as a path relative to `data/insurellm/` (e.g. `products/Carllm.md`). |
| `legacy/basic_rag/answer.py` | Basic RAG. Retrieves k=6 chunks for the current question plus the last 2 user turns (current question first), sends the last 6 history messages, and answers with `groq/openai/gpt-oss-120b` at temperature 0 via litellm, with tenacity retries on rate limits. Exposes `answer_question`, `stream_answer` and `fetch_context`. |
| `legacy/pro_rag/embeddings.py` | Local bge-small embeddings for the pro pipeline. |
| `legacy/pro_rag/ingest.py` | Pro ingestion. `groq/openai/gpt-oss-20b` splits each document into chunks (headline + summary + original text); long documents are sent in parts. The script is resumable through a cache in `legacy/preprocessed_db/chunk_cache/`. Writes Chroma `legacy/preprocessed_db/` (collection `docs`). |
| `legacy/pro_rag/answer.py` | Pro RAG: a history-aware query rewrite (gpt-oss-20b), then vector search on the original and the rewritten query plus BM25 keyword search, merged and reranked by a local cross-encoder (`ms-marco-MiniLM-L-6-v2`), keeping the top 10. Answers with gpt-oss-120b. Same interface as basic, including `stream_answer`; its docs are pydantic `Result` objects with `.page_content` and `.metadata`. |
| `evaluation/tests.jsonl` | 150 test questions with keywords, a reference answer and a category (direct_fact, temporal, comparative, numerical, relationship, spanning, holistic). |
| `evaluation/eval.py` | Retrieval metrics (MRR, nDCG, keyword coverage) and an LLM-as-judge answer score (accuracy, completeness, relevance, 1–5). The judge is `groq/qwen/qwen3.8-27b` at temperature 0, a different model family from the answerer. `--impl engine|basic|pro` picks the pipeline (default `engine`). Questions are loaded by `evaluation/question_set.py`. Batch runs save JSON to `evaluation/results/<label>.json`. |
| `evaluation/results/` | Saved eval runs: current ones at the top level (`engine_*_gpt41mini`, `engine_tune_*`, `openai_spend.json`); early runs (`baseline_*`, `after_bge_*`, `new_*`, `engine_v1_*`) in `results/archive/`. |
| `legacy/evaluator_dashboard.py` | Old Gradio dashboard for running the evals (`python -m legacy.evaluator_dashboard`). |
| `data/insurellm/{company,contracts,employees,products}/*.md` | Source documents (76 files, about 310K characters). The folder name becomes the `doc_type` metadata. |
| `engine_data/`, `legacy/vector_db/`, `legacy/preprocessed_db/` | Generated Chroma DBs. They are gitignored; rebuild them with the ingest commands. |

## Commands

Run everything from `ai-knowledge-assistant/` so that the package imports resolve (run scripts inside subfolders with `python -m`). This is Windows; the repo root path `D:\cllg\Project 1` contains a space, so quote it.

```powershell
cd "D:\cllg\Project 1\ai-knowledge-assistant"
.\.venv\Scripts\Activate.ps1

python -m answer_engine.pipeline ingest data/insurellm   # index the demo documents into engine_data/ (free, ~1 min)
python app.py                                      # chat UI (answer_engine)
python -m pytest answer_engine/tests -q            # 112 tests
python legacy/basic_rag/ingest.py                  # rebuild legacy/vector_db/ (~20 s, free)
python legacy/pro_rag/ingest.py                    # build legacy/preprocessed_db/ (~30-40 min on Groq free tier; resumable)
python -m legacy.basic_app                         # legacy chat UI
python -m legacy.evaluator_dashboard               # legacy evaluation dashboard
python -m evaluation.eval 0 --retrieval-only       # check retrieval for one test row (free; without the flag it also answers + judges)
python -m evaluation.eval all --retrieval-only --label X        # all 150, retrieval only: local, free, ~1-2 min
python -m evaluation.eval all --limit 30 --label X              # engine answers + judge on an evenly spaced subset (OpenAI cost, ~4 min)
python -m evaluation.eval all --split tune --label X              # engine answers on the tune split (OpenAI cost)
python -m evaluation.eval all --impl pro --label X              # same, against the pro pipeline
```

Dependencies are pinned in `requirements.txt` (exact versions tested in `.venv`); `requirements-dev.txt` adds `pytest` and `fpdf2` for the tests. Add any new package there with its exact version.

## Environment

Keys are read from `ai-knowledge-assistant/.env` via `python-dotenv`: `OPENAI_API_KEY` (answers in `answer_engine`), `GROQ_API_KEY` (helper, eval judge, legacy pipelines), `GEMINI_API_KEY` (unused), and `HF_TOKEN`. **Never print, commit, or copy `.env`.** On Hugging Face, set these as Space secrets.

## Working rules

- **Measure before and after every change.** Record a baseline first, then compare against it. Retrieval-only evals are free. Answer evals on the engine cost OpenAI credit (~$0.20–0.25 per 150 questions) plus Groq quota for the judge, so run them deliberately.
- **Use 150 questions for answer-accuracy claims.** On 30, one question is worth 3.3%. Don't tune on the same questions you report: keep a held-out split.
- **No document-specific tricks.** Every accuracy technique must work for any client's uploaded documents.
- The embedding model at ingest and at query time **must match**. Change `EMBEDDING_MODEL` only in `answer_engine/config.py` (legacy: `legacy/basic_rag/ingest.py`, `legacy/pro_rag/embeddings.py`), then re-ingest.
- Gradio is pinned to 5.50 in the Space requirements. `app.py` relies on 5.x APIs (`type="messages"`, `show_copy_button`).
- **Git:** the repo root is `D:\cllg\Project 1` and it's pushed to `github.com/Abdulhaq13/insurellm-knowledge-assistant-2`. Commit **each** logical change with a short, simple message and push. Stage files by explicit path, never `git add .`, because several Claude terminals may work in parallel, each owning different files. `.gitignore` excludes `.env`, `.venv`, caches and the generated vector DBs.
- Before making changes for the user, list the complete set of proposed changes and get approval.
