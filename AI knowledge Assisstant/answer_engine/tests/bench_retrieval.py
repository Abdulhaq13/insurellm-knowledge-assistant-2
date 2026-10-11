"""Retrieval benchmark: ingest knowledge-base/ into a throwaway client and score all 150 tests. Local and free
(no API calls unless --decompose). Run from "AI knowledge Assisstant/":

    python -m answer_engine.tests.bench_retrieval --label X [--no-list-extra] [--decompose]
"""
import argparse
import hashlib
import json
import re
import shutil
import tempfile
import time
from collections import defaultdict
from pathlib import Path

from answer_engine import retrieval
from answer_engine.config import FINAL_K, ROOT
from answer_engine.index import ClientIndex
from answer_engine.schema import LoadedDocument, Section
from evaluation.eval import score_retrieval
from evaluation.test import load_tests


KNOWLEDGE_BASE = ROOT / "knowledge-base"
BASELINE = ROOT / "evaluation" / "results" / "after_bge_1200_k6_retrieval.json"
RESULTS_DIR = Path(__file__).parent / "bench_results"
METRICS = ["mrr", "ndcg", "keyword_coverage"]
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")


def load_markdown(path: Path, doc_id: str) -> LoadedDocument:
    """Generic Markdown loader (stand-in until loaders.py exists): headings -> sections, pipe tables -> table sections."""
    raw = path.read_bytes()
    stack: list[tuple[int, str]] = []
    sections: list[Section] = []
    block: list[str] = []
    block_kind = "text"

    def flush():
        nonlocal block
        text = "\n".join(block).strip()
        if text:
            sections.append(Section(heading_path=[h for _, h in stack], text=text, kind=block_kind))
        block = []

    for line in raw.decode("utf-8", errors="replace").splitlines():
        heading = HEADING.match(line)
        if heading:
            flush()
            level = len(heading.group(1))
            stack = [(l, h) for l, h in stack if l < level] + [(level, heading.group(2).strip())]
            continue
        kind = "table" if line.lstrip().startswith("|") else "text"
        if kind != block_kind and line.strip():
            flush()
            block_kind = kind
        block.append(line)
    flush()
    return LoadedDocument(
        doc_id=doc_id, title=path.stem, source=doc_id, file_type="md", sections=sections,
        content_hash=hashlib.sha256(raw).hexdigest(), metadata={"doc_type": Path(doc_id).parts[0]},
    )


def ingest(index: ClientIndex) -> int:
    paths = sorted(KNOWLEDGE_BASE.rglob("*.md"))
    return sum(index.upsert_document(load_markdown(p, p.relative_to(KNOWLEDGE_BASE).as_posix())) for p in paths)


def summarize(rows: list[dict], key: str) -> dict:
    def mean(values):
        return round(sum(values) / len(values), 4)

    by_category = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row[key])
    return {
        "overall": {m: mean([r[key][m] for r in rows]) for m in METRICS},
        "by_category": {c: {m: mean([s[m] for s in v]) for m in METRICS} for c, v in sorted(by_category.items())},
    }


def print_table(name: str, summary: dict, baseline: dict):
    print(f"\n{name}")
    print(f"{'category':<14}" + "".join(f"{m:>22}" for m in METRICS))
    groups = [("OVERALL", summary["overall"], baseline["overall"])] + [
        (c, s, baseline["by_category"].get(c, {})) for c, s in summary["by_category"].items()
    ]
    for label, ours, base in groups:
        cells = ""
        for m in METRICS:
            b = base.get(m)
            cells += f"{ours[m]:>10.4f} ({ours[m] - b:+.4f})" if b is not None else f"{ours[m]:>22.4f}"
        print(f"{label:<14}{cells}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", default="bench")

    parser.add_argument("--no-list-extra", action="store_true", help="no extra chunks for list-style questions")
    parser.add_argument("--decompose", action="store_true", help="LLM sub-questions (uses Groq HELPER_MODEL quota)")
    parser.add_argument("--limit", type=int, help="only the first N tests")
    args = parser.parse_args()
    if args.no_list_extra:
        retrieval.LIST_EXTRA_K = 0
    retrieval.DECOMPOSE = args.decompose

    data_dir = Path(tempfile.mkdtemp(prefix="bench_"))
    try:
        index = ClientIndex("bench", data_dir)
        start = time.time()
        chunks = ingest(index)
        print(f"Ingested {len(index.list_documents())} documents, {chunks} chunks in {time.time() - start:.1f}s")

        tests = load_tests()[: args.limit]
        rows = []
        start = time.time()
        for test in tests:
            docs = retrieval.retrieve(index, test.question, [])
            rows.append({
                "question": test.question,
                "category": test.category,
                "returned": len(docs),
                "sources": [d.metadata["source"] for d in docs],
                "all": score_retrieval(test, docs).model_dump(include=set(METRICS)),
                "first_k": score_retrieval(test, docs[:FINAL_K]).model_dump(include=set(METRICS)),
            })
        seconds = time.time() - start
    finally:
        del index
        shutil.rmtree(data_dir, ignore_errors=True)

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))["summary"]
    result = {
        "label": args.label,
        "settings": {"list_extra_k": retrieval.LIST_EXTRA_K,
                     "decompose": retrieval.DECOMPOSE, "final_k": FINAL_K},
        "chunks": chunks,
        "tests": len(rows),
        "avg_chunks_returned": round(sum(r["returned"] for r in rows) / len(rows), 2),
        "seconds_per_question": round(seconds / len(rows), 3),
        "all_returned": summarize(rows, "all"),
        f"first_{FINAL_K}": summarize(rows, "first_k"),
    }
    print_table(f"All returned chunks (avg {result['avg_chunks_returned']}) vs basic", result["all_returned"], baseline)
    print_table(f"First {FINAL_K} chunks only vs basic", result[f"first_{FINAL_K}"], baseline)
    print(f"\n{result['seconds_per_question']}s per question")

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{args.label}.json"
    path.write_text(json.dumps({"summary": result, "rows": rows}, indent=2), encoding="utf-8")
    print(f"Saved {path}")


if __name__ == "__main__":
    main()
