import argparse
import importlib
import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import litellm
from pydantic import BaseModel, Field
from litellm import completion
from dotenv import load_dotenv
from tenacity import retry, stop_after_attempt, wait_exponential

from evaluation.test import TestQuestion, load_tests


load_dotenv(override=True)
litellm.suppress_debug_info = True

JUDGE_MODEL = "groq/qwen/qwen3.8-27b"
RESULTS_DIR = Path(__file__).parent / "results"
IMPLEMENTATIONS = {"basic": "implementation.answer", "pro": "pro_implementation.answer"}
_impl_name = "basic"


def use_implementation(name: str):
    """Choose which RAG implementation (basic or pro) the evaluation runs against."""
    global _impl_name
    _impl_name = name


def impl():
    # Imported lazily so only the chosen implementation (and its models / DB) gets loaded
    return importlib.import_module(IMPLEMENTATIONS[_impl_name])


class RetrievalEval(BaseModel):
    """Evaluation metrics for retrieval performance."""

    mrr: float = Field(description="Mean Reciprocal Rank - average across all keywords")
    ndcg: float = Field(description="Normalized Discounted Cumulative Gain (binary relevance)")
    keywords_found: int = Field(description="Number of keywords found in top-k results")
    total_keywords: int = Field(description="Total number of keywords to find")
    keyword_coverage: float = Field(description="Percentage of keywords found")


class AnswerEval(BaseModel):
    """LLM-as-a-judge evaluation of answer quality."""

    feedback: str = Field(
        description="Concise feedback on the answer quality, comparing it to the reference answer and evaluating based on the retrieved context"
    )
    accuracy: float = Field(
        description="How factually correct is the answer compared to the reference answer? 1 (wrong. any wrong answer must score 1) to 5 (ideal - perfectly accurate). An acceptable answer would score 3."
    )
    completeness: float = Field(
        description="How complete is the answer in addressing all aspects of the question? 1 (very poor - missing key information) to 5 (ideal - all the information from the reference answer is provided completely). Only answer 5 if ALL information from the reference answer is included."
    )
    relevance: float = Field(
        description="How relevant is the answer to the specific question asked? 1 (very poor - off-topic) to 5 (ideal - directly addresses question and gives no additional information). Only answer 5 if the answer is completely relevant to the question and gives no additional information."
    )


def calculate_mrr(keyword: str, retrieved_docs: list) -> float:
    """Calculate reciprocal rank for a single keyword (case-insensitive)."""
    keyword_lower = keyword.lower()
    for rank, doc in enumerate(retrieved_docs, start=1):
        if keyword_lower in doc.page_content.lower():
            return 1.0 / rank
    return 0.0


def calculate_dcg(relevances: list[int], k: int) -> float:
    """Calculate Discounted Cumulative Gain."""
    dcg = 0.0
    for i in range(min(k, len(relevances))):
        dcg += relevances[i] / math.log2(i + 2)  # i+2 because rank starts at 1
    return dcg


def calculate_ndcg(keyword: str, retrieved_docs: list, k: int = 10) -> float:
    """Calculate nDCG for a single keyword (binary relevance, case-insensitive)."""
    keyword_lower = keyword.lower()

    # Binary relevance: 1 if keyword found, 0 otherwise
    relevances = [
        1 if keyword_lower in doc.page_content.lower() else 0 for doc in retrieved_docs[:k]
    ]

    # DCG
    dcg = calculate_dcg(relevances, k)

    # Ideal DCG (best case: keyword in first position)
    ideal_relevances = sorted(relevances, reverse=True)
    idcg = calculate_dcg(ideal_relevances, k)

    return dcg / idcg if idcg > 0 else 0.0


def evaluate_retrieval(test: TestQuestion, k: int = 10) -> RetrievalEval:
    """
    Evaluate retrieval performance for a test question.

    Args:
        test: TestQuestion object containing question and keywords
        k: Number of top documents to retrieve (default 10)

    Returns:
        RetrievalEval object with MRR, nDCG, and keyword coverage metrics
    """
    return score_retrieval(test, impl().fetch_context(test.question), k)


def score_retrieval(test: TestQuestion, retrieved_docs: list, k: int = 10) -> RetrievalEval:
    # Calculate MRR (average across all keywords)
    mrr_scores = [calculate_mrr(keyword, retrieved_docs) for keyword in test.keywords]
    avg_mrr = sum(mrr_scores) / len(mrr_scores) if mrr_scores else 0.0

    # Calculate nDCG (average across all keywords)
    ndcg_scores = [calculate_ndcg(keyword, retrieved_docs, k) for keyword in test.keywords]
    avg_ndcg = sum(ndcg_scores) / len(ndcg_scores) if ndcg_scores else 0.0

    # Calculate keyword coverage
    keywords_found = sum(1 for score in mrr_scores if score > 0)
    total_keywords = len(test.keywords)
    keyword_coverage = (keywords_found / total_keywords * 100) if total_keywords > 0 else 0.0

    return RetrievalEval(
        mrr=avg_mrr,
        ndcg=avg_ndcg,
        keywords_found=keywords_found,
        total_keywords=total_keywords,
        keyword_coverage=keyword_coverage,
    )


def evaluate_answer(test: TestQuestion) -> tuple[AnswerEval, str, list]:
    """
    Evaluate answer quality using LLM-as-a-judge (async).

    Args:
        test: TestQuestion object containing question and reference answer

    Returns:
        Tuple of (AnswerEval object, generated_answer string, retrieved_docs list)
    """
    generated_answer, retrieved_docs = impl().answer_question(test.question)
    return judge_answer(test, generated_answer), generated_answer, retrieved_docs


@retry(wait=wait_exponential(multiplier=2, min=5, max=60), stop=stop_after_attempt(6), reraise=True)
def judge_answer(test: TestQuestion, generated_answer: str) -> AnswerEval:
    # LLM judge prompt
    judge_messages = [
        {
            "role": "system",
            "content": "You are an expert evaluator assessing the quality of answers from a chatbot for Insurellm, a fictional insurance-tech company. The knowledge base and the reference answers are all about Insurellm, so mentioning Insurellm or its products, employees and contracts is expected and is NOT a hallucination. Evaluate the generated answer by comparing it to the reference answer. Only give 5/5 scores for perfect answers.",
        },
        {
            "role": "user",
            "content": f"""Question:
{test.question}

Generated Answer:
{generated_answer}

Reference Answer:
{test.reference_answer}

Please evaluate the generated answer on three dimensions:
1. Accuracy: How factually correct is it compared to the reference answer? Only give 5/5 scores for perfect answers.
2. Completeness: How thoroughly does it address all aspects of the question, covering all the information from the reference answer?
3. Relevance: How well does it directly answer the specific question asked, giving no additional information?

Provide detailed feedback and scores from 1 (very poor) to 5 (ideal) for each dimension. If the answer is wrong, then the accuracy score must be 1.""",
        },
    ]

    judge_response = completion(
        model=JUDGE_MODEL, messages=judge_messages, response_format=AnswerEval, temperature=0
    )
    return AnswerEval.model_validate_json(judge_response.choices[0].message.content)


def evaluate_all_retrieval():
    """Evaluate all retrieval tests."""
    tests = load_tests()
    total_tests = len(tests)
    for index, test in enumerate(tests):
        result = evaluate_retrieval(test)
        progress = (index + 1) / total_tests
        yield test, result, progress


def evaluate_all_answers():
    """Evaluate all answers to tests using batched async execution."""
    tests = load_tests()
    total_tests = len(tests)
    for index, test in enumerate(tests):
        result = evaluate_answer(test)[0]
        progress = (index + 1) / total_tests
        yield test, result, progress


def run_cli_evaluation(test_number: int):
    """Run evaluation for a specific test (async helper for CLI)."""
    tests = load_tests()

    if test_number < 0 or test_number >= len(tests):
        print(f"Error: test_row_number must be between 0 and {len(tests) - 1}")
        sys.exit(1)

    # Get the test
    test = tests[test_number]

    # Print test info
    print(f"\n{'=' * 80}")
    print(f"Test #{test_number} ({_impl_name} implementation)")
    print(f"{'=' * 80}")
    print(f"Question: {test.question}")
    print(f"Keywords: {test.keywords}")
    print(f"Category: {test.category}")
    print(f"Reference Answer: {test.reference_answer}")

    # Retrieval Evaluation
    print(f"\n{'=' * 80}")
    print("Retrieval Evaluation")
    print(f"{'=' * 80}")

    retrieval_result = evaluate_retrieval(test)

    print(f"MRR: {retrieval_result.mrr:.4f}")
    print(f"nDCG: {retrieval_result.ndcg:.4f}")
    print(f"Keywords Found: {retrieval_result.keywords_found}/{retrieval_result.total_keywords}")
    print(f"Keyword Coverage: {retrieval_result.keyword_coverage:.1f}%")

    # Answer Evaluation
    print(f"\n{'=' * 80}")
    print("Answer Evaluation")
    print(f"{'=' * 80}")

    answer_result, generated_answer, retrieved_docs = evaluate_answer(test)

    print(f"\nGenerated Answer:\n{generated_answer}")
    print(f"\nFeedback:\n{answer_result.feedback}")
    print("\nScores:")
    print(f"  Accuracy: {answer_result.accuracy:.2f}/5")
    print(f"  Completeness: {answer_result.completeness:.2f}/5")
    print(f"  Relevance: {answer_result.relevance:.2f}/5")
    print(f"\n{'=' * 80}\n")


def sample_tests(tests: list[TestQuestion], limit: int | None) -> list[TestQuestion]:
    """Evenly spaced subset, so every category stays represented."""
    if not limit or limit >= len(tests):
        return tests
    step = len(tests) / limit
    return [tests[int(i * step)] for i in range(limit)]


def _mean(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


PASS_ACCURACY = 4  # an answer "passes" with accuracy >= 4; pass_rate is the headline target


def summarize(rows: list[dict], metrics: list[str], retrieval_only: bool) -> dict:
    """Averages of the metrics, plus pass rate and a failure breakdown for answer runs."""
    stats = {"tests": len(rows), **{m: _mean([r[m] for r in rows]) for m in metrics}}
    stats["retrieval_complete_rate"] = round(
        100 * sum(r["retrieval_complete"] for r in rows) / len(rows), 2) if rows else 0.0
    if not retrieval_only:
        failed = [r for r in rows if r["accuracy"] < PASS_ACCURACY]
        stats["pass_rate"] = round(100 * (len(rows) - len(failed)) / len(rows), 2) if rows else 0.0
        stats["failures"] = {
            "retrieval_miss": sum(not r["retrieval_complete"] for r in failed),
            "answer_mistake": sum(r["retrieval_complete"] for r in failed),
        }
    return stats


def run_batch(limit: int | None, retrieval_only: bool, label: str) -> Path:
    """Evaluate many tests and save per-test rows plus overall and per-category averages to JSON."""
    tests = sample_tests(load_tests(), limit)
    metrics = ["mrr", "ndcg", "keyword_coverage"]
    if not retrieval_only:
        metrics += ["accuracy", "completeness", "relevance"]

    rows = []
    error = None
    start = time.time()
    try:
        for index, test in enumerate(tests, start=1):
            row = {"question": test.question, "category": test.category}
            if retrieval_only:
                docs = impl().fetch_context(test.question)
            else:
                answer, docs = impl().answer_question(test.question)
                row["answer"] = answer
                judged = judge_answer(test, answer)
                row.update(judged.model_dump(include={"accuracy", "completeness", "relevance", "feedback"}))
            retrieval = score_retrieval(test, docs)
            row.update(retrieval.model_dump(include={"mrr", "ndcg", "keyword_coverage"}))
            # False = some keyword never reached the model, so a wrong answer is a retrieval miss
            row["retrieval_complete"] = retrieval.keywords_found == retrieval.total_keywords
            rows.append(row)
            print(f"[{index}/{len(tests)}] {test.category:<14} mrr={row['mrr']:.2f}"
                  + ("" if retrieval_only else f" acc={row['accuracy']:.0f}"), flush=True)
    except (Exception, KeyboardInterrupt) as e:
        error = f"{type(e).__name__}: {str(e)[:300]}"
        print(f"Stopped early after {len(rows)} tests -> {error}", file=sys.stderr)

    by_category = defaultdict(list)
    for row in rows:
        by_category[row["category"]].append(row)
    summary = {
        "label": label,
        "impl": _impl_name,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "tests": len(rows),
        "planned_tests": len(tests),
        "error": error,
        "answer_model": None if retrieval_only else impl().MODEL,
        "judge_model": None if retrieval_only else JUDGE_MODEL,
        "seconds": round(time.time() - start, 1),
        "overall": summarize(rows, metrics, retrieval_only),
        "by_category": {
            cat: summarize(rs, metrics, retrieval_only) for cat, rs in sorted(by_category.items())
        },
    }

    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{label}.json"
    path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"Saved {path}")
    return path


def main():
    parser = argparse.ArgumentParser(description="Evaluate the RAG system.")
    parser.add_argument("target", help="a test row number, or 'all' for a batch run")
    parser.add_argument("--limit", type=int, help="batch: evenly spaced subset of N tests")
    parser.add_argument("--retrieval-only", action="store_true", help="batch: skip LLM answer + judge (free, fast)")
    parser.add_argument("--impl", choices=sorted(IMPLEMENTATIONS), default="basic", help="RAG implementation to evaluate")
    parser.add_argument("--label", default=None, help="batch: results file name (evaluation/results/<label>.json)")
    args = parser.parse_args()
    use_implementation(args.impl)

    if args.target == "all":
        label = args.label or datetime.now().strftime("run_%Y%m%d_%H%M%S")
        run_batch(args.limit, args.retrieval_only, label)
        return

    try:
        test_number = int(args.target)
    except ValueError:
        parser.error("target must be an integer or 'all'")
    run_cli_evaluation(test_number)


if __name__ == "__main__":
    main()
