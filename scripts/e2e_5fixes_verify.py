"""
End-to-end verification for 5 fixes — runs 3 queries through the REAL pipeline.

Uses real DB (financial_db) and real LLM (no mocks).
Prints raw internal state fields: entity_count, actual_entity_count, visual_blocks,
chart_configs, top_n, insights.
"""

import os
import sys
import json
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

# ── structured logging so pipeline agent logs appear inline ──────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from src.core.pipeline import TextToSQLPipeline
from src.agents.query_rewriter import QueryRewriter
from src.agents.intent_classifier import IntentClassifier
from src.agents.query_planner import QueryPlanner
from src.agents.schema_retriever import SchemaRetriever
from src.agents.retrieval_evaluator import RetrievalEvaluator
from src.agents.sql_generator import SQLGenerator
from src.agents.sql_validator import SQLValidator
from src.agents.query_executor import QueryExecutor
from src.agents.insight_generator import InsightGenerator
from src.models.agent_state import AgentState
from src.core.config import Config

SEP  = "=" * 72
SEP2 = "-" * 72


def make_pipeline() -> TextToSQLPipeline:
    return TextToSQLPipeline(
        query_rewriter=QueryRewriter(),
        intent_classifier=IntentClassifier(),
        query_planner=QueryPlanner(),
        schema_retriever=SchemaRetriever(),
        retrieval_evaluator=RetrievalEvaluator(),
        sql_generator=SQLGenerator(),
        sql_validator=SQLValidator(enable_ai_validation=Config.ENABLE_AI_VALIDATION),
        query_executor=QueryExecutor(),
        insight_generator=InsightGenerator(),
    )


def dump_state(state: AgentState, label: str) -> None:
    print(f"\n{'─'*72}")
    print(f"  STATE DUMP — {label}")
    print(f"{'─'*72}")
    print(f"  query_out_of_range   : {state.query_out_of_range}")
    print(f"  intent               : {state.intent}")
    print(f"  row_count            : {state.row_count}")
    print(f"  validated_sql (first 200): {(state.validated_sql or '')[:200]!r}")

    # tool_results
    if state.tool_results:
        for i, tr in enumerate(state.tool_results):
            ae = getattr(tr, 'actual_entity_count', 0)
            print(f"  tool_results[{i}]")
            print(f"    tool_name            : {tr.tool_name}")
            print(f"    row_count            : {tr.row_count}")
            print(f"    actual_entity_count  : {ae}")
            print(f"    description          : {tr.description}")
    else:
        print(f"  tool_results         : []")

    # layout_plan visual_blocks
    lp = state.layout_plan or {}
    vbs = lp.get("visual_blocks", [])
    print(f"  visual_blocks count  : {len(vbs)}")
    for j, vb in enumerate(vbs):
        print(f"    [{j}] type={vb.get('type')}  purpose={vb.get('purpose')}")

    # chart_configs
    ccs = state.chart_configs or []
    print(f"  chart_configs count  : {len(ccs)}")
    for k, cc in enumerate(ccs):
        ds_labels = [ds.get("label") for ds in cc.get("datasets", [])]
        print(f"    [{k}] type={cc.get('type')}  title={cc.get('title')!r}")
        print(f"         dual_axis={cc.get('dual_axis')}  "
              f"y_is_pct={cc.get('y_is_pct')}  y1_is_pct={cc.get('y1_is_pct')}")
        print(f"         center_value={cc.get('center_value')!r}  "
              f"datasets={ds_labels}")
        if cc.get('dual_axis'):
            for ds in cc.get("datasets", []):
                print(f"           ds '{ds.get('label')}' → yAxisID={ds.get('yAxisID','y(default)')}")

    # insights (truncated)
    ins = state.insights or ""
    print(f"  insights ({len(ins)} chars, first 800):")
    print(f"  ---")
    print(f"  {ins[:800]}")
    if len(ins) > 800:
        print(f"  ... [truncated]")
    print(f"  ---")


# ─────────────────────────────────────────────────────────────────────────────

def run_query(pipeline: TextToSQLPipeline, query: str, label: str) -> None:
    print(f"\n{SEP}")
    print(f"  QUERY: {label}")
    print(f"  TEXT : {query}")
    print(SEP)

    state = AgentState(
        query=query,
        database="financial_db",
        conversation_history=[],
    )
    result = pipeline.run(state)
    dump_state(result, label)


def main():
    print(f"\n{SEP}")
    print("  Initializing full pipeline (real DB + real LLM)…")
    print(SEP)
    pipeline = make_pipeline()
    print(f"  data_end_date: {pipeline.data_end_date}")
    print(f"  context_snapshot length: {len(pipeline.context_snapshot or '')} chars")

    # ── Query 1 ───────────────────────────────────────────────────────────
    run_query(
        pipeline,
        "Distribusi share 5 partner terbesar bulan Juni 2026",
        "Q1: 5-partner distribution (expect 2× donut_chart)",
    )

    # ── Query 2 ───────────────────────────────────────────────────────────
    run_query(
        pipeline,
        "Distribusi share transaksi per partner bulan Juni 2026",
        "Q2: all-partner distribution (9 entities, expect bar_chart, y1_is_pct=False)",
    )

    # ── Query 3 ───────────────────────────────────────────────────────────
    run_query(
        pipeline,
        "Top 1000 produk berdasarkan volume transaksi bulan Juni 2026",
        "Q3: top-1000 products (expect actual_entity_count, data_table only)",
    )

    pipeline.close()
    print(f"\n{SEP}")
    print("  Done.")
    print(SEP)


if __name__ == "__main__":
    main()
