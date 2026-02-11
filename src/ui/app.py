"""
Streamlit UI - Text-to-SQL Chatbot

Simple web interface for non-technical users to query databases
using natural language.
"""

import streamlit as st
import requests
import json
import pandas as pd

# Page config
st.set_page_config(
    page_title="Text-to-SQL Chatbot",
    page_icon="🤖",
    layout="wide"
)

# API endpoint
API_URL = "http://localhost:8000"

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        margin: 1rem 0;
    }
    .error-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8d7da;
        border: 1px solid #f5c6cb;
        margin: 1rem 0;
    }
    .sql-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f8f9fa;
        border: 1px solid #dee2e6;
        font-family: monospace;
        font-size: 0.9rem;
    }
</style>
""", unsafe_allow_html=True)

# Header
st.markdown('<div class="main-header">🤖 Text-to-SQL Chatbot</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Tanya apa saja tentang data Anda dalam bahasa natural!</div>', unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.header("⚙️ Pengaturan")
    
    # Database selection
    database = st.selectbox(
        "Pilih Database",
        ["sales_db", "products_db", "analytics_db"],
        help="Pilih database yang ingin Anda query"
    )
    
    st.markdown("---")
    
    # Info
    st.subheader("ℹ️ Informasi Database")
    
    if database == "sales_db":
        st.write("**Sales Database**")
        st.write("📊 Tables:")
        st.write("- customers (100 rows)")
        st.write("- orders (500 rows)")
        st.write("- payments (500 rows)")
    elif database == "products_db":
        st.write("**Products Database**")
        st.write("📦 Tables:")
        st.write("- products (50 rows)")
        st.write("- sellers (20 rows)")
        st.write("- order_items (500 rows)")
    else:
        st.write("**Analytics Database**")
        st.write("📈 Tables:")
        st.write("- customer_segments (100 rows)")
        st.write("- daily_metrics (90 rows)")
    
    st.markdown("---")
    
    # Example queries
    st.subheader("💡 Contoh Pertanyaan")
    
    examples = {
        "sales_db": [
            "Berapa jumlah customer?",
            "Total revenue berapa?",
            "Top 5 customer berdasarkan spending",
            "Berapa order bulan ini?",
            "Customer dari Jakarta"
        ],
        "products_db": [
            "Berapa jumlah produk?",
            "Produk dari kategori Electronics",
            "Top 3 seller",
            "Rata-rata harga produk"
        ],
        "analytics_db": [
            "Berapa customer VIP?",
            "Total sales 7 hari terakhir",
            "Customer lifetime value tertinggi"
        ]
    }
    
    for example in examples.get(database, []):
        st.write(f"• {example}")

# Main content
col1, col2 = st.columns([3, 1])

with col1:
    # Query input
    user_question = st.text_input(
        "💬 Tanyakan sesuatu:",
        placeholder="Contoh: Berapa total revenue bulan ini?",
        help="Ketik pertanyaan Anda dalam bahasa natural"
    )

with col2:
    # Button
    st.write("")  # Spacer
    ask_button = st.button("🚀 Tanya!", type="primary", use_container_width=True)

# Process query
if ask_button and user_question:
    with st.spinner("🔄 Sedang memproses pertanyaan Anda..."):
        try:
            # Call API
            response = requests.post(
                f"{API_URL}/query",
                json={
                    "question": user_question,
                    "database": database
                },
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Success message
                st.markdown('<div class="success-box">✅ <strong>Query berhasil!</strong></div>', unsafe_allow_html=True)
                
                # Display results in tabs
                tab1, tab2, tab3 = st.tabs(["📊 Hasil", "🔍 SQL Query", "⚙️ Metadata"])
                
                with tab1:
                    st.subheader("📊 Hasil Query")
                    
                    if result['data'] and len(result['data']) > 0:
                        # Convert to DataFrame for better display
                        df = pd.DataFrame(result['data'])
                        
                        # Format numbers
                        for col in df.columns:
                            if df[col].dtype in ['float64', 'int64']:
                                if 'value' in col.lower() or 'revenue' in col.lower() or 'spending' in col.lower() or 'price' in col.lower():
                                    # Format as currency
                                    df[col] = df[col].apply(lambda x: f"Rp {x:,.2f}" if pd.notnull(x) else "")
                        
                        st.dataframe(df, use_container_width=True, height=400)
                        
                        # Summary
                        st.info(f"📈 Menampilkan **{result['row_count']}** baris data")
                        
                        # Download button
                        csv = df.to_csv(index=False)
                        st.download_button(
                            label="📥 Download CSV",
                            data=csv,
                            file_name=f"query_result_{database}.csv",
                            mime="text/csv"
                        )
                    else:
                        st.warning("⚠️ Query tidak mengembalikan data")
                
                with tab2:
                    st.subheader("🔍 SQL Query yang Di-generate")
                    st.markdown(f'<div class="sql-box">{result["sql"]}</div>', unsafe_allow_html=True)
                    
                    # Copy button
                    st.code(result['sql'], language='sql')
                
                with tab3:
                    st.subheader("⚙️ Metadata")
                    
                    col1, col2, col3 = st.columns(3)
                    
                    with col1:
                        st.metric(
                            "⏱️ Total Waktu",
                            f"{result['execution_time_ms']:.0f} ms"
                        )
                    
                    with col2:
                        st.metric(
                            "🗄️ Database",
                            result['metadata']['database']
                        )
                    
                    with col3:
                        st.metric(
                            "📊 Jumlah Baris",
                            result['row_count']
                        )
                    
                    # Detailed metadata
                    with st.expander("📋 Detail Lengkap"):
                        st.json(result['metadata'])
            
            else:
                st.markdown(f'<div class="error-box">❌ <strong>Error:</strong> {response.text}</div>', unsafe_allow_html=True)
        
        except requests.exceptions.Timeout:
            st.markdown('<div class="error-box">⏱️ <strong>Timeout:</strong> Query terlalu lama. Coba query yang lebih sederhana.</div>', unsafe_allow_html=True)
        
        except requests.exceptions.ConnectionError:
            st.markdown('<div class="error-box">🔌 <strong>Connection Error:</strong> Tidak bisa terhubung ke API. Pastikan API server sedang running di http://localhost:8000</div>', unsafe_allow_html=True)
        
        except Exception as e:
            st.markdown(f'<div class="error-box">❌ <strong>Error:</strong> {str(e)}</div>', unsafe_allow_html=True)

elif ask_button and not user_question:
    st.warning("⚠️ Silakan masukkan pertanyaan terlebih dahulu!")

# Footer
st.markdown("---")
st.markdown(
    """
    <div style="text-align: center; color: #666; font-size: 0.9rem;">
        <p>💡 <strong>Tips:</strong> Tanyakan dalam bahasa natural seperti berbicara dengan manusia!</p>
        <p>🤖 Powered by Claude Sonnet 4 | 🗄️ PostgreSQL | ⚡ FastAPI</p>
    </div>
    """,
    unsafe_allow_html=True
)