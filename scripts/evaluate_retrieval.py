"""
Retrieval Evaluation Script

Measures SchemaRetriever quality against the golden set in config/golden_set.yaml.

Metrics computed per query:
  - recall@k   : fraction of expected tables found in top-k retrieved
  - hit@1      : 1 if at least one expected table is the top result

Aggregate metrics:
  - mean recall@k across all queries
  - per-intent-category breakdown
  - per-table miss frequency (which tables are hardest to retrieve)
  - retriever contribution (Chroma vs BM25 vs Graph) when available

Usage:
    python scripts/evaluate_retrieval.py
    python scripts/evaluate_retrieval.py --top-k 3
    python scripts/evaluate_retrieval.py --golden config/golden_set.yaml --verbose
"""

import argparse
import logging
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from src.agents.schema_retriever import SchemaRetriever  # noqa: E402
from src.models.agent_state import AgentState  # noqa: E402

logging.basicConfig(level=logging.WARNING)  # suppress agent INFO logs during eval


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_golden_set(path: Path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data["questions"]


def recall(expected: list[str], retrieved: list[str]) -> float:
    """Fraction of expected tables found anywhere in the retrieved list."""
    if not expected:
        return 1.0
    found = sum(1 for t in expected if t in retrieved)
    return found / len(expected)


def _bar(value: float, width: int = 20) -> str:
    filled = round(value * width)
    return "█" * filled + "░" * (width - filled)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main(golden_path: Path, top_k: int, verbose: bool) -> None:
    questions = load_golden_set(golden_path)
    total = len(questions)
    print(f"\nLoaded {total} questions from {golden_path.name}")
    print(f"Initialising SchemaRetriever (top_k={top_k})...\n")

    retriever = SchemaRetriever(top_k=top_k)

    results: list[dict] = []
    miss_table_counts: dict[str, int] = {}
    intent_buckets: dict[str, list[float]] = {}

    for q in questions:
        qid     = q["id"]
        query   = q["query"]
        intent  = q.get("intent", "unknown")
        expected = q.get("expected_tables", [])

        state = AgentState(query=query, database="financial_db")
        try:
            state = retriever.run(state)
            retrieved_names = [t.table_name for t in state.retrieved_tables]
        except Exception as exc:
            print(f"  [{qid}] ERROR: {exc}")
            retrieved_names = []

        r = recall(expected, retrieved_names)
        results.append({
            "id": qid, "query": query, "intent": intent,
            "expected": expected, "retrieved": retrieved_names,
            "recall": r,
        })

        intent_buckets.setdefault(intent, []).append(r)

        for t in expected:
            if t not in retrieved_names:
                miss_table_counts[t] = miss_table_counts.get(t, 0) + 1

        status = "✓" if r == 1.0 else ("~" if r > 0 else "✗")
        if verbose or r < 1.0:
            print(f"  [{qid}] {status}  recall={r:.2f}  | expected={expected}  got={retrieved_names}")
            if q.get("notes"):
                print(f"         notes: {q['notes']}")

    # ── Summary ───────────────────────────────────────────────────────────────
    recalls = [r["recall"] for r in results]
    mean_recall = sum(recalls) / len(recalls)
    perfect     = sum(1 for r in recalls if r == 1.0)
    partial     = sum(1 for r in recalls if 0 < r < 1.0)
    zero        = sum(1 for r in recalls if r == 0.0)

    print("\n" + "═" * 60)
    print(f"  OVERALL  recall@{top_k} = {mean_recall:.3f}  {_bar(mean_recall)}")
    print(f"  {perfect}/{total} perfect  {partial} partial  {zero} zero-recall")
    print("═" * 60)

    print("\n── By intent ─────────────────────────────────────────────")
    for intent, vals in sorted(intent_buckets.items()):
        avg = sum(vals) / len(vals)
        print(f"  {intent:25s} {avg:.3f}  {_bar(avg, 16)}  (n={len(vals)})")

    if miss_table_counts:
        print("\n── Most missed tables ────────────────────────────────────")
        for table, cnt in sorted(miss_table_counts.items(), key=lambda x: -x[1]):
            print(f"  {table:30s} missed {cnt}×")

    # ── Per-query table ───────────────────────────────────────────────────────
    print("\n── Per-query results ─────────────────────────────────────")
    header = f"  {'ID':7}  {'R@k':5}  {'Expected':35}  Retrieved"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for r in results:
        flag = "✓" if r["recall"] == 1.0 else ("~" if r["recall"] > 0 else "✗")
        exp_str = ", ".join(r["expected"])
        got_str = ", ".join(r["retrieved"])
        print(f"  {r['id']:7}  {flag} {r['recall']:.2f}  {exp_str:35}  {got_str}")

    print()
    if mean_recall >= 0.90:
        verdict = "GOOD — retrieval is solid."
    elif mean_recall >= 0.75:
        verdict = "FAIR — some tables are hard to retrieve, consider enriching their descriptions."
    else:
        verdict = "POOR — retrieval needs significant tuning."
    print(f"  Verdict: {verdict}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate SchemaRetriever against golden set")
    parser.add_argument("--golden", default=str(ROOT / "config" / "golden_set.yaml"),
                        help="Path to golden set YAML")
    parser.add_argument("--top-k", type=int, default=5,
                        help="Number of tables to retrieve per query (default: 5)")
    parser.add_argument("--verbose", action="store_true",
                        help="Print all queries, not just misses")
    args = parser.parse_args()

    main(Path(args.golden), args.top_k, args.verbose)
