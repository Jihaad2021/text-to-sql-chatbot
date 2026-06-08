"""
Component 7: Insight Generator

Generates natural language insights from query results using Claude.

Type: Agentic (LLM-based)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.validated_sql
    - state.query_result
    - state.row_count
    - state.is_multi_step (bool)
    - state.step_results (list[StepResult], for multi-step queries)
    - state.conversation_history (optional)

Writes to state:
    - state.insights (str)

Example:
    >>> generator = InsightGenerator()
    >>> state = AgentState(query="berapa total customer?")
    >>> state.query_result = [{"total": 100}]
    >>> state.row_count = 1
    >>> state = generator.run(state)
    >>> print(state.insights)
    "Terdapat 100 customer yang terdaftar dalam sistem."
"""

import json

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState


class InsightGenerator(LLMBaseAgent):
    """
    Generate natural language insights from SQL query results.

    Produces conversational Indonesian insights that:
    - Directly answer the user's question
    - Format numbers properly (juta/miliar)
    - Highlight key findings
    - Handle empty results gracefully
    """

    def __init__(self) -> None:
        super().__init__(name="insight_generator", version="1.0.0")

    def execute(self, state: AgentState) -> AgentState:
        """
        Generate insights from query results.

        Args:
            state: Pipeline state with query_result and row_count

        Returns:
            Updated state with state.insights and state.chart_config
        """
        try:
            prompt = self._build_prompt(state)
            insights = self._call_llm(prompt, max_tokens=1000, temperature=0.3)
            state.insights = insights
            self.log(f"Insights generated ({len(insights)} chars)")

        except Exception as e:
            self.log(f"LLM insight failed, using fallback: {e}", level="warning")
            state.insights = self._fallback(state)

        state.chart_config = self._build_chart_config(state)
        if state.chart_config:
            self.log(f"Chart config built: type={state.chart_config['type']}")

        return state

    def _build_prompt(self, state: AgentState) -> str:
        """Branch to investigation, multi-step, or single-step prompt based on state."""
        if (
            state.intent
            and state.intent.get("category") == "root_cause_analysis"
            and state.investigation_steps
        ):
            return self._build_investigation_prompt(state)
        if state.is_multi_step and state.step_results:
            return self._build_multi_step_prompt(state)
        return self._build_single_step_prompt(state)

    def _build_single_step_prompt(self, state: AgentState) -> str:
        """Build insight prompt for a single-step query."""
        if state.query_result and state.row_count > 0:
            results_text = json.dumps(state.query_result[:10], indent=2, default=str)
            if state.row_count > 10:
                results_text += f"\n... and {state.row_count - 10} more rows"
        else:
            results_text = "No results returned"

        history_block = self._build_history_block(state.conversation_history)

        return f"""You are a data analyst for Telkomsel's digital payment platform. Generate insights in conversational Indonesian.
{history_block}
USER QUESTION: "{state.query}"

SQL EXECUTED:
{state.validated_sql}

RESULTS ({state.row_count} rows):
{results_text}

CRITICAL — Number formatting rules:

TRANSACTION COUNTS (kolom: total_trx, success_trx, fail_trx, daily_unique_users, unique_users):
  - These are INTEGER COUNTS of transactions or users — NEVER format as Rupiah
  - Under 1,000: "452 transaksi"
  - Under 1 million: "52.000 transaksi"
  - 1M–999M: "52,6 juta transaksi"
  - 1B+: "1,2 miliar transaksi"

REVENUE / MONEY (kolom: total_revenue, net_revenue, platform_fee, net_gap, total_net_revenue, total_platform_fee):
  - These ARE Rupiah amounts — format with Rp prefix
  - Under 1 million: "Rp 500.000"
  - 1M–999M: "Rp 252,3 juta"
  - 1B+: "Rp 1,2 miliar"

PERCENTAGES (kolom: success_rate_pct, avg_success_rate):
  - Format as "92,5%"

RULES:
1. Directly answer the user's question first
2. Look at the column name in the SQL to determine if it's transactions, revenue, or percentage
3. Highlight key findings using "tertinggi", "terendah", "rata-rata"
4. Keep it concise: 2-4 sentences max

If no results (0 rows):
- Explain what data is available
- Suggest alternative queries or time ranges

Your insights in Indonesian:"""

    def _build_multi_step_prompt(self, state: AgentState) -> str:
        """Build insight prompt that synthesises all step results."""
        history_block = self._build_history_block(state.conversation_history)
        steps_block = self._build_steps_block(state.step_results)

        return f"""You are a data analyst for Telkomsel's digital payment platform.
{history_block}
USER ORIGINAL QUESTION: "{state.query}"

ANALYSIS STEPS EXECUTED:

{steps_block}

CRITICAL — Number formatting rules:

TRANSACTION COUNTS (kolom: total_trx, success_trx, fail_trx, daily_unique_users, unique_users):
  - INTEGER COUNTS — NEVER format as Rupiah
  - Under 1,000: "452 transaksi"
  - Under 1 million: "52.000 transaksi"
  - 1M–999M: "52,6 juta transaksi"
  - 1B+: "1,2 miliar transaksi"

REVENUE / MONEY (kolom: total_revenue, net_revenue, platform_fee, net_gap, total_net_revenue, total_platform_fee):
  - Rupiah amounts — format with Rp prefix
  - Under 1 million: "Rp 500.000"
  - 1M–999M: "Rp 252,3 juta"
  - 1B+: "Rp 1,2 miliar"

PERCENTAGES: format as "92,5%"

COMPARISON INSTRUCTIONS — when multiple steps represent two groups being compared:
1. Compute the absolute difference between the two groups
2. Compute the ratio (e.g. "X kali lipat lebih tinggi")
3. Compute the percentage change: ((A - B) / B) * 100
4. State clearly which group is higher/lower
5. Do NOT skip the math — calculate it yourself from the raw numbers in the step results

SYNTHESIS RULES:
1. Lead with the direct answer to the original question
2. Show the key numbers from each step with correct formatting
3. State the comparison result with computed ratio or percentage
4. If a step has 0 rows or failed, acknowledge it briefly and work with the available data
5. Max 5-6 sentences total

Your insights in Indonesian:"""

    def _build_steps_block(self, step_results: list) -> str:
        """Format step results for the multi-step prompt."""
        lines = []
        for step in step_results:
            if step.row_count == 0 or not step.data:
                lines.append(f"STEP {step.step_number}: {step.description}")
                lines.append("Status: FAILED or returned 0 rows — skip this step")
                lines.append("")
            else:
                preview = json.dumps(step.data[:10], indent=2, default=str)
                lines.append(f"STEP {step.step_number}: {step.description}")
                lines.append(f"SQL: {step.sql}")
                lines.append(f"Results ({step.row_count} rows):")
                lines.append(preview)
                lines.append("")
        return "\n".join(lines)

    def _build_investigation_prompt(self, state: AgentState) -> str:
        """Build insight prompt that synthesises all investigation iterations."""
        history_block = self._build_history_block(state.conversation_history)
        investigation_block = self._build_investigation_block(state.investigation_steps)

        return f"""You are a data analyst for Telkomsel's digital payment platform.
{history_block}
USER ORIGINAL QUESTION: "{state.query}"

INVESTIGATION COMPLETED — steps executed across multiple dimensions:

{investigation_block}

CRITICAL — Number formatting rules:

TRANSACTION COUNTS (kolom: total_trx, success_trx, fail_trx, daily_unique_users, unique_users):
  - INTEGER COUNTS — NEVER format as Rupiah
  - Under 1,000: "452 transaksi"
  - Under 1 million: "52.000 transaksi"
  - 1M–999M: "52,6 juta transaksi"
  - 1B+: "1,2 miliar transaksi"

REVENUE / MONEY (kolom: total_revenue, net_revenue, platform_fee, net_gap, total_net_revenue, total_platform_fee):
  - Rupiah amounts — format with Rp prefix
  - Under 1 million: "Rp 500.000"
  - 1M–999M: "Rp 252,3 juta"
  - 1B+: "Rp 1,2 miliar"

PERCENTAGES: format as "92,5%"

SYNTHESIS INSTRUCTIONS:
1. Synthesize a conclusive answer in Indonesian to the original question.
2. Compute comparisons, ratios, and percentages directly from the raw data in each step.
3. Identify the root cause based on the pattern across all dimensions.
4. Distinguish organic vs promotional patterns: if all partners rise proportionally → organic; if only 2-3 partners spike while others are flat → promo.
5. If a step has 0 rows or failed, skip it briefly and work with available data.
6. Max 6-8 sentences total.

Your insights in Indonesian:"""

    def _build_investigation_block(self, steps: list) -> str:
        """Format investigation steps for the investigation prompt."""
        lines = []
        for step in steps:
            if step.row_count == 0 or not step.data:
                lines.append(f"ITERATION {step.iteration}: {step.sub_query}")
                lines.append("Status: FAILED — skip")
                lines.append("")
            else:
                preview = json.dumps(step.data[:10], indent=2, default=str)
                lines.append(f"ITERATION {step.iteration}: {step.sub_query}")
                lines.append(f"Results ({step.row_count} rows):")
                lines.append(preview)
                lines.append("")
        return "\n".join(lines)

    def _build_history_block(self, history: list[dict]) -> str:
        """Return formatted last 2 conversation turns, or empty string."""
        if not history:
            return ""

        recent = history[-2:]
        lines = ["\nRECENT CONVERSATION:"]
        for turn in recent:
            q = turn.get("query", "")
            a = turn.get("insights", "")
            if q:
                lines.append(f"Q: {q}")
            if a:
                lines.append(f"A: {a[:200]}{'...' if len(a) > 200 else ''}")
        lines.append("")
        return "\n".join(lines)

    # ── Chart config ──────────────────────────────────────────

    _CHART_COLORS = [
        '#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6',
        '#06b6d4', '#f97316', '#84cc16', '#ec4899', '#6366f1',
    ]
    _TIME_KEYWORDS = {'date', 'month', 'week', 'year', 'day', 'hour',
                      'tanggal', 'bulan', 'minggu', 'tahun', 'jam', 'period', 'waktu'}
    _MAX_CHART_ROWS = 50

    def _build_chart_config(self, state: AgentState) -> dict | None:
        """
        Build a Chart.js-compatible config from query results.
        Uses heuristics — no extra LLM call.
        Returns None when a chart would not add value (single scalar, too many rows, etc.).
        """
        # Multi-step: compare a metric across steps
        if state.is_multi_step and state.step_results:
            return self._chart_from_steps(state.step_results)

        data = state.query_result
        if not data or len(data) == 0:
            return None

        cols = list(data[0].keys())
        if len(data) <= 1:
            return None  # single row — nothing to compare, insight text is enough
        if len(data) > self._MAX_CHART_ROWS:
            return None

        def _to_num(v: object) -> float | None:
            if isinstance(v, bool):
                return None
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                try:
                    return float(v.replace(',', '').replace(' ', ''))
                except ValueError:
                    return None
            # Handles Decimal, numpy types, etc. from PostgreSQL/SQLAlchemy
            try:
                return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                return None

        numeric_cols = [c for c in cols if _to_num(data[0].get(c)) is not None]
        text_cols    = [c for c in cols if c not in numeric_cols]

        if not numeric_cols:
            return None

        x_col   = text_cols[0] if text_cols else None
        y_cols  = numeric_cols[:3]  # cap at 3 series
        labels  = [str(row.get(x_col, i)) for i, row in enumerate(data)] if x_col \
                  else [str(i + 1) for i in range(len(data))]

        # Determine chart type
        is_time = x_col and any(kw in x_col.lower() for kw in self._TIME_KEYWORDS)
        if is_time:
            chart_type = 'line'
        elif len(data) <= 6 and len(y_cols) == 1:
            chart_type = 'doughnut'
        else:
            chart_type = 'bar'

        datasets = []
        for i, y_col in enumerate(y_cols):
            color = self._CHART_COLORS[i % len(self._CHART_COLORS)]
            values = [_to_num(row.get(y_col)) for row in data]
            ds: dict = {
                'label': y_col.replace('_', ' ').title(),
                'data':  values,
            }
            if chart_type == 'doughnut':
                ds['backgroundColor'] = self._CHART_COLORS[:len(data)]
            else:
                ds['backgroundColor'] = color + '99'  # 60% opacity
                ds['borderColor']     = color
                ds['borderWidth']     = 1
            if chart_type == 'line':
                ds['tension'] = 0.3
                ds['fill']    = False
            datasets.append(ds)

        return {'type': chart_type, 'labels': labels, 'datasets': datasets}

    def _chart_from_steps(self, step_results: list) -> dict | None:
        """Bar chart comparing one numeric metric across steps."""
        valid = [s for s in step_results if s.data and s.row_count > 0]
        if len(valid) < 2:
            return None

        def _is_num(v: object) -> bool:
            if isinstance(v, bool): return False
            if isinstance(v, (int, float)): return True
            if isinstance(v, str):
                try: float(v.replace(',', '')); return True
                except ValueError: return False
            try: float(v); return True  # type: ignore[arg-type]
            except (TypeError, ValueError): return False

        first_cols = list(valid[0].data[0].keys())
        numeric_keys = [
            c for c in first_cols
            if all(_is_num(s.data[0].get(c)) for s in valid)
        ]
        if not numeric_keys:
            return None

        metric = numeric_keys[0]
        labels = [f"Tahap {s.step_number}" for s in valid]
        def _to_f(v: object) -> float:
            if isinstance(v, (int, float)): return float(v)
            try: return float(v)  # type: ignore[arg-type]
            except (TypeError, ValueError): pass
            try: return float(str(v).replace(',', ''))
            except ValueError: return 0.0

        values = [_to_f(s.data[0].get(metric)) for s in valid]
        color  = self._CHART_COLORS[0]

        return {
            'type': 'bar',
            'labels': labels,
            'datasets': [{
                'label':           metric.replace('_', ' ').title(),
                'data':            values,
                'backgroundColor': [self._CHART_COLORS[i % len(self._CHART_COLORS)] + '99'
                                    for i in range(len(valid))],
                'borderColor':     [self._CHART_COLORS[i % len(self._CHART_COLORS)]
                                    for i in range(len(valid))],
                'borderWidth': 1,
            }],
        }

    def _fallback(self, state: AgentState) -> str:
        """Fallback insight if LLM call fails."""
        if not state.query_result or state.row_count == 0:
            return f"Query untuk '{state.query}' tidak mengembalikan hasil."

        if state.row_count == 1 and len(state.query_result[0]) == 1:
            key = list(state.query_result[0].keys())[0]
            value = state.query_result[0][key]
            if isinstance(value, (int, float)):
                return f"Hasil: {value:,}"
            return f"Hasil: {value}"

        return f"Query mengembalikan {state.row_count} baris data."
