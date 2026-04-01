# 05 - Codebase Guide

Panduan lengkap untuk developer yang baru bergabung ke project ini.
Baca dokumen ini sebelum menyentuh kode apapun.

---

## 1. Sistem Ini Apa?

**Text-to-SQL Chatbot** — sistem yang mengubah pertanyaan bahasa natural (Indonesia/English) menjadi SQL query, mengeksekusinya ke PostgreSQL, dan mengembalikan insight dalam Bahasa Indonesia.

```
User: "Berapa total revenue bulan ini?"
         ↓
    [7 Agent Pipeline]
         ↓
System: "Total revenue bulan ini adalah Rp 252,3 juta dari 1.234 transaksi."
```

---

## 2. Struktur Folder

```
text-to-sql-chatbot/
│
├── config/                         # Konfigurasi
│   └── few_shot_examples.yaml      # Contoh query untuk SQL Generator
│
├── data/                           # Data
│   ├── metadata.json               # Output ekstraksi schema dari PostgreSQL
│   ├── raw/                        # CSV data mentah (8 file)
│   └── schemas/
│       └── metadata.yaml           # Schema + deskripsi (output enrichment)
│
├── docs/                           # Dokumentasi
│   ├── 01_DESIGN_RATIONALE.md      # Keputusan arsitektur
│   ├── 02_IMPLEMENTATION_GUIDE.md  # Panduan implementasi
│   ├── 03_TEST_STRATEGY.md         # Strategi testing
│   ├── 04_QUICK_REFERENCE.md       # Referensi cepat
│   └── 05_CODEBASE_GUIDE.md        # File ini
│
├── logs/                           # Log files (auto-generated)
│
├── sql/                            # SQL migration scripts
│   ├── add_pk_fk_sales.sql         # PK & FK untuk ecommerce_sales
│   └── add_pk_fk_products.sql      # PK & FK untuk ecommerce_products
│
├── src/                            # Source code utama
│   ├── components/                 # 7 Agent pipeline
│   ├── core/                       # Fondasi arsitektur
│   ├── models/                     # Data models
│   ├── pipeline/                   # Schema pipeline
│   ├── ui/                         # Streamlit UI
│   ├── utils/                      # Utilities
│   └── main.py                     # FastAPI entry point
│
├── tests/                          # Test suite
│   ├── unit/                       # Unit tests (mock)
│   ├── integration/                # Integration tests (mock)
│   └── e2e/                        # End-to-end tests (real API & DB)
│
└── tools/                          # Developer utilities
    ├── generate_sample_data.py     # Generate data dummy
    └── setup_databases.py          # Setup/reset database
```

---

## 3. Penjelasan File per File

### `src/core/` — Fondasi Arsitektur

| File | Fungsi |
|------|--------|
| `base_agent.py` | Abstract base class untuk semua agent. Berisi `execute()`, `run()`, logging, dan metrics tracking. **Semua agent wajib inherit class ini.** |
| `llm_base_agent.py` | Extend BaseAgent dengan Anthropic Claude client dan `_call_llm()`. **Hanya agent yang pakai LLM yang inherit class ini.** |
| `config.py` | Centralized configuration. Semua konstanta (model, timeout, allowed tables, DB URLs) ada di sini. |

### `src/models/` — Data Models

| File | Fungsi |
|------|--------|
| `agent_state.py` | **File terpenting.** Shared state yang mengalir dari agent ke agent. Semua input dan output agent disimpan di sini. |
| `retrieved_table.py` | Dataclass untuk merepresentasikan satu tabel hasil retrieval dari ChromaDB. |

### `src/components/` — 7 Agent Pipeline

| File | Agent | Type | Input dari State | Output ke State |
|------|-------|------|-----------------|-----------------|
| `intent_classifier.py` | Agent 1 | LLM | `state.query` | `state.intent`, `state.needs_clarification` |
| `schema_retriever.py` | Agent 2 | Traditional | `state.query` | `state.retrieved_tables`, `state.database` |
| `retrieval_evaluator.py` | Agent 3 | LLM | `state.query`, `state.retrieved_tables` | `state.evaluated_tables` |
| `sql_generator.py` | Agent 4 | LLM | `state.query`, `state.evaluated_tables`, `state.intent` | `state.sql` |
| `sql_validator.py` | Agent 5 | Hybrid | `state.sql`, `state.query` | `state.validated_sql` |
| `query_executor.py` | Agent 6 | Traditional | `state.validated_sql`, `state.database` | `state.query_result`, `state.row_count` |
| `insight_generator.py` | Agent 7 | LLM | `state.query`, `state.validated_sql`, `state.query_result`, `state.row_count` | `state.insights` |

### `src/pipeline/` — Schema Pipeline

> Pipeline ini dijalankan **sekali di awal** (atau saat ada perubahan schema database).
> Bukan bagian dari query pipeline yang berjalan setiap user bertanya.

| File | Fungsi | Urutan |
|------|--------|--------|
| `pg_metadata_extractor.py` | Ekstrak schema dari semua PostgreSQL database → `data/metadata.json` | Step 1 |
| `enrich_metadata.py` | Generate deskripsi schema via Claude API → `data/schemas/metadata.yaml` | Step 2 |
| `index_schemas.py` | Index metadata.yaml ke ChromaDB untuk semantic search | Step 3 |

**Cara menjalankan schema pipeline:**
```bash
python -m src.pipeline.pg_metadata_extractor
python -m src.pipeline.enrich_metadata
python -m src.pipeline.index_schemas
```

### `src/utils/` — Utilities

| File | Fungsi |
|------|--------|
| `logger.py` | `setup_logger()` — fungsi untuk setup logger yang konsisten di semua agent. |
| `exceptions.py` | Custom exceptions per komponen (`AgentExecutionError`, `SQLValidationError`, dll). |

### `src/ui/app.py` — Streamlit UI

Interface web untuk user non-teknis. Terhubung ke FastAPI via HTTP.

### `src/main.py` — FastAPI Entry Point

Orkestrasi pipeline. Menerima request dari user, menjalankan 7 agent secara berurutan, mengembalikan response.

**Endpoint utama:**
```
POST /query  → jalankan full pipeline
GET  /health → cek status semua agent
GET  /databases → list database yang tersedia
```

---

## 4. Alur Data (Pipeline Flow)

```
User Query
    │
    ▼
AgentState(query="berapa total customer?")
    │
    ▼
[1] IntentClassifier.run(state)
    → state.intent = {"category": "aggregation", "sql_strategy": "..."}
    → state.needs_clarification = False
    │
    ▼ (jika needs_clarification → stop, return ke user)
    │
[2] SchemaRetriever.execute(state)
    → state.retrieved_tables = [customers, orders, ...]
    → state.database = "sales_db"
    │
    ▼
[3] RetrievalEvaluator.run(state)
    → state.evaluated_tables = [customers]  ← filtered
    │
    ▼
[4] SQLGenerator.run(state)
    → state.sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"
    │
    ▼
[5] SQLValidator.run(state)
    → state.validated_sql = "SELECT COUNT(*) as total FROM customers LIMIT 100;"
    │
    ▼
[6] QueryExecutor.run(state)
    → state.query_result = [{"total": 100}]
    → state.row_count = 1
    │
    ▼
[7] InsightGenerator.run(state)
    → state.insights = "Terdapat 100 customer yang terdaftar dalam sistem."
    │
    ▼
Response ke User
```

---

## 5. AgentState — Kontrak Data

`src/models/agent_state.py` adalah **single source of truth** untuk semua data yang mengalir antar agent.

```python
@dataclass
class AgentState:
    # ── INPUT ──────────────────────────────────────
    query: str                    # Pertanyaan user (wajib)
    database: str                 # Target database (default: sales_db)

    # ── AGENT OUTPUTS ──────────────────────────────
    intent: dict                  # Hasil IntentClassifier
    retrieved_tables: list        # Hasil SchemaRetriever
    evaluated_tables: list        # Hasil RetrievalEvaluator
    sql: str                      # Hasil SQLGenerator
    validated_sql: str            # Hasil SQLValidator
    query_result: List[Dict]      # Hasil QueryExecutor
    row_count: int                # Hasil QueryExecutor
    insights: str                 # Hasil InsightGenerator

    # ── TRACKING ───────────────────────────────────
    errors: List[str]             # Error yang terjadi
    timing: Dict[str, float]      # Waktu eksekusi per agent (ms)
    current_stage: str            # Agent yang sedang berjalan
    needs_clarification: bool     # Query perlu klarifikasi?
    clarification_reason: str     # Alasan perlu klarifikasi
```

---

## 6. Cara Menjalankan

### Step 1 — Install PostgreSQL (Linux/WSL)

```bash
# Ubuntu/Debian/WSL
sudo apt update
sudo apt install postgresql postgresql-contrib -y

# Start PostgreSQL
sudo service postgresql start

# Cek status
sudo service postgresql status
```

### Step 2 — Buat Databases

```bash
# Masuk ke PostgreSQL
sudo -u postgres psql

# Di dalam psql, jalankan:
CREATE DATABASE ecommerce_sales;
CREATE DATABASE ecommerce_products;
CREATE DATABASE ecommerce_analytics;

# Beri akses ke user Anda (ganti your_username & your_password)
CREATE USER your_username WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE ecommerce_sales TO your_username;
GRANT ALL PRIVILEGES ON DATABASE ecommerce_products TO your_username;
GRANT ALL PRIVILEGES ON DATABASE ecommerce_analytics TO your_username;

# Keluar
\q
```

### Step 3 — Clone & Setup Project

```bash
# Clone repository
git clone <repo-url>
cd text-to-sql-chatbot

# Buat virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Copy .env
cp .env.example .env
```

### Step 4 — Konfigurasi .env

Buka file `.env` dan isi semua variabel:

```
ANTHROPIC_API_KEY=sk-ant-...      # Dari console.anthropic.com
OPENAI_API_KEY=sk-...             # Dari platform.openai.com

SALES_DB_URL=postgresql://your_username:your_password@localhost:5432/ecommerce_sales
PRODUCTS_DB_URL=postgresql://your_username:your_password@localhost:5432/ecommerce_products
ANALYTICS_DB_URL=postgresql://your_username:your_password@localhost:5432/ecommerce_analytics
```

### Step 5 — Load Data ke PostgreSQL

```bash
# Load semua CSV ke database (sekali saja)
python tools/load_data.py
```

Script ini akan:
- Load 8 CSV dari `data/raw/` ke PostgreSQL
- Tambah PK & FK constraints otomatis
- Print progress & error jika ada

### Step 6 — Setup Schema Pipeline

```bash
# Ekstrak schema dari PostgreSQL
python -m src.pipeline.pg_metadata_extractor

# Generate deskripsi via Claude API
python -m src.pipeline.enrich_metadata

# Index ke ChromaDB
python -m src.pipeline.index_schemas
```

### Step 7 — Jalankan Aplikasi

Aplikasi ini membutuhkan **2 terminal yang berjalan bersamaan**.

**Terminal 1 — Jalankan FastAPI (backend):**
```bash
# Pastikan virtual environment aktif
source venv/bin/activate

# Jalankan API server
uvicorn src.main:app --reload --port 8000
```
Biarkan terminal ini tetap berjalan. Jangan ditutup.

**Terminal 2 — Jalankan Streamlit (frontend):**
```bash
# Buka terminal baru, masuk ke folder project
cd text-to-sql-chatbot

# Aktifkan virtual environment
source venv/bin/activate

# Jalankan UI
streamlit run src/ui/app.py
```

Setelah keduanya berjalan, buka browser:
```
FastAPI docs : http://localhost:8000/docs
Streamlit UI : http://localhost:8501
```

### Jalankan UI
```bash
streamlit run src/ui/app.py
```

### Jalankan Tests
```bash
# Unit tests (tidak butuh API/DB)
pytest tests/unit/ -v

# Integration tests (tidak butuh API/DB)
pytest tests/integration/ -v

# E2E tests (butuh API key & DB running)
pytest tests/e2e/ -v -s
```

---

## 7. Panduan untuk Developer Baru

### ✅ Yang BOLEH dilakukan
```
→ Ubah logika di dalam execute() setiap agent
→ Ubah prompt LLM di dalam agent
→ Tambah method baru di dalam agent
→ Tambah field BARU di AgentState (jangan hapus yang lama)
→ Tambah test baru
```

### ❌ Yang TIDAK BOLEH diubah
```
→ Nama field yang sudah ada di AgentState
→ Tipe data field yang sudah ada di AgentState
→ Signature method execute(self, state) → AgentState
→ Nama class setiap agent
→ Import path yang sudah dipakai di main.py
```

### 📋 Checklist sebelum push code
```
□ Sudah baca docstring di agent yang diubah
□ Input dari state tidak berubah
□ Output ke state tidak berubah
□ Unit test masih passing
□ Tidak ada hardcoded credentials
```

---

## 8. Database

| Database | Nama di PostgreSQL | Tabel |
|----------|-------------------|-------|
| `sales_db` | `ecommerce_sales` | customers, orders, payments |
| `products_db` | `ecommerce_products` | products, sellers, order_items |
| `analytics_db` | `ecommerce_analytics` | customer_segments, daily_metrics |

**Relasi antar tabel:**
```
ecommerce_sales:
customers.customer_id ←── orders.customer_id
orders.order_id       ←── payments.order_id

ecommerce_products:
products.product_id ←── order_items.product_id
sellers.seller_id   ←── order_items.seller_id
```

---

## 9. Environment Variables (.env)

```
ANTHROPIC_API_KEY=    # Untuk semua LLM agents
OPENAI_API_KEY=       # Untuk ChromaDB embeddings

SALES_DB_URL=postgresql://user@localhost:5432/ecommerce_sales
PRODUCTS_DB_URL=postgresql://user@localhost:5432/ecommerce_products
ANALYTICS_DB_URL=postgresql://user@localhost:5432/ecommerce_analytics
```