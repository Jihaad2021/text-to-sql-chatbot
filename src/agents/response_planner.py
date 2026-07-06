"""
ResponsePlanner — Plans output structure before InsightGenerator runs.

Type: Agentic (LLM-based, lightweight — uses cheaper model)
Inherits: LLMBaseAgent

Reads from state:
    - state.query
    - state.intent
    - state.query_result
    - state.row_count
    - state.is_multi_step
    - state.step_results

Writes to state:
    - state.layout_plan (dict)

─────────────────────────────────────────────────────────────────────────
LAYOUT PLAN SCHEMA
─────────────────────────────────────────────────────────────────────────
{
    "narrative_sections": [
        {"id": "s1", "title": null,             "instruction": "..."},
        {"id": "s2", "title": "## Section Title", "instruction": "..."}
    ],
    "visual_blocks": [
        # purpose="leading_answer"  → anchor_after MUST be null (renders BEFORE all sections)
        {"type": "bar_chart",  "anchor_after": null, "purpose": "leading_answer"},
        # purpose="supporting_evidence" → anchor_after = section id it supports
        {"type": "line_chart", "anchor_after": "s2", "purpose": "supporting_evidence"},
        # purpose="detail_reference"   → anchor_after = last section id; always sorted last + collapsed
        {"type": "data_table", "anchor_after": "s3", "purpose": "detail_reference"},
    ],
    "needs_visual":    true | false,           # enforced deterministically in _compute_needs_visual()
    "key_metrics":     ["col_name", ...],      # max 4 columns to bold in narrative
    "response_length": "brief" | "standard" | "detailed",
    "anomaly_flag":    true | false,           # derived from visual_blocks; kept for InsightGenerator compat
}

─────────────────────────────────────────────────────────────────────────
VISUAL PURPOSE SEMANTICS
─────────────────────────────────────────────────────────────────────────
leading_answer      → The chart IS the primary answer (comparison, distribution, ranking).
                      anchor_after MUST be null — it renders BEFORE all narrative sections,
                      not after any specific section. Auto-fixed in _parse_plan() if LLM
                      emits a non-null value.

supporting_evidence → The chart reinforces a claim made in anchor_after section.
                      Frontend renders it immediately after that section.

detail_reference    → Raw data / table for users who want to drill down.
                      anchor_after is forced to the last section id in _parse_plan().
                      Frontend renders it collapsed at the very bottom.

─────────────────────────────────────────────────────────────────────────
RENDER ORDER WITHIN A SHARED ANCHOR GROUP
─────────────────────────────────────────────────────────────────────────
When multiple visual_blocks share the same anchor_after value, _parse_plan()
sorts them deterministically using _PURPOSE_RENDER_ORDER — do NOT rely on the
order the LLM emits them:

    null anchor   : leading_answer only (always first in the entire list)
    same section  : supporting_evidence  (rendered inline, immediately visible)
                    detail_reference     (rendered last in group, collapsed)

─────────────────────────────────────────────────────────────────────────
NEEDS_VISUAL RULES  (enforced in code, not left to the LLM)
─────────────────────────────────────────────────────────────────────────
false when:
    - row_count < 2  (nothing meaningful to plot)
    - single scalar (1 row × 1 col) AND response_length == "brief"
true otherwise when visual_blocks is non-empty.
"""

import json
import os

from src.core.llm_base_agent import LLMBaseAgent
from src.models.agent_state import AgentState

# Cheap default models per provider — planner doesn't need full reasoning power
_CHEAP_MODELS: dict[str, str] = {
    "openai":     "gpt-4o-mini",
    "anthropic":  "claude-haiku-4-5-20251001",
    "groq":       "llama3-8b-8192",
    "gemini":     "gemini-1.5-flash",
    "openrouter": "google/gemini-2.5-flash",
}

_VALID_VISUAL_TYPES = {
    "line_chart", "bar_chart", "diverging_bar_chart", "donut_chart",
    "grouped_bar_chart",
    "kpi_grid", "anomaly_callout", "data_table", "ranking_table",
}

_VALID_PURPOSES = {"leading_answer", "supporting_evidence", "detail_reference"}

_VALID_LENGTHS = {"brief", "standard", "detailed"}

# Render order within a shared anchor_after group — do NOT trust LLM output order.
# leading_answer is always anchor=None so it won't share a group, but included for completeness.
_PURPOSE_RENDER_ORDER: dict[str, int] = {
    "leading_answer":      0,
    "supporting_evidence": 1,
    "detail_reference":    2,
}


class ResponsePlanner(LLMBaseAgent):
    """
    Plans the narrative structure and visual block placement for each response.

    Uses a cheap/fast model because the task is purely structural —
    no prose generation, only JSON classification.

    Output (state.layout_plan) is consumed by:
      - InsightGenerator._build_layout_block(): reads narrative_sections,
        response_length, key_metrics, anomaly_flag to structure its LLM prompt.
      - Frontend renderer (future): reads visual_blocks + anchor_after + purpose
        to position charts adaptively inside the narrative flow.
    """

    def __init__(self) -> None:
        super().__init__(name="response_planner", version="2.0.0")
        self._maybe_use_cheap_model()

    def _maybe_use_cheap_model(self) -> None:
        """Downgrade to cheaper model unless explicitly overridden in env."""
        if os.getenv("RESPONSE_PLANNER_MODEL"):
            return
        cheap = _CHEAP_MODELS.get(self.provider)
        if cheap and cheap != self.model:
            self.log(f"Using cheap model for planning: {cheap} (was {self.model})")
            self.model = cheap

    def execute(self, state: AgentState) -> AgentState:
        has_data = (
            bool(state.query_result)
            or bool(state.tool_results)
            or (state.is_multi_step and state.step_results)
        )
        if not has_data:
            state.layout_plan = self._default_plan("empty")
            return state

        try:
            prompt = self._build_prompt(state)
            raw    = self._call_llm(prompt, max_tokens=700, temperature=0)
            plan   = self._parse_plan(raw)
            plan   = self._enforce_chart_rules(state, plan)
            plan   = self._apply_anomaly_flag(state, plan)
            plan["needs_visual"] = self._compute_needs_visual(state, plan)
            state.layout_plan = plan
            self.log(
                f"Layout: {len(plan['narrative_sections'])} sections, "
                f"{len(plan['visual_blocks'])} visual(s), "
                f"needs_visual={plan['needs_visual']}, "
                f"length={plan['response_length']}"
            )
        except Exception as e:
            self.log(f"Planner failed, using default: {e}", level="warning")
            state.layout_plan = self._default_plan(state.intent)

        return state

    # ─────────────────────────────────────────────────────────────
    # DATA SHAPE
    # ─────────────────────────────────────────────────────────────

    # Column-name substrings that indicate a time dimension
    _TIME_KEYWORDS = frozenset({"date", "period", "bulan", "month", "week", "minggu", "hour", "jam"})
    # Column-name substrings checked via exact contains (lowercase)
    _PCT_CHANGE_KEYWORDS = frozenset({"pct_change", "pct_growth", "pct_diff"})
    _SHARE_KEYWORDS      = frozenset({"share_pct", "distribution", "share", "kontribusi"})

    def _build_data_shape(self, state: AgentState) -> dict:
        """
        Build a structured dict describing the query result shape.

        Used by _build_prompt() to give the LLM precise, typed signals instead of
        a freeform string — helps Haiku consistently choose visual_blocks.

        Priority:
          1. tool_results (analytics path) — per-tool shapes, each with its own schema
          2. step_results (multi-step SQL path) — per-step shapes
          3. query_result (single-step SQL path) — single shape

        For multi-tool / multi-step: returns {"is_multi_step": True, "steps": [...]}
        For single-step:             returns {"is_multi_step": False, <shape fields>}
        """
        # Analytics tool-calling path: each tool has its own schema — never mix them
        if state.tool_results:
            steps = []
            for tr in state.tool_results:
                if not tr.data:
                    continue
                cols = list(tr.data[0].keys())
                steps.append(self._shape_for_cols(cols, tr.row_count, tr.tool_name, data=tr.data))
            return {"is_multi_step": True, "steps": steps}

        if state.is_multi_step and state.step_results:
            steps = []
            for s in state.step_results:
                if not s.data:
                    continue
                cols = list(s.data[0].keys())
                steps.append(self._shape_for_cols(cols, s.row_count, s.description, data=s.data))
            return {"is_multi_step": True, "steps": steps}

        if not state.query_result:
            return {"is_multi_step": False, "row_count": 0, "columns": []}

        cols = list(state.query_result[0].keys())
        return {"is_multi_step": False, **self._shape_for_cols(cols, state.row_count, data=state.query_result)}

    def _shape_for_cols(
        self,
        cols: list[str],
        row_count: int,
        label: str | None = None,
        *,
        data: list[dict] | None = None,
    ) -> dict:
        """Compute shape signals for a single column list + row count.

        Args:
            cols:      Column names from the result set.
            row_count: Number of rows.
            label:     Optional label (tool name / step description) for multi-step shapes.
            data:      Actual row data — used to count distinct time values so that a
                       single-date filter (WHERE date = '2026-06-30') is NOT treated as a
                       real time series.  When data is None the column-name heuristic alone
                       is used (conservative: presence of a date column → has_time=True).
        """
        cols_lower = [c.lower() for c in cols]

        has_time   = any(kw in c for c in cols_lower for kw in self._TIME_KEYWORDS)
        has_pct    = any(kw in c for c in cols_lower for kw in self._PCT_CHANGE_KEYWORDS)
        has_share  = any(kw in c for c in cols_lower for kw in self._SHARE_KEYWORDS)

        # Detect *_a / *_b column pairs (compare_periods two-period pattern).
        # A pair is valid when the same prefix exists for both suffixes, e.g.
        # trx_a + trx_b → prefix "trx" is in both sets.
        _a_prefixes = {c[:-2] for c in cols_lower if c.endswith('_a')}
        _b_prefixes = {c[:-2] for c in cols_lower if c.endswith('_b')}
        has_ab_pairs = bool(_a_prefixes & _b_prefixes)

        # Refine has_time when actual row data is available: a time column with only one
        # distinct value is a point filter (e.g. WHERE date = '2026-06-30'), NOT a real
        # time series.  Only treat it as a time dimension when ≥2 distinct values exist.
        if has_time and data:
            time_col = next(
                (c for c in cols if any(kw in c.lower() for kw in self._TIME_KEYWORDS)),
                None,
            )
            if time_col:
                distinct_time_vals = len({row.get(time_col) for row in data})
                has_time = distinct_time_vals > 1

        shape: dict = {
            "row_count":              row_count,
            "columns":                cols,
            "has_time_dimension":     has_time,
            "has_pct_change_column":  has_pct,
            "has_share_column":       has_share,
            "has_ab_pair_columns":    has_ab_pairs,
            "distinct_entity_count":  row_count,
        }
        if label is not None:
            shape["label"] = label
        return shape

    # ─────────────────────────────────────────────────────────────
    # PROMPT
    # ─────────────────────────────────────────────────────────────

    def _build_prompt(self, state: AgentState) -> str:
        intent_cat = ""
        if isinstance(state.intent, dict):
            intent_cat = state.intent.get("category", "")
        elif isinstance(state.intent, str):
            intent_cat = state.intent

        data_shape = json.dumps(self._build_data_shape(state), ensure_ascii=False)

        # Segment from IntentClassifier, fallback to keyword detection
        intent_segment = ""
        if isinstance(state.intent, dict):
            intent_segment = state.intent.get("segment", "")

        if intent_segment and intent_segment != "general":
            segment = intent_segment.upper()
        else:
            q_lower = (state.query or "").lower()
            if any(w in q_lower for w in ("partner", "gopay", "dana", "ovo", "linkaja")):
                segment = "PARTNERS"
            elif any(w in q_lower for w in ("produk", "product", "pulsa", "internet", "paket", "konten")):
                segment = "PRODUCTS"
            elif any(w in q_lower for w in ("channel", "saluran", "umb", "mytelkomsel", "wec")):
                segment = "CHANNELS"
            elif any(w in q_lower for w in ("transaksi", "volume", "revenue", "sr", "user", "arpu")):
                segment = "TRANSACTIONS"
            else:
                segment = "GENERAL"

        return f"""You are a response layout planner for a data analytics chatbot about Telkomsel's digital payment platform.
Given the query, business segment, intent, and structured data shape, output a JSON layout plan.

QUERY: "{state.query}"
SEGMENT: {segment}
INTENT: {intent_cat}
DATA_SHAPE: {data_shape}

DATA_SHAPE field guide (use these to choose visual_blocks type):
  row_count             — total rows returned; use for needs_visual rule (false if < 2)
  columns               — list of column names in the result
  has_time_dimension    — true when a date/period/month column is present → prefer line_chart
  has_pct_change_column — true when a *_pct_change column exists → prefer diverging_bar_chart for comparison
  has_share_column      — true when a *_share_pct / distribution column exists → prefer donut_chart (≤6 rows) or bar_chart
  has_ab_pair_columns   — true when *_a AND *_b column pairs exist (e.g. trx_a/trx_b, rev_a/rev_b) → emit grouped_bar_chart as a SECOND chart alongside diverging_bar_chart
  distinct_entity_count — number of rows = number of categories; ≤6 → donut_chart eligible (guarded by has_time_dimension=false, see Rule 1), >6 → bar_chart

Return ONLY valid JSON — no explanation, no markdown fences:
{{
  "narrative_sections": [
    {{"id": "s1", "title": null,               "instruction": "one concise instruction"}},
    {{"id": "s2", "title": "## Section Title", "instruction": "one concise instruction"}}
  ],
  "visual_blocks": [
    {{
      "type":         "bar_chart",
      "anchor_after": null,
      "purpose":      "leading_answer"
    }},
    {{
      "type":         "line_chart"|"bar_chart"|"diverging_bar_chart"|"donut_chart"|"grouped_bar_chart"|"kpi_grid"|"anomaly_callout"|"ranking_table",
      "anchor_after": "s1"|"s2"|"s3"|"s4",
      "purpose":      "supporting_evidence"
    }},
    {{
      "type":         "data_table"|"ranking_table",
      "anchor_after": "s2",
      "purpose":      "detail_reference"
    }}
  ],
  "needs_visual":    true|false,
  "key_metrics":     ["col_name", ...],
  "response_length": "brief"|"standard"|"detailed"
}}

═══════════════════════════════════════════════
SECTION RULES
═══════════════════════════════════════════════
- narrative_sections: 1–4 entries.
- First section ALWAYS has title=null — gives the direct 1–2 sentence answer + SEHAT/PERHATIAN/KRITIS verdict. Its id is always "s1".
- Subsequent sections have titled sub-topics. Their ids are "s2", "s3", "s4".
- Each instruction MUST specify whether content should be bullet points or numbered list.
- Segment-aware section titles to prefer:
  TRANSACTIONS: "## Performa Harian", "## Tren Volume", "## Success Rate", "## Anomali"
  PRODUCTS:     "## Portfolio Produk", "## Momentum Pertumbuhan", "## Produk Bermasalah"
  PARTNERS:     "## Kesehatan Ekosistem", "## Momentum Partner", "## Partner Berisiko"
  CHANNELS:     "## Distribusi Channel", "## Performa Channel", "## Konsentrasi Channel"

═══════════════════════════════════════════════
VISUAL BLOCK RULES
═══════════════════════════════════════════════
CHART SELECTION — check rules in order, take first match:

  1. donut_chart
     WHEN: has_share_column=true AND has_time_dimension=false AND distinct_entity_count ≤ 6
     NOTE: has_time_dimension=false is mandatory. distinct_entity_count equals row_count,
     so a 5-partner × 6-month query gives distinct_entity_count=30 (not 5). Without
     this guard the rule fires on multi-entity time-series; rule 2 handles those instead.

  2. line_chart
     WHEN: has_time_dimension=true

  3. diverging_bar_chart  +  grouped_bar_chart  (may co-exist)
     diverging_bar_chart — TWO trigger paths — fire on the FIRST that matches:
       A. is_multi_step=true
          AND steps[0].columns == steps[1].columns (identical column names)
          AND steps[0].row_count == steps[1].row_count
          (Identical-schema step pair = side-by-side period comparison. InsightGenerator
          computes % change; ResponsePlanner only needs to detect the structural pattern.)
       B. has_pct_change_column=true (single-step DATA_SHAPE)
          OR any steps[N].has_pct_change_column=true (multi-step/tool-results DATA_SHAPE)
          AND has_time_dimension=false
          (Pre-computed ± deltas from compare_periods or detect_anomaly are already in the
          data — use diverging bar to show positive/negative directions explicitly.
          SKIP if has_time_dimension=true; a line_chart handles time-series better.)
     grouped_bar_chart — ALWAYS emit alongside diverging_bar_chart when:
          has_ab_pair_columns=true (columns like trx_a/trx_b from compare_periods)
          purpose="supporting_evidence", anchor_after="s1"
          (Shows absolute values for two periods side-by-side per entity — answers
          "how much was it each period" while diverging_bar answers "how much did it change".)
          NOTE: the deterministic _enforce_chart_rules() adds this automatically even if
          you omit it, but emit it explicitly when has_ab_pair_columns=true.

  4. bar_chart
     WHEN: has_share_column=true AND distinct_entity_count > 6
     (Too many slices for a donut — use bar chart.)

  5. data_table  (no chart — do not add a chart entry in visual_blocks)
     WHEN: distinct_entity_count > 10 AND has_time_dimension=false
     (Too many categories to chart meaningfully; surface raw data only.)

  6. bar_chart
     WHEN: is_multi_step=false AND has_time_dimension=false AND has_share_column=false
     (Ranking / top-N / categorical breakdown.)

  7. DEFAULT: kpi_grid + data_table
     (Scalar metrics or unclassified result.)

Non-chart types (always available regardless of rules above):
  kpi_grid        → ≤6 rows × ≤4 cols of scalar metrics (no time dimension)
  anomaly_callout → only when anomaly/spike/drop is the primary finding
  data_table      → raw drill-down reference
  ranking_table   → top/bottom N list with scores

Choose purpose — this controls WHERE the visual appears in the response:
  "leading_answer"     → The chart IS the primary answer (comparison, distribution, top-N ranking).
                         Use when a user asks "berapa / siapa / tampilkan / bandingkan" and the
                         chart answers it more directly than text.
                         anchor_after MUST be null — NOT "s1" or any section id.
                         It renders BEFORE all narrative sections begin.
                         WRONG:   {{"type": "bar_chart", "anchor_after": "s1", "purpose": "leading_answer"}}
                         CORRECT: {{"type": "bar_chart", "anchor_after": null, "purpose": "leading_answer"}}
  "supporting_evidence"→ The chart reinforces a specific claim made in anchor_after section.
                         The TEXT investigation is the primary answer; the chart supports it.
                         anchor_after must be the id of the section it supports ("s1", "s2", ...).

                         DECISION RULE — ask: "Is the chart the answer, or does the text explain
                         and the chart just shows the trend?"
                           Query = "berapa / tampilkan / bandingkan"  → chart IS the answer → leading_answer
                           Query = "kenapa / mengapa / apa penyebab / jelaskan / analisis" → text IS the answer → supporting_evidence

                         EXAMPLE for root_cause_analysis intent:
                           User: "kenapa GoPay turun bulan Juni?"
                           WRONG:   {{"type": "line_chart", "anchor_after": null,  "purpose": "leading_answer"}}
                           CORRECT: {{"type": "line_chart", "anchor_after": "s2", "purpose": "supporting_evidence"}}
                           Reason: the user wants an explanation (text is primary). The trend chart
                           sits inside the analysis section ("## Tren Harian") to support the claim,
                           not as the standalone opening answer.

  "detail_reference"   → Raw data table for drill-down. Not everyone needs it.
                         anchor_after should be the last section id.
                         Will always be rendered collapsed, at the bottom of the response.

anchor_after: null for leading_answer; a section id ("s1"–"s4") for all other purposes.

ORDERING within the same anchor_after group:
  If two blocks share the same anchor_after, the renderer always shows supporting_evidence
  before detail_reference — regardless of the order you write them in visual_blocks.
  You do NOT need to manually sort them; just declare what each block IS.

NEEDS_VISUAL:
  true  — data has ≥2 rows and at least one visual_block is meaningful
  false — single scalar result (1 row × 1 col), or no plottable data

═══════════════════════════════════════════════
OTHER RULES
═══════════════════════════════════════════════
- key_metrics: max 4 column names from data that are most important to bold in narrative.
- response_length: "brief" single-scalar or ≤3 rows; "standard" most queries; "detailed" for root_cause_analysis/complex_analytics/ranking_analysis.
- visual_blocks may be empty [] if no chart is useful.
- Output ONLY the JSON object."""

    # ─────────────────────────────────────────────────────────────
    # PARSE + VALIDATE
    # ─────────────────────────────────────────────────────────────

    def _parse_plan(self, raw: str) -> dict:
        """Parse LLM JSON, validate all fields, and sanitize invalid values."""
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

        plan = json.loads(text)

        # ── narrative_sections ──
        sections = plan.get("narrative_sections", [])
        if not isinstance(sections, list) or not sections:
            sections = [{"id": "s1", "title": None, "instruction": "Jawab pertanyaan langsung."}]
        # Ensure ids exist and are unique; backfill missing ids
        seen_ids: set[str] = set()
        clean_sections = []
        for i, s in enumerate(sections[:4]):
            sid = s.get("id") if isinstance(s.get("id"), str) else f"s{i + 1}"
            if not sid or sid in seen_ids:
                sid = f"s{i + 1}"
            seen_ids.add(sid)
            clean_sections.append({
                "id":          sid,
                "title":       s.get("title"),
                "instruction": s.get("instruction", "Tulis konten bagian ini."),
            })
        plan["narrative_sections"] = clean_sections

        # ── visual_blocks ──
        valid_section_ids = {s["id"] for s in clean_sections}
        last_section_id   = clean_sections[-1]["id"] if clean_sections else "s1"

        raw_blocks = plan.get("visual_blocks", [])
        if not isinstance(raw_blocks, list):
            raw_blocks = []

        clean_blocks: list[dict] = []
        for b in raw_blocks:
            if not isinstance(b, dict):
                continue
            vtype   = b.get("type", "")
            purpose = b.get("purpose", "supporting_evidence")
            anchor  = b.get("anchor_after")   # may be None/null or a section id string

            if vtype not in _VALID_VISUAL_TYPES:
                continue
            if purpose not in _VALID_PURPOSES:
                purpose = "supporting_evidence"

            # ── anchor_after enforcement (schema contract, not left to LLM) ──
            if purpose == "leading_answer":
                # MUST be null — renders before all sections, not anchored to any section.
                # Auto-fix silently; LLM frequently emits "s1" here by mistake.
                if anchor is not None:
                    self.log(
                        f"Auto-fixed anchor_after={anchor!r} → null for leading_answer block ({vtype})",
                        level="warning",
                    )
                anchor = None
            elif purpose == "detail_reference":
                # Always force to last section so it renders at the bottom.
                anchor = last_section_id
            else:
                # supporting_evidence — anchor must be a real section id.
                if anchor not in valid_section_ids:
                    anchor = "s1"

            clean_blocks.append({
                "type":         vtype,
                "anchor_after": anchor,
                "purpose":      purpose,
            })

        # Sort deterministically within each anchor group so the renderer doesn't depend
        # on LLM output order: null anchors first, then by section id, then by purpose tier.
        clean_blocks.sort(key=lambda b: (
            b["anchor_after"] or "",          # None → "" sorts before "s1", "s2", …
            _PURPOSE_RENDER_ORDER.get(b["purpose"], 1),
        ))

        # Dedup: remove exact (type, anchor_after, purpose) duplicates that LLMs occasionally
        # emit, e.g. two data_table blocks anchored to the same section.
        seen_block_keys: set[tuple] = set()
        deduped: list[dict] = []
        for b in clean_blocks:
            key = (b["type"], b["anchor_after"], b["purpose"])
            if key in seen_block_keys:
                self.log(
                    f"Duplicate visual_block removed: type={b['type']!r} "
                    f"anchor={b['anchor_after']!r} purpose={b['purpose']!r}",
                    level="warning",
                )
                continue
            seen_block_keys.add(key)
            deduped.append(b)
        clean_blocks = deduped

        plan["visual_blocks"] = clean_blocks

        # ── needs_visual — LLM hint; overridden by _compute_needs_visual() after parse ──
        if not isinstance(plan.get("needs_visual"), bool):
            plan["needs_visual"] = bool(clean_blocks)

        # ── response_length ──
        if plan.get("response_length") not in _VALID_LENGTHS:
            plan["response_length"] = "standard"

        # ── key_metrics ──
        if not isinstance(plan.get("key_metrics"), list):
            plan["key_metrics"] = []

        # ── anomaly_flag — derived for InsightGenerator backward compatibility ──
        plan["anomaly_flag"] = any(
            b["type"] == "anomaly_callout" for b in clean_blocks
        )

        return plan

    # ─────────────────────────────────────────────────────────────
    # NEEDS_VISUAL ENFORCEMENT
    # ─────────────────────────────────────────────────────────────

    def _compute_needs_visual(self, state: AgentState, plan: dict) -> bool:
        """
        Deterministically enforce needs_visual rules, overriding whatever the LLM said.

        Rules (in priority order):
          1. No visual_blocks → always False
          2. row_count < 2 → False (nothing to plot)
          3. Single scalar (1 row × 1 col) AND response_length == "brief" → False
          4. Multi-step: True if any step has ≥2 rows
          5. Otherwise: True
        """
        if not plan.get("visual_blocks"):
            return False

        if state.is_multi_step and state.step_results:
            return any(s.row_count >= 2 for s in state.step_results)

        # Analytics tool path: tool_results populated, query_result may be empty
        if state.tool_results:
            return any(tr.row_count >= 2 for tr in state.tool_results)

        row_count = state.row_count or (
            len(state.query_result) if state.query_result else 0
        )
        if row_count < 2:
            return False

        cols = list(state.query_result[0].keys()) if state.query_result else []
        is_scalar = (row_count == 1 and len(cols) == 1)
        if is_scalar and plan.get("response_length") == "brief":
            return False

        return True

    def _enforce_chart_rules(self, state: AgentState, plan: dict) -> dict:
        """
        Deterministic post-parse guard: enforce chart-selection rules the LLM
        might violate regardless of prompt compliance. Rules run in order so
        later rules see already-upgraded types (donut→bar→diverging_bar is valid).

        Rules enforced:
          1. donut_chart + entity_count > 6          → downgrade to bar_chart.
          2. bar_chart + has_pct_change + no time    → upgrade to diverging_bar_chart.
             Covers both single-step (query_result) and analytics tool path
             (tool_results from compare_periods / detect_anomaly) where ± deltas
             are pre-computed and need explicit sign direction in the chart.

        Guard condition: skip only when there is genuinely no data anywhere —
        neither query_result NOR tool_results.  The old guard (not state.query_result)
        incorrectly skipped analytics-path results where tool_results is populated
        but query_result is empty.
        """
        has_any_data = bool(state.query_result) or bool(state.tool_results)
        if state.is_multi_step or not has_any_data:
            return plan

        shape = self._build_data_shape(state)

        # entity_count: for tool_results path the value is nested inside steps[0],
        # not at the top level — extract from steps when top-level is missing (FIX 3).
        entity_count = shape.get("distinct_entity_count") or (
            shape["steps"][0].get("distinct_entity_count", 0) if shape.get("steps") else 0
        )

        # Detect pct_change, time, and ab_pair signals across single-step and tool_results shapes
        has_pct_change = shape.get("has_pct_change_column", False) or any(
            s.get("has_pct_change_column", False) for s in shape.get("steps", [])
        )
        has_time = shape.get("has_time_dimension", False) or any(
            s.get("has_time_dimension", False) for s in shape.get("steps", [])
        )
        has_ab_pairs = shape.get("has_ab_pair_columns", False) or any(
            s.get("has_ab_pair_columns", False) for s in shape.get("steps", [])
        )
        has_share_col = shape.get("has_share_column", False) or any(
            s.get("has_share_column", False) for s in shape.get("steps", [])
        )

        updated: list[dict] = []
        for b in plan.get("visual_blocks", []):
            # Rule 1: donut with too many entities → bar
            if b["type"] == "donut_chart" and entity_count > 6:
                self.log(
                    f"donut_chart → bar_chart (distinct_entity_count={entity_count} > 6)",
                    level="warning",
                )
                b = {**b, "type": "bar_chart"}

            # Rule 2: bar with pre-computed ± deltas → diverging_bar (skip if time-series)
            if b["type"] == "bar_chart" and has_pct_change and not has_time:
                self.log(
                    "bar_chart → diverging_bar_chart (has_pct_change_column=true, no time dimension)",
                    level="warning",
                )
                b = {**b, "type": "diverging_bar_chart"}

            updated.append(b)

        # Rule 3: data has *_a/*_b column pairs (compare_periods pattern) → ensure a
        # grouped_bar_chart block is present so absolute period values are charted.
        # This is injected deterministically regardless of what the LLM emitted — the LLM
        # prompt also knows about this type but may omit it; this guard is the backstop.
        if has_ab_pairs and not any(b["type"] == "grouped_bar_chart" for b in updated):
            sections = plan.get("narrative_sections", [])
            anchor = sections[0]["id"] if sections else "s1"
            updated.append({
                "type":         "grouped_bar_chart",
                "anchor_after": anchor,
                "purpose":      "supporting_evidence",
            })
            self.log(
                "grouped_bar_chart injected: data contains *_a/*_b column pairs (compare_periods schema)",
                level="warning",
            )

        # Rule 4: share distribution with ≤6 entities → replace bar_chart with donut blocks.
        # Inject one donut_chart visual block per *_share_pct column so InsightGenerator
        # produces a separate donut for trx_share_pct and rev_share_pct.
        if has_share_col and 0 < entity_count <= 6 and not has_time and not has_pct_change:
            _cols_list = shape.get("columns") or (
                shape["steps"][0].get("columns", []) if shape.get("steps") else []
            )
            _n_share_pct = len([c for c in _cols_list if c.endswith("_share_pct")])
            _n_donuts = min(max(1, _n_share_pct), 2)
            _donut_injected = False
            _rule4_updated: list[dict] = []
            for _b in updated:
                if _b["type"] in ("bar_chart", "diverging_bar_chart") and not _donut_injected:
                    for _ in range(_n_donuts):
                        _rule4_updated.append({**_b, "type": "donut_chart"})
                    _donut_injected = True
                    self.log(
                        f"bar_chart → {_n_donuts}× donut_chart "
                        f"(entity_count={entity_count} ≤ 6, _share_pct cols={_n_share_pct})",
                        level="warning",
                    )
                else:
                    _rule4_updated.append(_b)
            updated = _rule4_updated

        # Rule 5: pure distribution data with >10 entities → enforce data_table, remove charts.
        # Applies only to share/distribution data (no pct_change, no time, no ab_pairs).
        # Avoids accidental removal for compare_periods (has_pct_change) or trend (has_time).
        _CHART_BLOCK_TYPES = {"bar_chart", "line_chart", "donut_chart", "diverging_bar_chart", "grouped_bar_chart"}
        if entity_count > 10 and has_share_col and not has_time and not has_pct_change and not has_ab_pairs:
            if any(b["type"] in _CHART_BLOCK_TYPES for b in updated):
                self.log(
                    f"entity_count={entity_count} > 10, distribution data → removing chart blocks, enforcing data_table",
                    level="warning",
                )
                non_chart = [b for b in updated if b["type"] not in _CHART_BLOCK_TYPES]
                if not any(b["type"] == "data_table" for b in non_chart):
                    sections = plan.get("narrative_sections", [])
                    anchor = sections[0]["id"] if sections else "s1"
                    non_chart.append({"type": "data_table", "anchor_after": anchor, "purpose": "data"})
                updated = non_chart

        plan["visual_blocks"] = updated
        return plan

    def _apply_anomaly_flag(self, state: AgentState, plan: dict) -> dict:
        """Auto-set anomaly_flag=True when detect_anomaly returned anomalous entities.

        _parse_plan() sets anomaly_flag only when the LLM emits an anomaly_callout block,
        which it rarely does. This guard ensures InsightGenerator receives anomaly_flag=True
        whenever the data actually warrants it, regardless of LLM chart selection.

        Only fires when anomaly_flag is currently False (does not override an existing True).
        """
        if plan.get("anomaly_flag"):
            return plan  # already set via anomaly_callout block in _parse_plan

        for tr in state.tool_results:
            if tr.tool_name != "detect_anomaly":
                continue
            if any(row.get("is_anomaly") for row in tr.data):
                plan["anomaly_flag"] = True
                self.log(
                    "anomaly_flag auto-set: detect_anomaly tool returned is_anomaly=true row(s)",
                    level="warning",
                )
                return plan

        return plan

    # ─────────────────────────────────────────────────────────────
    # DEFAULT PLAN
    # ─────────────────────────────────────────────────────────────

    def _default_plan(self, intent: object) -> dict:
        """Fallback plan when LLM call fails or data is empty."""
        intent_str = ""
        if isinstance(intent, dict):
            intent_str = intent.get("category", "")
        elif isinstance(intent, str):
            intent_str = intent

        length = "detailed" if intent_str in {
            "root_cause_analysis", "complex_analytics"
        } else "standard"

        return {
            "narrative_sections": [
                {"id": "s1", "title": None,
                 "instruction": "Jawab pertanyaan langsung dengan angka utama dan verdict SEHAT/PERHATIAN/KRITIS."},
                {"id": "s2", "title": "## Konteks & Analisis",
                 "instruction": "Buat 3–4 bullet poin konteks, perbandingan, dan implikasi."},
            ],
            "visual_blocks": [
                {"type": "data_table", "anchor_after": "s2", "purpose": "detail_reference"},
            ],
            "needs_visual":    False,
            "key_metrics":     [],
            "response_length": length,
            "anomaly_flag":    False,
        }
