"""
Streamlit UI - Text-to-SQL Chatbot

Web interface for querying databases using natural language.
Database is auto-detected by the system — no manual selection needed.
"""

import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="Text-to-SQL Chatbot",
    page_icon="🤖",
    layout="wide"
)

API_URL = os.getenv("API_URL", "http://localhost:8000")

# ─────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = []
if "chat_display" not in st.session_state:
    st.session_state.chat_display = []  # list of {role, content, type, data}

# ─────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');

    html, body, [class*="css"] {
        font-family: 'IBM Plex Sans', sans-serif;
    }

    .main-header {
        font-family: 'IBM Plex Mono', monospace;
        font-size: 2rem;
        font-weight: 600;
        color: #0f172a;
        letter-spacing: -0.02em;
        margin-bottom: 0.25rem;
    }

    .sub-header {
        font-size: 1rem;
        color: #64748b;
        margin-bottom: 2rem;
    }

    .insight-box {
        padding: 1.25rem 1.5rem;
        border-radius: 0.75rem;
        background: linear-gradient(135deg, #eff6ff 0%, #f0fdf4 100%);
        border-left: 4px solid #3b82f6;
        margin: 1rem 0;
        font-size: 1rem;
        line-height: 1.6;
    }

    .clarification-box {
        padding: 1.25rem 1.5rem;
        border-radius: 0.75rem;
        background: #fffbeb;
        border-left: 4px solid #f59e0b;
        margin: 1rem 0;
    }

    .clarification-title {
        font-weight: 600;
        color: #92400e;
        margin-bottom: 0.5rem;
        font-size: 0.95rem;
    }

    .suggestion-chip {
        display: inline-block;
        padding: 0.35rem 0.75rem;
        border-radius: 999px;
        background: #e0f2fe;
        color: #0369a1;
        font-size: 0.85rem;
        margin: 0.25rem;
        cursor: pointer;
        border: 1px solid #bae6fd;
    }

    .db-badge {
        display: inline-block;
        padding: 0.2rem 0.6rem;
        border-radius: 0.375rem;
        background: #f1f5f9;
        color: #475569;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.8rem;
        border: 1px solid #e2e8f0;
    }

    .metric-card {
        padding: 1rem;
        border-radius: 0.75rem;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        text-align: center;
    }

    .sql-container {
        background: #0f172a;
        border-radius: 0.75rem;
        padding: 1.25rem;
        font-family: 'IBM Plex Mono', monospace;
        font-size: 0.875rem;
        color: #e2e8f0;
        overflow-x: auto;
        white-space: pre-wrap;
    }

    .error-box {
        padding: 1rem 1.5rem;
        border-radius: 0.75rem;
        background: #fef2f2;
        border-left: 4px solid #ef4444;
        color: #7f1d1d;
    }

    .stButton > button {
        border-radius: 0.5rem;
        font-family: 'IBM Plex Sans', sans-serif;
        font-weight: 600;
    }

    .stTextInput > div > div > input {
        border-radius: 0.5rem;
        font-family: 'IBM Plex Sans', sans-serif;
    }

    .chat-user {
        display: flex;
        justify-content: flex-end;
        margin: 0.5rem 0;
    }

    .chat-user-bubble {
        background: #3b82f6;
        color: #fff;
        padding: 0.6rem 1rem;
        border-radius: 1rem 1rem 0.25rem 1rem;
        max-width: 70%;
        font-size: 0.95rem;
        line-height: 1.5;
    }

    .chat-assistant {
        display: flex;
        justify-content: flex-start;
        margin: 0.5rem 0;
    }

    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────
st.markdown('<div class="main-header">🤖 Text-to-SQL Chatbot</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tanya apa saja tentang data Anda — sistem akan otomatis memilih database yang tepat.</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("💡 Tips Bertanya")

    st.markdown("""
    **✅ Pertanyaan yang bagus:**
    - Gunakan kata kerja: *tampilkan*, *berapa*, *success rate*
    - Sebutkan entitas: *partner*, *produk*, *transaksi*, *revenue*
    - Spesifik: *"success rate per partner bulan Mei 2026"*

    **❌ Hindari:**
    - Terlalu singkat: *"data transaksi"*
    - Tanpa konteks: *"tampilkan semua"*
    """)

    st.markdown("---")
    st.subheader("📌 Contoh Pertanyaan")

    examples = [
        "Berapa total transaksi bulan April 2026?",
        "Success rate per partner bulan Mei 2026",
        "10 produk dengan revenue tertinggi",
        "Total transaksi linkaja semua variannya",
        "Revenue gopay vs ovo vs dana",
        "Jam berapa paling banyak transaksi?",
        "Produk dengan success rate di bawah 80%",
        "Net gap terbesar per payment provider",
        "Tren transaksi harian bulan April 2026",
        "Berapa pengguna aktif harian rata-rata?",
    ]

    for ex in examples:
        st.markdown(f"• {ex}")

    st.markdown("---")
    st.caption("🔄 Data: Telkomsel Payment Platform • Mar–Mei 2026")

    st.markdown("---")
    if st.button("🗑️ Bersihkan Percakapan", use_container_width=True):
        st.session_state.conversation_history = []
        st.session_state.chat_display = []
        st.rerun()

# ─────────────────────────────────────────────
# QUERY INPUT
# ─────────────────────────────────────────────
with st.form(key="query_form"):
    col_input, col_btn = st.columns([5, 1])

    with col_input:
        user_question = st.text_input(
            "💬 Pertanyaan Anda:",
            placeholder="Contoh: success rate per partner bulan Mei 2026, urutkan dari yang terendah",
            label_visibility="collapsed"
        )

    with col_btn:
        ask_button = st.form_submit_button("🚀 Tanya", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
# RENDER CHAT HISTORY
# ─────────────────────────────────────────────
def _render_data_table(data: list, row_count: int) -> None:
    """Render query result as a formatted dataframe with download button."""
    if not data:
        st.info("ℹ️ Query tidak mengembalikan data.")
        return

    df = pd.DataFrame(data)
    MONEY_KEYWORDS = ["revenue", "gap", "fee", "price"]
    TRX_KEYWORDS = ["_trx", "transaksi", "users", "unique"]
    for col in df.columns:
        col_lower = col.lower()
        is_money = any(k in col_lower for k in MONEY_KEYWORDS)
        is_trx = any(k in col_lower for k in TRX_KEYWORDS)
        if is_money and not is_trx and df[col].dtype in ["float64", "int64"]:
            df[col] = df[col].apply(
                lambda x: f"Rp {x:,.0f}" if pd.notnull(x) else ""
            )

    st.dataframe(df, use_container_width=True, height=400)
    col_info, col_download = st.columns([3, 1])
    with col_info:
        st.caption(f"📈 {row_count} baris data")
    with col_download:
        csv = pd.DataFrame(data).to_csv(index=False)
        st.download_button(
            "📥 Download CSV",
            data=csv,
            file_name="query_result.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _render_assistant_entry(entry: dict) -> None:
    """Render one assistant chat entry with insight, SQL tab, results, and plan expander."""
    result = entry.get("result", {})
    metadata = result.get("metadata", {})

    if metadata.get("needs_clarification"):
        reason = metadata.get("clarification_reason", "")
        st.markdown(f"""
        <div class="clarification-box">
            <div class="clarification-title">⚠️ Pertanyaan Perlu Diperjelas</div>
            <p style="margin: 0.5rem 0; color: #78350f;">{reason}</p>
        </div>
        """, unsafe_allow_html=True)
        return

    detected_db = metadata.get("database", "")
    if detected_db:
        st.markdown(
            f'🗄️ Database: <span class="db-badge">{detected_db}</span>',
            unsafe_allow_html=True,
        )

    # Multi-step plan expander
    if result.get("is_multi_step") and result.get("step_results"):
        with st.expander("📋 Plan Analisis", expanded=False):
            for step in result["step_results"]:
                st.markdown(
                    f"**Step {step['step_number']}: {step['description']}** "
                    f"— {step['row_count']} baris"
                )
                if step.get("sql"):
                    st.code(step["sql"], language="sql")

    tab1, tab2, tab3 = st.tabs(["📊 Hasil", "🔍 SQL Query", "⚙️ Detail"])

    with tab1:
        if result.get("insights"):
            st.markdown(
                f'<div class="insight-box">💡 {result["insights"]}</div>',
                unsafe_allow_html=True,
            )
        _render_data_table(result.get("data") or [], result.get("row_count", 0))

    with tab2:
        if result.get("sql"):
            st.code(result["sql"], language="sql")

    with tab3:
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("⏱️ Waktu", f"{result.get('execution_time_ms', 0) / 1000:.2f} s")
        with c2:
            st.metric("🗄️ Database", detected_db)
        with c3:
            st.metric("📊 Baris", result.get("row_count", 0))
        with st.expander("🔎 Detail Lengkap"):
            st.json(metadata)


for entry in st.session_state.chat_display:
    if entry["role"] == "user":
        st.markdown(
            f'<div class="chat-user"><div class="chat-user-bubble">💬 {entry["content"]}</div></div>',
            unsafe_allow_html=True,
        )
    else:
        with st.container():
            _render_assistant_entry(entry)

# ─────────────────────────────────────────────
# PROCESS QUERY
# ─────────────────────────────────────────────
if ask_button and user_question:
    with st.spinner("⏳ Memproses pertanyaan..."):
        try:
            response = requests.post(
                f"{API_URL}/query",
                json={
                    "question": user_question,
                    "database": "financial_db",
                    "conversation_history": st.session_state.conversation_history,
                },
                timeout=120,
            )

            if response.status_code == 200:
                result = response.json()

                # Update conversation memory from server response
                st.session_state.conversation_history = result.get(
                    "conversation_history", []
                )

                # Append to display thread
                st.session_state.chat_display.append(
                    {"role": "user", "content": user_question}
                )
                st.session_state.chat_display.append(
                    {"role": "assistant", "result": result}
                )

            else:
                error_detail = response.json().get("detail", response.text)
                st.markdown(
                    f'<div class="error-box">❌ <strong>Error:</strong> {error_detail}</div>',
                    unsafe_allow_html=True,
                )

            st.rerun()

        except requests.exceptions.Timeout:
            st.markdown(
                '<div class="error-box">⏱️ <strong>Timeout:</strong> Query terlalu lama. Coba pertanyaan yang lebih sederhana.</div>',
                unsafe_allow_html=True,
            )
        except requests.exceptions.ConnectionError:
            st.markdown(
                '<div class="error-box">🔌 <strong>Connection Error:</strong> Tidak bisa terhubung ke API. Pastikan server berjalan di http://localhost:8000</div>',
                unsafe_allow_html=True,
            )
        except Exception as e:
            st.markdown(
                f'<div class="error-box">❌ <strong>Error:</strong> {str(e)}</div>',
                unsafe_allow_html=True,
            )

elif ask_button and not user_question:
    st.warning("⚠️ Silakan masukkan pertanyaan terlebih dahulu!")

# ─────────────────────────────────────────────
# FOOTER
# ─────────────────────────────────────────────
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #94a3b8; font-size: 0.85rem; font-family: 'IBM Plex Mono', monospace;">
        Text-to-SQL Chatbot • PostgreSQL • FastAPI • ChromaDB + BM25 + Graph
    </div>
    """,
    unsafe_allow_html=True
)
