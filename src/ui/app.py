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
    - Gunakan kata kerja: *tampilkan*, *berapa*, *siapa*
    - Sebutkan entitas: *customer*, *order*, *produk*
    - Spesifik: *"top 5 customer berdasarkan spending"*

    **❌ Hindari:**
    - Terlalu singkat: *"data customer"*
    - Tanpa konteks: *"tampilkan semua"*
    """)

    st.markdown("---")
    st.subheader("📌 Contoh Pertanyaan")

    examples = [
        "Berapa jumlah total customer?",
        "Tampilkan customer dari Jakarta",
        "Siapa 5 customer dengan spending tertinggi?",
        "Berapa total nilai semua pembayaran?",
        "Tampilkan semua orders yang statusnya delivered",
        "Berapa jumlah produk yang tersedia?",
        "Seller mana yang paling banyak menjual?",
        "Berapa rata-rata nilai order per customer?",
    ]

    for ex in examples:
        st.markdown(f"• {ex}")

    st.markdown("---")
    st.caption("🔄 Database dipilih otomatis oleh sistem berdasarkan pertanyaan Anda.")

# ─────────────────────────────────────────────
# QUERY INPUT
# ─────────────────────────────────────────────
with st.form(key="query_form"):
    col_input, col_btn = st.columns([5, 1])

    with col_input:
        user_question = st.text_input(
            "💬 Pertanyaan Anda:",
            placeholder="Contoh: Siapa 5 customer dengan total pembelian tertinggi?",
            label_visibility="collapsed"
        )

    with col_btn:
        ask_button = st.form_submit_button("🚀 Tanya", type="primary", use_container_width=True)

# ─────────────────────────────────────────────
# PROCESS QUERY
# ─────────────────────────────────────────────
if ask_button and user_question:
    with st.spinner("⏳ Memproses pertanyaan..."):
        try:
            response = requests.post(
                f"{API_URL}/query",
                json={"question": user_question},
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                metadata = result.get("metadata", {})

                # ── Needs Clarification ──────────────────
                if metadata.get("needs_clarification"):
                    reason = metadata.get("clarification_reason", "")
                    st.markdown(f"""
                    <div class="clarification-box">
                        <div class="clarification-title">⚠️ Pertanyaan Perlu Diperjelas</div>
                        <p style="margin: 0.5rem 0; color: #78350f;">{reason}</p>
                        <p style="margin: 0.5rem 0; color: #78350f; font-size: 0.9rem;">
                            <strong>Saran:</strong> Coba pertanyaan yang lebih spesifik dengan menyebutkan entitas data
                            (customer, order, produk, dll) dan kata kerja yang jelas (tampilkan, berapa, siapa).
                        </p>
                    </div>
                    """, unsafe_allow_html=True)

                    # Suggestion chips
                    st.markdown("**💡 Coba pertanyaan seperti ini:**")
                    suggestions = [
                        "Tampilkan semua customer",
                        "Berapa total order?",
                        "Siapa customer dengan spending tertinggi?",
                        "Berapa jumlah produk?"
                    ]
                    cols = st.columns(len(suggestions))
                    for i, sug in enumerate(suggestions):
                        with cols[i]:
                            st.markdown(f'<span class="suggestion-chip">📌 {sug}</span>', unsafe_allow_html=True)

                # ── Success ──────────────────────────────
                else:
                    # Database badge
                    detected_db = metadata.get("database", "")
                    if detected_db:
                        st.markdown(
                            f'🗄️ Database yang digunakan: <span class="db-badge">{detected_db}</span>',
                            unsafe_allow_html=True
                        )
                        st.markdown("")

                    # Tabs
                    tab1, tab2, tab3 = st.tabs(["📊 Hasil", "🔍 SQL Query", "⚙️ Detail"])

                    with tab1:
                        # Insights
                        if result.get("insights"):
                            st.markdown(
                                f'<div class="insight-box">💡 {result["insights"]}</div>',
                                unsafe_allow_html=True
                            )

                        # Data table
                        if result.get("data") and len(result["data"]) > 0:
                            df = pd.DataFrame(result["data"])

                            # Format currency columns
                            for col in df.columns:
                                if any(k in col.lower() for k in ["value", "revenue", "spending", "price", "total"]):
                                    if df[col].dtype in ["float64", "int64"]:
                                        df[col] = df[col].apply(
                                            lambda x: f"Rp {x:,.2f}" if pd.notnull(x) else ""
                                        )

                            st.dataframe(df, use_container_width=True, height=400)

                            col_info, col_download = st.columns([3, 1])
                            with col_info:
                                st.caption(f"📈 {result['row_count']} baris data")
                            with col_download:
                                csv = pd.DataFrame(result["data"]).to_csv(index=False)
                                st.download_button(
                                    "📥 Download CSV",
                                    data=csv,
                                    file_name="query_result.csv",
                                    mime="text/csv",
                                    use_container_width=True
                                )
                        else:
                            st.info("ℹ️ Query tidak mengembalikan data.")

                    with tab2:
                        if result.get("sql"):
                            st.code(result["sql"], language="sql")

                    with tab3:
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.metric("⏱️ Waktu", f"{result['execution_time_ms'] / 1000:.2f} s")
                        with c2:
                            st.metric("🗄️ Database", detected_db)
                        with c3:
                            st.metric("📊 Baris", result["row_count"])

                        with st.expander("🔎 Detail Lengkap"):
                            st.json(metadata)

            else:
                error_detail = response.json().get("detail", response.text)
                st.markdown(
                    f'<div class="error-box">❌ <strong>Error:</strong> {error_detail}</div>',
                    unsafe_allow_html=True
                )

        except requests.exceptions.Timeout:
            st.markdown(
                '<div class="error-box">⏱️ <strong>Timeout:</strong> Query terlalu lama. Coba pertanyaan yang lebih sederhana.</div>',
                unsafe_allow_html=True
            )
        except requests.exceptions.ConnectionError:
            st.markdown(
                '<div class="error-box">🔌 <strong>Connection Error:</strong> Tidak bisa terhubung ke API. Pastikan server berjalan di http://localhost:8000</div>',
                unsafe_allow_html=True
            )
        except Exception as e:
            st.markdown(
                f'<div class="error-box">❌ <strong>Error:</strong> {str(e)}</div>',
                unsafe_allow_html=True
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
