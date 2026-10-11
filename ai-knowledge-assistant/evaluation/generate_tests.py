"""Write test questions for any folder of documents, in the tests.jsonl format, into a NEW file.

    python -m evaluation.generate_tests data/insurellm --out evaluation/generated_tests.jsonl
    python -m evaluation.generate_tests some/client/docs --out evaluation/client_tests.jsonl --pairs 10

Each line also records the source document(s), so an interrupted run (rate limit, daily quota)
resumes where it stopped when re-run with the same --out. Never writes to tests.jsonl.
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

import litellm
from dotenv import load_dotenv
from litellm import completion
from litellm.exceptions import RateLimitError
from pydantic import BaseModel, Field
from tenacity import retry, retry_if_not_exception_type, stop_after_attempt, wait_exponential

from evaluation.question_set import TEST_FILE

load_dotenv(override=True)
litellm.suppress_debug_info = True

MODEL = "groq/openai/gpt-oss-20b"
MAX_PART_CHARS = 6000  # keeps each request under Groq's free ~8K tokens/minute
FALLBACK_EXTENSIONS = {".md", ".txt"}
SINGLE_DOC_CATEGORIES = ["direct_fact", "numerical", "temporal", "relationship"]
PAIR_CATEGORIES = ["comparative", "spanning"]


class DailyLimitReached(Exception):
    pass


class GeneratedTest(BaseModel):
    question: str = Field(description="A question a user of this company's assistant might ask")
    keywords: list[str] = Field(
        description="2-4 short words or phrases, copied exactly from the document(s), that any passage answering the question must contain"
    )
    reference_answer: str = Field(description="A correct, complete answer using only facts from the document(s)")
    category: str = Field(description="One of the allowed categories")


class GeneratedTests(BaseModel):
    tests: list[GeneratedTest]


def load_documents(folder: Path) -> list[dict]:
    """Use the answer engine's loaders (all file types) when available, else plain .md/.txt."""
    try:
        from answer_engine.loaders import SUPPORTED_EXTENSIONS, load_file

        def read(path: Path) -> str:
            doc = load_file(path, path.relative_to(folder).as_posix())
            return "\n\n".join(section.text for section in doc.sections)

        extensions = SUPPORTED_EXTENSIONS
    except (ImportError, AttributeError):
        def read(path: Path) -> str:
            return path.read_text(encoding="utf-8", errors="replace")

        extensions = FALLBACK_EXTENSIONS

    documents = []
    for path in sorted(folder.rglob("*")):
        if path.is_file() and path.suffix.lower() in extensions:
            try:
                text = read(path)
            except NotImplementedError:  # engine loaders not built yet
                text = path.read_text(encoding="utf-8", errors="replace") if path.suffix.lower() in FALLBACK_EXTENSIONS else ""
            if text.strip():
                documents.append({"source": path.relative_to(folder).as_posix(), "text": text})
    return documents


def split_text(text: str) -> list[str]:
    parts, current = [], ""
    for paragraph in text.split("\n\n"):
        if current and len(current) + len(paragraph) > MAX_PART_CHARS:
            parts.append(current)
            current = ""
        current += paragraph + "\n\n"
    if current.strip():
        parts.append(current)
    return [part[:MAX_PART_CHARS] for part in parts]


def make_prompt(excerpts: list[tuple[str, str]], count: int, categories: list[str]) -> str:
    docs = "\n\n".join(f"### Document: {source}\n\n{text}" for source, text in excerpts)
    cross = (
        "Every question must need information from BOTH documents to answer.\n" if len(excerpts) > 1 else ""
    )
    return f"""You write evaluation questions for a question-answering assistant that answers from a company's documents.

Write {count} varied questions that can be answered ONLY from the document text below.
{cross}Allowed categories: {", ".join(categories)}
- direct_fact: a single fact; numerical: a number, price or amount; temporal: a date or time period;
  relationship: how two people, products or organisations are connected;
  comparative: compares things across documents; spanning: combines facts from several documents.
Rules:
- Ask the question the way a real user would, naming the specific subject (never "this document").
- keywords: 2-4 short words or phrases copied EXACTLY (same spelling) from the document text, that any passage answering the question must contain.
- reference_answer: correct and complete, using only facts stated in the text. Never invent anything.

{docs}"""


def retry_after_seconds(message: str) -> float:
    match = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m(?!s))?(?:([\d.]+)(ms|s))?", message)
    if not match or not any(match.groups()):
        return 0.0
    h, m, value, unit = match.groups()
    return int(h or 0) * 3600 + int(m or 0) * 60 + float(value or 0) / (1000 if unit == "ms" else 1)


_backoff = wait_exponential(multiplier=1, min=10, max=120)


def wait_for_rate_limit(retry_state) -> float:
    return max(retry_after_seconds(str(retry_state.outcome.exception())) + 1, _backoff(retry_state))


@retry(wait=wait_for_rate_limit, stop=stop_after_attempt(5),
       retry=retry_if_not_exception_type(DailyLimitReached), reraise=True)
def generate(excerpts: list[tuple[str, str]], count: int, categories: list[str]) -> list[GeneratedTest]:
    messages = [{"role": "user", "content": make_prompt(excerpts, count, categories)}]
    try:
        response = completion(model=MODEL, messages=messages, response_format=GeneratedTests,
                              reasoning_effort="low")
    except RateLimitError as e:
        wait = retry_after_seconds(str(e))
        if wait > 600 or ("per day" in str(e).lower() and not wait):
            raise DailyLimitReached(str(e)[:300]) from e
        raise
    return GeneratedTests.model_validate_json(response.choices[0].message.content).tests


def clean(test: GeneratedTest, text: str, categories: list[str]) -> dict | None:
    """Keep only keywords that really occur in the source text; drop unusable questions."""
    lowered = text.lower()
    keywords = list(dict.fromkeys(k.strip() for k in test.keywords if k.strip() and k.strip().lower() in lowered))
    if not keywords or not test.question.strip() or not test.reference_answer.strip():
        return None
    category = test.category if test.category in categories else categories[0]
    return {"question": test.question.strip(), "keywords": keywords,
            "reference_answer": test.reference_answer.strip(), "category": category}


def main():
    parser = argparse.ArgumentParser(description="Generate tests.jsonl-style questions from a folder of documents.")
    parser.add_argument("folder", type=Path, help="folder of documents (searched recursively)")
    parser.add_argument("--out", type=Path, required=True, help="NEW .jsonl file to write (resumes if it exists)")
    parser.add_argument("--per-part", type=int, default=2, help="questions per document part (~6K chars)")
    parser.add_argument("--pairs", type=int, default=0, help="extra questions spanning two random documents")
    parser.add_argument("--limit", type=int, help="process at most N documents/pairs this run (smoke test)")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    if args.out.resolve() == Path(TEST_FILE).resolve():
        sys.exit("Refusing to write to tests.jsonl; choose another --out file.")
    documents = load_documents(args.folder)
    if not documents:
        sys.exit(f"No readable documents found in {args.folder}")

    done = set()
    if args.out.exists():
        for line in args.out.read_text(encoding="utf-8").splitlines():
            if line.strip():
                done.add(tuple(json.loads(line).get("sources", [])))
    print(f"{len(documents)} documents; {len(done)} already have questions in {args.out}")

    jobs = []  # (sources, excerpts, count, categories)
    for doc in documents:
        parts = split_text(doc["text"])
        excerpts = [(doc["source"], part) for part in parts]
        jobs.append(((doc["source"],), excerpts, args.per_part * len(parts), SINGLE_DOC_CATEGORIES))
    rng = random.Random(args.seed)
    for _ in range(args.pairs):
        a, b = rng.sample(documents, 2)
        excerpts = [(d["source"], d["text"][: MAX_PART_CHARS // 2]) for d in (a, b)]
        jobs.append(((a["source"], b["source"]), excerpts, 1, PAIR_CATEGORIES))
    jobs = [job for job in jobs if job[0] not in done]
    if args.limit is not None:
        jobs = jobs[: args.limit]

    written = 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("a", encoding="utf-8") as out:
        for index, (sources, excerpts, count, categories) in enumerate(jobs, start=1):
            # Long documents: one request per part, so each stays under the per-minute token limit
            batches = [[e] for e in excerpts] if len(sources) == 1 else [excerpts]
            per_batch = count // len(batches)
            rows = []
            try:
                for batch in batches:
                    text = "\n\n".join(t for _, t in batch)
                    rows += [r for t in generate(batch, per_batch, categories) if (r := clean(t, text, categories))]
            except DailyLimitReached as e:
                print(f"Stopping: Groq quota exhausted -> {e}\nRe-run with the same --out to resume.")
                break
            except Exception as e:
                print(f"Skipping {sources}: {type(e).__name__}: {str(e)[:200]}")
                continue
            for row in rows:
                out.write(json.dumps({**row, "sources": list(sources)}) + "\n")
            out.flush()
            written += len(rows)
            print(f"[{index}/{len(jobs)}] {' + '.join(sources)}: {len(rows)} questions", flush=True)
    print(f"Wrote {written} questions to {args.out}")


if __name__ == "__main__":
    main()
