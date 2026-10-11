# CLAUDE.md

This file gives Claude Code guidance for working in this repository.

## What this is

A RAG (retrieval-augmented generation) chatbot that answers questions about **Insurellm**, a fictional insurance-tech company. The knowledge base is a folder of Markdown files. It is based on Week 5 of the "LLM Engineering" course.

There are two top-level folders:

- `AI knowledge Assisstant/` is the main development project: app, two RAG implementations, evaluation harness, knowledge base, prebuilt vector DB and a local `.venv` (Python 3.13).
- `Huggig face space/Space 1/` is the deployment copy for a Hugging Face Space. Its `app.py`, `implementation/`, `knowledge-base/` and `vector_db/` are **byte-identical copies** of the main project. If you change the main project, copy the change here too (or ask the user first).

`AI knowledge Assisstant/community-contributions/` (~26 MB) holds other students' course submissions. It is not part of this app. Ignore it unless asked.

## Layout (inside `AI knowledge Assisstant/`)

| Path | Role |
|---|---|
| `app.py` | Gradio chat UI. Left side is the chat, right side shows the retrieved chunks. Uses `implementation.answer`. |
| `implementation/ingest.py` | Basic ingestion. LangChain `DirectoryLoader` loads the files, `RecursiveCharacterTextSplitter` splits them (500/200), `all-MiniLM-L6-v2` embeds them, and the vectors go to Chroma at `vector_db/`. |
| `implementation/answer.py` | Basic RAG. Retrieves top-10 chunks (the query is all the user's prior turns plus the current question), then calls `gpt-4.1-nano` through `langchain_openai`. |
| `pro_implementation/ingest.py` | Advanced ingestion. An LLM does the chunking (headline, summary and original text), `text-embedding-3-large` embeds the chunks, and they go to `preprocessed_db/` (collection `docs`). This DB has **not been built yet**. |
| `pro_implementation/answer.py` | Advanced RAG. Rewrites the query, retrieves twice (20 each), merges the results, has an LLM rerank them and keeps the top 10. Uses litellm with `groq/openai/gpt-oss-120b`. |
| `evaluation/tests.jsonl` | 150 test questions with keywords, reference answer and category. |
| `evaluation/eval.py` | Retrieval metrics (MRR, nDCG, keyword coverage) and an LLM-as-judge answer score (accuracy, completeness and relevance, each 1–5). Imports `implementation.answer`. |
| `evaluator.py` | Gradio dashboard for running `evaluation/eval.py` over all tests. |
| `knowledge-base/{company,contracts,employees,products}/*.md` | Source documents. The folder name becomes the `doc_type` metadata. |
| `vector_db/` | Prebuilt Chroma DB (970 chunks, 384-dim). |

Both `answer.py` modules expose the same interface, `answer_question(question, history) -> (answer, docs)` and `fetch_context(question) -> docs`. To switch implementations, change the import in `app.py` / `evaluation/eval.py`. Note that `pro_implementation` returns pydantic `Result` objects, not LangChain `Document`s. They have the same `.page_content` and `.metadata` attributes.

## Commands

Run everything from `AI knowledge Assisstant/` so that the `implementation` and `evaluation` package imports resolve. This is Windows, and paths contain spaces, so quote them.

```powershell
cd "D:\cllg\Project 1\AI knowledge Assisstant"
.\.venv\Scripts\Activate.ps1

python implementation/ingest.py          # rebuild vector_db/ (needed after any knowledge-base edit)
python app.py                            # chat UI
python evaluator.py                      # evaluation dashboard
python -m evaluation.eval 0              # CLI eval of test row 0 (must be run as a module)
python pro_implementation/ingest.py      # build preprocessed_db/ (costs OpenAI calls)
```

There is no `requirements.txt` in the main project. The dependency list is in `Huggig face space/Space 1/requirements.txt`. The pro implementation and evaluation also need `litellm`, `tenacity`, `tqdm` and `pandas`.

## Environment

Keys are read from `AI knowledge Assisstant/.env` via `python-dotenv`: `OPENAI_API_KEY` (required), `GROQ_API_KEY` (pro implementation), `GEMINI_API_KEY`, `HF_TOKEN`. **Never print, commit, or copy `.env` into the Space folder.** On Hugging Face, set these as Space secrets.

## Conventions and gotchas

- The embedding model used in ingest and in answer **must match**. The basic implementation uses HuggingFace MiniLM (384-dim), and the pro implementation uses OpenAI `text-embedding-3-large`. If you switch one side, re-ingest.
- Chunk `metadata["source"]` holds the absolute path at ingest time. Right now these are Windows `D:\...` paths, and `app.py` displays them.
- Gradio is pinned to 5.50 in the Space requirements. `app.py` relies on 5.x APIs (`type="messages"`, `show_copy_button`).
- Model names are hardcoded as `MODEL` constants at the top of each module.
