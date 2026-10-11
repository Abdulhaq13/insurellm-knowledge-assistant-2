"""Print every failed answer (accuracy <= 3) from a saved eval run, split into retrieval misses
(some keyword never reached the model) and answer mistakes (the right context was there).

Local file reading only, no API calls:
    python -m evaluation.failures evaluation/results/basic_answers_150.json
    python -m evaluation.failures basic_answers_150 --category spanning
"""
import argparse
import json
import sys
import textwrap
from collections import Counter
from pathlib import Path

from evaluation.test import load_tests

RESULTS_DIR = Path(__file__).parent / "results"
FAIL_ACCURACY = 3  # matches eval.py: an answer passes with accuracy >= 4


def resolve(path_or_label: str) -> Path:
    path = Path(path_or_label)
    if path.exists():
        return path
    path = RESULTS_DIR / f"{path_or_label.removesuffix('.json')}.json"
    if path.exists():
        return path
    sys.exit(f"No results file found for {path_or_label!r}")


def block(title: str, text: str, width: int = 100) -> str:
    body = "\n".join(
        textwrap.fill(line, width, initial_indent="    ", subsequent_indent="    ") or ""
        for line in str(text).strip().splitlines()
    )
    return f"  {title}:\n{body}"


def main():
    parser = argparse.ArgumentParser(description="List failed answers from an eval results JSON.")
    parser.add_argument("results", help="results JSON path, or a label in evaluation/results/")
    parser.add_argument("--category", help="only show this category")
    args = parser.parse_args()

    data = json.loads(resolve(args.results).read_text(encoding="utf-8"))
    rows = data["rows"]
    if not rows or "accuracy" not in rows[0]:
        sys.exit("This is a retrieval-only run; there are no graded answers.")

    tests = {test.question: test for test in load_tests()}  # old runs have no row index
    failed = [r for r in rows if r["accuracy"] <= FAIL_ACCURACY]
    if args.category:
        failed = [r for r in failed if r["category"] == args.category]

    for r in failed:
        test = tests.get(r["question"])
        # Older runs have no retrieval_complete flag; full keyword coverage means the same thing
        complete = r.get("retrieval_complete", r["keyword_coverage"] >= 100)
        kind = "ANSWER MISTAKE (context had all keywords)" if complete else "RETRIEVAL MISS"
        print("=" * 100)
        print(f"#{r.get('index', '?')}  [{r['category']}]  accuracy={r['accuracy']:.0f}  "
              f"completeness={r['completeness']:.0f}  coverage={r['keyword_coverage']:.0f}%  -> {kind}")
        print(block("Question", r["question"]))
        if test:
            print(block("Keywords", ", ".join(test.keywords)))
            print(block("Reference", test.reference_answer))
        print(block("Generated", r.get("answer", "")))
        print(block("Judge feedback", r.get("feedback", "")))

    total = len([r for r in rows if not args.category or r["category"] == args.category])
    kinds = Counter(
        "answer mistake" if r.get("retrieval_complete", r["keyword_coverage"] >= 100) else "retrieval miss"
        for r in failed
    )
    print("=" * 100)
    print(f"{len(failed)} of {total} answers failed (accuracy <= {FAIL_ACCURACY}): "
          f"{kinds['retrieval miss']} retrieval misses, {kinds['answer mistake']} answer mistakes")
    for category, count in sorted(Counter(r["category"] for r in failed).items(), key=lambda kv: -kv[1]):
        print(f"  {category:<14} {count}")


if __name__ == "__main__":
    main()
