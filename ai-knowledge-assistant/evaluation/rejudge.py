"""Re-grade the saved answers of an eval run with another judge model, so several runs can be
compared under the same judge. Answers are never regenerated (no answer-model cost); only the
judge is called. Resumable: re-run with the same --label to continue.

    python -m evaluation.rejudge engine_holdout_gpt41mini --judge-model groq/<model> --label engine_holdout_rejudged
"""
import argparse
import json
import sys
from pathlib import Path

import evaluation.eval as ev
from evaluation.question_set import load_tests


def main():
    parser = argparse.ArgumentParser(description="Re-judge saved answers with a different judge model.")
    parser.add_argument("source", help="label (or path) of an answer run in evaluation/results/")
    parser.add_argument("--judge-model", required=True)
    parser.add_argument("--label", required=True, help="output label (evaluation/results/<label>.json)")
    args = parser.parse_args()

    if args.judge_model.startswith(("openai/", "gpt-")):
        sys.exit("Refusing an OpenAI judge: the answers come from OpenAI; ask before changing this.")
    source = Path(args.source) if Path(args.source).exists() else ev.RESULTS_DIR / f"{args.source}.json"
    data = json.loads(source.read_text(encoding="utf-8"))
    rows = [r for r in data["rows"] if "answer" in r]
    if not rows:
        sys.exit(f"{source} has no saved answers to re-judge")

    out = ev.RESULTS_DIR / f"{args.label}.json"
    previous = json.loads(out.read_text(encoding="utf-8"))["rows"] if out.exists() else []
    done = {r["question"] for r in previous}
    tests = {test.question: test for test in load_tests()}  # older runs have no row index
    ev.JUDGE_MODEL = args.judge_model  # judge_answer reads the module-level constant
    ev.use_implementation(data["summary"]["impl"])
    if data["summary"].get("answer_model"):
        ev.set_answer_model(data["summary"]["answer_model"])  # so the summary reports the real answerer

    metrics = ["mrr", "ndcg", "keyword_coverage", "accuracy", "completeness", "relevance"]
    settings = {**{k: data["summary"].get(k) for k in ("impl", "split", "limit", "answer_model")},
                "label": args.label, "retrieval_only": False, "rejudged_from": source.stem}
    new_rows, error = list(previous), None
    try:
        for count, row in enumerate([r for r in rows if r["question"] not in done], start=len(done) + 1):
            judged = ev.judge_answer(tests[row["question"]], row["answer"])
            new_rows.append({**row, **judged.model_dump(include={"accuracy", "completeness", "relevance", "feedback"})})
            ev.write_results(out, new_rows, settings, metrics, None, len(rows), 0.0)
            print(f"[{count}/{len(rows)}] {row['category']:<14} acc={judged.accuracy:.0f}", flush=True)
    except (Exception, KeyboardInterrupt) as e:
        error = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"Stopped after {len(new_rows)} -> {error}\nRe-run the same command to continue.", file=sys.stderr)

    new_rows.sort(key=lambda r: r.get("index", 0))
    summary = ev.write_results(out, new_rows, settings, metrics, error, len(rows), 0.0)
    print(json.dumps(summary["overall"], indent=2))
    print(f"Saved {out}")


if __name__ == "__main__":
    main()
