"""Old vs new retrieval on Terminal B's holdout split (evaluation.eval.split_tests("holdout"), 50 tests).
Reads saved per-question results only: no models, no API calls. Run from "AI knowledge Assisstant/":

    python -m answer_engine.tests.bench_holdout [new run label]

Caveat: the new pipeline's settings were chosen while looking at results for all 150 tests, so this split
was not truly unseen. Report-only: don't change settings based on this output.
"""
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from answer_engine.config import ROOT
from evaluation.eval import split_tests

RESULTS_DIR = Path(__file__).parent / "bench_results"
BASELINE = ROOT / "evaluation" / "results" / "after_bge_1200_k6_retrieval.json"
METRICS = ["mrr", "ndcg", "keyword_coverage"]


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def bootstrap_interval(diffs: list[float], rounds: int = 10000, seed: int = 0) -> tuple[float, float]:
    rng = random.Random(seed)
    means = sorted(mean(rng.choices(diffs, k=len(diffs))) for _ in range(rounds))
    return means[int(rounds * 0.025)], means[int(rounds * 0.975)]


def main():
    run = sys.argv[1] if len(sys.argv) > 1 else "d_final_hybrid_list"
    questions = [test.question for _, test in split_tests("holdout")]
    old = {r["question"]: r for r in json.loads(BASELINE.read_text(encoding="utf-8"))["rows"]}
    new = {r["question"]: r for r in json.loads((RESULTS_DIR / f"{run}.json").read_text(encoding="utf-8"))["rows"]}
    views = {"old (basic)": lambda q: old[q], "new": lambda q: new[q]["all"], "new, first 6": lambda q: new[q]["first_k"]}

    groups = defaultdict(list)
    for q in questions:
        groups["OVERALL"].append(q)
        groups[old[q]["category"]].append(q)

    print(f"Holdout split: {len(questions)} tests. New run: {run}\n")
    print(f"{'category':<14}{'n':>3}  " + "".join(f"{m + ' ' + v:>26}" for m in METRICS for v in ["old", "new"]))
    for name in ["OVERALL"] + sorted(k for k in groups if k != "OVERALL"):
        qs = groups[name]
        cells = "".join(f"{mean([views[v](q)[m] for q in qs]):>26.4f}" for m in METRICS for v in ["old (basic)", "new"])
        print(f"{name:<14}{len(qs):>3}  {cells}")

    first6 = {m: mean([views["new, first 6"](q)[m] for q in questions]) for m in METRICS}
    print("\nnew, first 6 chunks only (same size as basic): " + ", ".join(f"{m} {v:.4f}" for m, v in first6.items()))
    diffs = [new[q]["all"]["mrr"] - old[q]["mrr"] for q in questions]
    low, high = bootstrap_interval(diffs)
    wins = sum(d > 1e-9 for d in diffs)
    losses = sum(d < -1e-9 for d in diffs)
    print(f"MRR gain new - old: {mean(diffs):+.4f}, 95% CI [{low:+.4f}, {high:+.4f}]; "
          f"{wins} better, {losses} worse, {len(diffs) - wins - losses} same")


if __name__ == "__main__":
    main()
