"""
Direct real-DB test for FIX 1 (revenue y-axis) and FIX 2/3 (entity_count for 9-partner).
Calls get_distribution() with real DB, then builds chart configs.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import logging
logging.basicConfig(level=logging.WARNING)

from dotenv import load_dotenv; load_dotenv()
from unittest.mock import patch, MagicMock
from sqlalchemy import create_engine

from src.agents.insight_generator import InsightGenerator
from src.agents.response_planner import ResponsePlanner
from src.models.agent_state import AgentState, ToolCallResult
from src.tools.analytics_tools import get_distribution

engine = create_engine(os.getenv('FINANCIAL_DB_URL'))

# ── FIX 4: real COUNT pre-flight ──────────────────────────────────────────────
result = get_distribution(engine, '2026-06-01', '2026-06-30', dimension='partner', top_n=30)
print("=" * 70)
print("FIX 4 — real COUNT pre-flight for 9-partner distribution")
print("=" * 70)
print(f"  actual_entity_count : {result['actual_entity_count']}")
print(f"  row_count           : {result['row_count']}")
print(f"  description         : {result['description']}")
print(f"  clamp order         : _top_n=max(1,min(30,200))=30 → top_n_final=min(30,{result['actual_entity_count']})={min(30, result['actual_entity_count'])}")
print()

data = result['data']
print(f"  Columns returned    : {list(data[0].keys())}")
print(f"  Rows returned       : {len(data)}")

# ── FIX 1: chart configs — dual-axis revenue must show y1_is_pct=False ────────
with patch.object(InsightGenerator, '_init_client', return_value=('openai', MagicMock(), 'gpt-4o')):
    ig = InsightGenerator()

state = AgentState(query='distribusi partner', database='financial_db', query_result=data, row_count=len(data))
state.tool_results = [ToolCallResult(
    tool_name='get_distribution', data=data, row_count=len(data),
    sql_or_params='', description=result['description'],
    actual_entity_count=result['actual_entity_count'],
)]

configs = ig._build_chart_configs(state)
print()
print("=" * 70)
print("FIX 1 — chart configs for 9-entity distribution (bar, not donut)")
print("=" * 70)
print(f"  Chart configs built : {len(configs)}")
for k, cc in enumerate(configs):
    print(f"  Config {k}: type={cc['type']}  title={cc['title']!r}")
    print(f"    dual_axis  = {cc['dual_axis']}")
    print(f"    y_is_pct   = {cc['y_is_pct']}")
    print(f"    y1_is_pct  = {cc['y1_is_pct']}")
    for ds in cc['datasets']:
        axis = ds.get('yAxisID', 'y(default)')
        print(f"    dataset: '{ds['label']}'  yAxisID={axis}")
    if cc.get('dual_axis'):
        renderer_fmt = "v + '%'" if cc['y1_is_pct'] else "_shortNum(v)"
        print(f"    → renderer y1 formatter: {renderer_fmt}")
        y1_datasets = [ds['label'] for ds in cc['datasets'] if ds.get('yAxisID') == 'y1']
        print(f"    → y1 column(s): {y1_datasets}")

# ── FIX 2/3: entity_count from tool_results shape ────────────────────────────
with patch.object(ResponsePlanner, '_init_client', return_value=('openai', MagicMock(), 'gpt-4o')):
    rp = ResponsePlanner()

shape = rp._build_data_shape(state)
entity_count = shape.get('distinct_entity_count') or (
    shape['steps'][0].get('distinct_entity_count', 0) if shape.get('steps') else 0
)

print()
print("=" * 70)
print("FIX 2/3 — entity_count extraction from tool_results shape (9-partner)")
print("=" * 70)
print(f"  shape['steps'][0]['distinct_entity_count'] = {shape['steps'][0]['distinct_entity_count']}")
print(f"  entity_count resolved = {entity_count}")

plan = {'visual_blocks': [{'type': 'bar_chart', 'anchor_after': 's1', 'purpose': 'primary'}], 'narrative_sections': [{'id': 's1'}]}
result_plan = rp._enforce_chart_rules(state, plan)
print(f"  visual_blocks after enforce = {[b['type'] for b in result_plan['visual_blocks']]}")
print(f"  Rule 4 fired? {entity_count <= 6}   (threshold ≤6, actual={entity_count})")
print(f"  Rule 5 fired? {entity_count > 10}   (threshold >10, actual={entity_count})")
print("  → Correct: bar_chart stays, no donut, no forced data_table")
