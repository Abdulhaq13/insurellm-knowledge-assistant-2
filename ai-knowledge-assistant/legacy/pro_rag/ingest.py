import argparse
import json
import re
import sys
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from chromadb import PersistentClient
from tqdm import tqdm
from litellm import completion
from litellm.exceptions import RateLimitError
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

sys.path.insert(0, str(Path(__file__).parents[2]))  # allow running as a script
from legacy.pro_rag.embeddings import embed_documents


load_dotenv(override=True)

MODEL = "groq/openai/gpt-oss-20b"

ROOT = Path(__file__).parent.parent
DB_NAME = str(ROOT / "preprocessed_db")
CACHE_PATH = ROOT / "preprocessed_db" / "chunk_cache"
collection_name = "docs"
KNOWLEDGE_BASE_PATH = ROOT.parent / "data" / "insurellm"
AVERAGE_CHUNK_SIZE = 100
# Groq free tier allows ~8K tokens/minute, so long documents are sent in parts of this size
MAX_PART_CHARS = 6000
# Longest rate-limit pause worth waiting for; beyond this (daily quota) we stop and resume later
MAX_RATE_LIMIT_WAIT = 600

WORKERS = 1


class DailyLimitReached(Exception):
    pass


class Result(BaseModel):
    page_content: str
    metadata: dict


class Chunk(BaseModel):
    headline: str = Field(
        description="A brief heading for this chunk, typically a few words, that is most likely to be surfaced in a query",
    )
    summary: str = Field(
        description="A few sentences summarizing the content of this chunk to answer common questions"
    )
    original_text: str = Field(
        description="The original text of this chunk from the provided document, exactly as is, not changed in any way"
    )

    def as_result(self, document):
        metadata = {"source": document["source"], "type": document["type"]}
        return Result(
            page_content=self.headline + "\n\n" + self.summary + "\n\n" + self.original_text,
            metadata=metadata,
        )


class Chunks(BaseModel):
    chunks: list[Chunk]


def fetch_documents():
    """A homemade version of the LangChain DirectoryLoader"""

    documents = []

    for folder in KNOWLEDGE_BASE_PATH.iterdir():
        doc_type = folder.name
        for file in folder.rglob("*.md"):
            with open(file, "r", encoding="utf-8") as f:
                source = file.relative_to(ROOT).as_posix()
                documents.append({"type": doc_type, "source": source, "text": f.read()})

    print(f"Loaded {len(documents)} documents")
    return documents


def split_document(document):
    """Split a long document on paragraph boundaries into parts of at most MAX_PART_CHARS."""
    parts, current = [], ""
    for paragraph in document["text"].split("\n\n"):
        if current and len(current) + len(paragraph) > MAX_PART_CHARS:
            parts.append(current)
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        parts.append(current)
    return [
        {**document, "text": text, "part": index, "parts": len(parts)}
        for index, text in enumerate(parts)
    ]


def cache_file(part):
    name = re.sub(r"[^\w-]+", "_", Path(part["source"]).stem)
    return CACHE_PATH / f"{part['type']}__{name}__{part['part']}.json"


def make_prompt(document):
    how_many = (len(document["text"]) // AVERAGE_CHUNK_SIZE) + 1
    part_note = ""
    if document["parts"] > 1:
        part_note = f"\nThis is part {document['part'] + 1} of {document['parts']} of the document.\n"
    return f"""
You take a document and you split the document into overlapping chunks for a KnowledgeBase.

The document is from the shared drive of a company called Insurellm.
The document is of type: {document["type"]}
The document has been retrieved from: {document["source"]}
{part_note}
A chatbot will use these chunks to answer questions about the company.
You should divide up the document as you see fit, being sure that the entire document is returned across the chunks - don't leave anything out.
This document should probably be split into at least {how_many} chunks, but you can have more or less as appropriate, ensuring that there are individual chunks to answer specific questions.
There should be overlap between the chunks as appropriate; typically about 25% overlap or about 50 words, so you have the same text in multiple chunks for best retrieval results.

For each chunk, you should provide a headline, a summary, and the original text of the chunk.
Together your chunks should represent the entire document with overlap.

Here is the document:

{document["text"]}

Respond with the chunks.
"""


def make_messages(document):
    return [
        {"role": "user", "content": make_prompt(document)},
    ]


def retry_after_seconds(message):
    """Parse Groq's 'Please try again in 1m2.5s' hint; 0 if absent."""
    match = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)(ms|s))?", message)
    if not match or not any(match.groups()):
        return 0.0
    h, m, value, unit = match.groups()
    seconds = float(value or 0) / (1000 if unit == "ms" else 1)
    return int(h or 0) * 3600 + int(m or 0) * 60 + seconds


_backoff = wait_exponential(multiplier=1, min=10, max=120)


def wait_for_rate_limit(retry_state):
    """Wait at least as long as the provider asks, else exponential backoff."""
    hint = retry_after_seconds(str(retry_state.outcome.exception()))
    return max(hint + 1, _backoff(retry_state))


@retry(
    wait=wait_for_rate_limit,
    stop=stop_after_attempt(5),
    retry=retry_if_not_exception_type(DailyLimitReached),
    reraise=True,
)
def process_document(document):
    messages = make_messages(document)
    try:
        response = completion(
            model=MODEL, messages=messages, response_format=Chunks, reasoning_effort="low"
        )
    except RateLimitError as e:
        wait_hint = retry_after_seconds(str(e))
        daily = "per day" in str(e).lower()
        if wait_hint > MAX_RATE_LIMIT_WAIT or (daily and not wait_hint):
            raise DailyLimitReached(str(e)[:300]) from e
        raise
    reply = response.choices[0].message.content
    doc_as_chunks = Chunks.model_validate_json(reply).chunks
    return [chunk.as_result(document) for chunk in doc_as_chunks]


def create_chunks(documents, limit=None):
    """
    Chunk every document part with the LLM, caching each part's chunks on disk so an
    interrupted run (rate limits, daily quota) resumes where it left off.
    Returns (chunks, number_of_parts_still_missing).
    """
    CACHE_PATH.mkdir(parents=True, exist_ok=True)
    parts = [part for document in documents for part in split_document(document)]
    todo = sorted((p for p in parts if not cache_file(p).exists()), key=lambda p: len(p["text"]))
    print(f"{len(parts)} parts, {len(parts) - len(todo)} cached, {len(todo)} to process")
    if limit is not None:
        todo = todo[:limit]

    for part in tqdm(todo):
        try:
            results = process_document(part)
        except DailyLimitReached as e:
            print(f"\nStopping: Groq quota exhausted for now -> {e}\nRe-run later to resume.")
            break
        except Exception as e:
            print(f"\nSkipping {part['source']} part {part['part']}: {type(e).__name__}: {str(e)[:200]}")
            continue
        cache_file(part).write_text(
            json.dumps([r.model_dump() for r in results], indent=1), encoding="utf-8"
        )

    chunks, missing = [], 0
    for part in parts:
        path = cache_file(part)
        if path.exists():
            chunks.extend(Result(**r) for r in json.loads(path.read_text(encoding="utf-8")))
        else:
            missing += 1
    return chunks, missing


def create_embeddings(chunks):
    chroma = PersistentClient(path=DB_NAME)
    if collection_name in [c.name for c in chroma.list_collections()]:
        chroma.delete_collection(collection_name)

    texts = [chunk.page_content for chunk in chunks]
    vectors = embed_documents(texts)

    collection = chroma.get_or_create_collection(collection_name)

    ids = [str(i) for i in range(len(chunks))]
    metas = [chunk.metadata for chunk in chunks]

    collection.add(ids=ids, embeddings=vectors, documents=texts, metadatas=metas)
    print(f"Vectorstore created with {collection.count()} documents")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build preprocessed_db with LLM chunking.")
    parser.add_argument("--limit", type=int, help="process at most N uncached parts (smoke test)")
    parser.add_argument("--partial", action="store_true", help="build the DB even if some parts are missing")
    args = parser.parse_args()

    documents = fetch_documents()
    chunks, missing = create_chunks(documents, args.limit)
    if missing and not args.partial:
        print(f"{missing} parts still missing; DB not built. Re-run to resume, or pass --partial.")
        sys.exit(1)
    create_embeddings(chunks)
    print("Ingestion complete" + (f" ({missing} parts missing)" if missing else ""))
