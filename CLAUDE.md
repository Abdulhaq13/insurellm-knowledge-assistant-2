# CLAUDE.md

This file gives Claude Code guidance for working in this repository.

## What this is

A RAG (retrieval-augmented generation) assistant that answers questions from a set of documents. Today it answers about **Insurellm**, a fictional insurance-tech company whose knowledge base is a folder of Markdown files. It started from Week 5 of the "LLM Engineering" course and is the user's college project.

**Where it is heading** (the user's decision on 2026-10-11, in this order):
1. **Accuracy first.** Get answer accuracy above 90% using *general* techniques that work on any documents. Never hard-code anything about specific documents (no parsers for "the employee file format", no Insurellm-specific rules), because clients will upload their own files.
2. **Then a multi-client platform ("Option 1").** One codebase. Each client organisation gets its own assistant with a separate document collection, its own admins (who upload, replace and delete documents) and its own employees/users (who only ask questions). Clients must never see each other's data. The user is the platform owner.
3. **All file types** (PDF, Word, Excel, text, Markdown). Cost and latency must stay low.

There are two top-level folders:

- `AI knowledge Assisstant/` is the main development project: app, two RAG pipelines, evaluation harness, knowledge base and a local `.venv` (Python 3.13).
- `Huggig face space/Space 1/` is the deployment copy for a Hugging Face Space. It is **stale**: it still has the original MiniLM / OpenAI code and the old `vector_db/`. It gets synced once the pipeline choice is final. Never copy `.env` into it.

`AI knowledge Assisstant/community-contributions/` (~26 MB) holds other students' course submissions. It is not part of this app. Ignore it unless asked.

## Cost rule: free tier first

Use only free models until the product is final and has real users: Groq free tier for LLMs, plus local sentence-transformers / cross-encoder models. Keep every model name in one constant so moving to paid models later is a one-line change. Groq free limits are **per model, shared across the whole account**: about 8,000 tokens/minute and 1,000 requests/day. Two processes calling the same model slow each other down. Gemini's free tier is ~20 requests/day per model, which is unusable for evals.

## Layout (inside `AI knowledge Assisstant/`)

| Path | Role |
|---|---|
| `app.py` | Gradio chat UI. The chat streams on the left, and the retrieved chunks and their sources show on the right. Uses `implementation.answer.stream_answer`. |
| `implementation/ingest.py` | Basic ingestion, and the **single source of truth** for `EMBEDDING_MODEL` (`BAAI/bge-small-en-v1.5`, 384-dim, with a query prompt), `CHUNK_SIZE`/`CHUNK_OVERLAP` (1200/200) and `DB_NAME`. Writes Chroma at `vector_db/` (~330 chunks). Stores `source` as a path relative to `knowledge-base/` (e.g. `products/Carllm.md`). |
| `implementation/answer.py` | Basic RAG. Retrieves k=6 chunks for the current question plus the last 2 user turns (current question first), sends the last 6 history messages, and answers with `groq/openai/gpt-oss-120b` at temperature 0 via litellm, with tenacity retries on rate limits. Exposes `answer_question`, `stream_answer` and `fetch_context`. |
| `pro_implementation/embeddings.py` | Local bge-small embeddings for the pro pipeline. |
| `pro_implementation/ingest.py` | Pro ingestion. `groq/openai/gpt-oss-20b` splits each document into chunks (headline + summary + original text); long documents are sent in parts. The script is resumable through a cache in `preprocessed_db/chunk_cache/`. Writes Chroma `preprocessed_db/` (collection `docs`). |
| `pro_implementation/answer.py` | Pro RAG: a history-aware query rewrite (gpt-oss-20b), then vector search on the original and the rewritten query plus BM25 keyword search, merged and reranked by a local cross-encoder (`ms-marco-MiniLM-L-6-v2`), keeping the top 10. Answers with gpt-oss-120b. Same interface as basic, including `stream_answer`; its docs are pydantic `Result` objects with `.page_content` and `.metadata`. |
| `evaluation/tests.jsonl` | 150 test questions with keywords, a reference answer and a category (direct_fact, temporal, comparative, numerical, relationship, spanning, holistic). |
| `evaluation/eval.py` | Retrieval metrics (MRR, nDCG, keyword coverage) and an LLM-as-judge answer score (accuracy, completeness, relevance, 1–5). The judge is `groq/qwen/qwen3.8-27b` at temperature 0, a different model family from the answerer. `--impl basic|pro` picks the pipeline. Batch runs save JSON to `evaluation/results/<label>.json`. |
| `evaluation/results/` | Saved eval runs. `baseline_*` is the original setup and `after_bge_1200_k6_*` is the current basic pipeline. |
| `evaluator.py` | Gradio dashboard for running the evals. |
| `knowledge-base/{company,contracts,employees,products}/*.md` | Source documents (76 files, about 310K characters). The folder name becomes the `doc_type` metadata. |
| `vector_db/`, `preprocessed_db/` | Generated Chroma DBs. They are gitignored; rebuild them with the ingest scripts. |

## Commands

Run everything from `AI knowledge Assisstant/` so that the package imports resolve. This is Windows, and paths contain spaces, so quote them.

```powershell
cd "D:\cllg\Project 1\AI knowledge Assisstant"
.\.venv\Scripts\Activate.ps1

python implementation/ingest.py                    # rebuild vector_db/ (~20 s, free; needed after any KB or chunking change)
python pro_implementation/ingest.py                # build preprocessed_db/ (~30-40 min on Groq free tier; resumable)
python app.py                                      # chat UI
python evaluator.py                                # evaluation dashboard
python -m evaluation.eval 0                        # evaluate one test row
python -m evaluation.eval all --retrieval-only --label X        # all 150, retrieval only: local, free, ~2 s
python -m evaluation.eval all --limit 30 --label X              # answers + judge on an evenly spaced subset (~4 min)
python -m evaluation.eval all --impl pro --label X              # same, against the pro pipeline
```

Dependencies are pinned in `requirements.txt` (exact versions tested in `.venv`); `requirements-dev.txt` adds `pytest` and `fpdf2` for the tests. Add any new package there with its exact version.

## Environment

Keys are read from `AI knowledge Assisstant/.env` via `python-dotenv`: `GROQ_API_KEY` (used by everything now), `GEMINI_API_KEY`, `OPENAI_API_KEY` (not used while on the free tier), and `HF_TOKEN`. **Never print, commit, or copy `.env`.** On Hugging Face, set these as Space secrets.

## Working rules

- **Measure before and after every change.** Record a baseline first, then compare against it. Retrieval-only evals are free; answer evals use Groq quota.
- **Use 150 questions for answer-accuracy claims.** On 30, one question is worth 3.3%. Don't tune on the same questions you report: keep a held-out split.
- **No document-specific tricks.** Every accuracy technique must work for any client's uploaded documents.
- The embedding model at ingest and at query time **must match**. Change `EMBEDDING_MODEL` only in `implementation/ingest.py` (or `pro_implementation/embeddings.py`), then re-ingest.
- Gradio is pinned to 5.50 in the Space requirements. `app.py` relies on 5.x APIs (`type="messages"`, `show_copy_button`).
- **Git:** the repo root is `D:\cllg\Project 1` and it's pushed to `github.com/Abdulhaq13/insurellm-knowledge-assistant-2`. Commit **each** logical change with a short, simple message and push. Stage files by explicit path, never `git add .`, because several Claude terminals may work in parallel, each owning different files. `.gitignore` excludes `.env`, `.venv`, the vector DBs, `community-contributions` and the Space folder.
- Before making changes for the user, list the complete set of proposed changes and get approval.
