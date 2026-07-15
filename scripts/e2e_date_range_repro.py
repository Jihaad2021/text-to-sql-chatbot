"""
Reproduksi end-to-end date range guard — dua skenario.

Skenario A: "bulan ini" pada 2026-07-03, data_end_date=2026-06-30
  → query_out_of_range harus True
  → InsightGenerator skip LLM, kembalikan template message

Skenario B: periode VALID (Juni 2026, dalam rentang data), genuinely 0 baris
  → query_out_of_range tetap False
  → InsightGenerator panggil LLM → verdict BOLEH muncul
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from datetime import date, datetime
from unittest.mock import MagicMock, patch

from src.agents.query_rewriter import QueryRewriter
from src.agents.insight_generator import InsightGenerator
from src.models.agent_state import AgentState

SEPARATOR = "=" * 65


# ─────────────────────────────────────────────────────────────
# SKENARIO A
# ─────────────────────────────────────────────────────────────
def scenario_a():
    print(SEPARATOR)
    print("SKENARIO A — 'bulan ini' pada 2026-07-03, data s.d. 2026-06-30")
    print(SEPARATOR)

    # LLM QueryRewriter mendeteksi "bulan ini" → period_start = 2026-07-01
    rewriter_response = json.dumps({
        "rewritten": "bagaimana performa transaksi bulan Juli 2026?",
        "changes": ["'bulan ini' diubah ke Juli 2026"],
        "was_rewritten": True,
        "period_start": "2026-07-01",   # ← first of current month on 2026-07-03
    })

    state = AgentState(
        query="bagaimana performa transaksi bulan ini?",
        database="financial_db",
        data_end_date=date(2026, 6, 30),   # ← MAX(date) dari daily_master
    )

    print(f"\n[INPUT]")
    print(f"  state.query          = {state.query!r}")
    print(f"  state.data_end_date  = {state.data_end_date}")

    with patch.object(QueryRewriter, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4o-mini")):
        rewriter = QueryRewriter()

    with patch.object(rewriter, "_call_llm", return_value=rewriter_response):
        state = rewriter.run(state)

    print(f"\n[SETELAH QueryRewriter]")
    print(f"  state.query              = {state.query!r}")
    print(f"  state.query_out_of_range = {state.query_out_of_range}")
    print(f"  state.out_of_range_latest= {state.out_of_range_latest!r}")

    assert state.query_out_of_range is True, "FAIL: query_out_of_range harus True"
    assert state.out_of_range_latest == "2026-06-30", "FAIL: latest harus 2026-06-30"

    # Jalankan InsightGenerator — harus skip LLM
    with patch.object(InsightGenerator, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4o-mini")):
        ig = InsightGenerator()

    llm_call_tracker = MagicMock(return_value="SHOULD NOT BE CALLED")
    with patch.object(ig, "_call_llm", llm_call_tracker):
        state = ig.run(state)

    print(f"\n[SETELAH InsightGenerator]")
    print(f"  _call_llm dipanggil      = {llm_call_tracker.called}")
    print(f"  state.insights           =")
    print(f"    {state.insights!r}")

    assert not llm_call_tracker.called, "FAIL: LLM tidak boleh dipanggil"
    assert "30 Juni 2026" in state.insights, "FAIL: harus ada tanggal 30 Juni 2026"
    assert "Belum ada data" in state.insights, "FAIL: harus ada teks 'Belum ada data'"
    assert "KRITIS" not in state.insights, "FAIL: tidak boleh ada verdict KRITIS"
    assert "WARNING" not in state.insights, "FAIL: tidak boleh ada verdict WARNING"

    print("\n  ✓ query_out_of_range = True")
    print("  ✓ LLM tidak dipanggil")
    print("  ✓ Template message berisi tanggal terakhir dalam format Indonesia")
    print("  ✓ Tidak ada verdict KRITIS/WARNING")
    print("\n  SKENARIO A → LULUS\n")


# ─────────────────────────────────────────────────────────────
# SKENARIO B
# ─────────────────────────────────────────────────────────────
def scenario_b():
    print(SEPARATOR)
    print("SKENARIO B — periode VALID (Juni 2026), genuinely 0 baris data")
    print(SEPARATOR)

    # QueryRewriter menyetujui periode ini sebagai VALID (dalam rentang data)
    rewriter_response = json.dumps({
        "rewritten": "bagaimana performa transaksi partner XYZ bulan Juni 2026?",
        "changes": [],
        "was_rewritten": False,
        "period_start": "2026-06-01",   # ← DALAM rentang data (s.d. 2026-06-30)
    })

    state = AgentState(
        query="bagaimana performa transaksi partner XYZ bulan Juni 2026?",
        database="financial_db",
        data_end_date=date(2026, 6, 30),
    )

    print(f"\n[INPUT]")
    print(f"  state.query          = {state.query!r}")
    print(f"  state.data_end_date  = {state.data_end_date}")

    with patch.object(QueryRewriter, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4o-mini")):
        rewriter = QueryRewriter()

    with patch.object(rewriter, "_call_llm", return_value=rewriter_response):
        state = rewriter.run(state)

    print(f"\n[SETELAH QueryRewriter]")
    print(f"  state.query_out_of_range = {state.query_out_of_range}")
    print(f"  state.out_of_range_latest= {state.out_of_range_latest!r}")

    assert state.query_out_of_range is False, "FAIL: query_out_of_range harus False untuk periode valid"

    # Simulasi: QueryExecutor sudah jalan, hasilnya genuinely 0 baris
    # (bukan 1-row-all-NULL — sudah dinormalkan oleh analytics_tools._run())
    state.query_result  = []
    state.row_count     = 0
    state.validated_sql = (
        "SELECT SUM(total_trx) FROM daily_master "
        "WHERE partner_group = 'XYZ' "
        "AND date BETWEEN '2026-06-01' AND '2026-06-30'"
    )
    state.intent = {"category": "trend_analysis"}

    print(f"\n[STATE sebelum InsightGenerator]")
    print(f"  state.query_result       = {state.query_result!r}")
    print(f"  state.row_count          = {state.row_count}")

    # LLM InsightGenerator mengembalikan insight + VERDICT (karena data valid tapi kosong)
    llm_verdict_reply = (
        "Tidak ditemukan data transaksi untuk partner XYZ pada Juni 2026. "
        "Berdasarkan threshold SR <98%, kondisi ini memerlukan investigasi lebih lanjut. "
        "**Verdict: PERHATIAN** — partner XYZ belum memiliki aktivitas di periode ini."
    )

    with patch.object(InsightGenerator, "_init_client",
                      return_value=("openai", MagicMock(), "gpt-4o-mini")):
        ig = InsightGenerator()

    llm_call_tracker = MagicMock(return_value=llm_verdict_reply)
    with patch.object(ig, "_call_llm", llm_call_tracker):
        state = ig.run(state)

    print(f"\n[SETELAH InsightGenerator]")
    print(f"  _call_llm dipanggil      = {llm_call_tracker.called}")
    print(f"  state.insights           =")
    print(f"    {state.insights!r}")

    assert llm_call_tracker.called, "FAIL: LLM HARUS dipanggil untuk periode valid"
    assert "PERHATIAN" in state.insights or "KRITIS" in state.insights or "Verdict" in state.insights, \
        "FAIL: verdict harus muncul untuk data valid dengan 0 baris"

    print("\n  ✓ query_out_of_range = False (periode dalam rentang data)")
    print("  ✓ LLM dipanggil normal — guard out-of-range tidak mem-block")
    print("  ✓ Verdict PERHATIAN muncul dalam output InsightGenerator")
    print("\n  SKENARIO B → LULUS\n")


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    scenario_a()
    scenario_b()
    print(SEPARATOR)
    print("SEMUA SKENARIO LULUS")
    print(SEPARATOR)
