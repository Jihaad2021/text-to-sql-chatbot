# 🤖 Text-to-SQL Analytics Chatbot

AI-powered chatbot for multi-database analytics using natural language. Convert questions in Indonesian or English into SQL queries with intelligent validation and beautiful insights.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![CI](https://github.com/Jihaad2021/text-to-sql-chatbot/actions/workflows/ci.yml/badge.svg)](https://github.com/Jihaad2021/text-to-sql-chatbot/actions)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

---

## ✨ Features

- 🗣️ **Natural Language Queries** — Ask in Indonesian or English
- 🤖 **Multi-LLM Support** — Anthropic Claude, OpenAI GPT, Groq, Google Gemini; configurable per-agent
- 🔍 **Hybrid Retrieval** — ChromaDB (semantic) + BM25 (keyword) + Graph (relationship) with RRF fusion
- 🛡️ **Security First** — SQL injection prevention, read-only enforcement, CORS from env var
- ✅ **Smart Validation** — 4-layer hybrid validation (syntax, security, table whitelist, logic)
- 💡 **Natural Language Insights** — Conversational Indonesian explanations with formatted numbers
- 🎯 **Intent Detection** — Catches ambiguous queries before processing
- 📊 **Multi-Database** — Works across 3 separate PostgreSQL databases
- 🚀 **Production Ready** — Rate limiting, connection pooling, structured JSON logging, startup validation
- 🐳 **Docker Compose** — One command to run API + UI

---

## 🎥 Demo

**Example Queries:**
```
User: "Berapa jumlah customer?"
→ SQL: SELECT COUNT(*) FROM customers;
→ Result: "Anda memiliki total 100 customer dalam database."

User: "Top 5 customers by spending"
→ SQL: SELECT c.customer_name, SUM(p.payment_value) as total...
→ Result: Beautiful table + insights in Indonesian
```

---

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Tech Stack](#tech-stack)
- [Configuration](#configuration)
- [Capabilities](#capabilities)
- [Performance](#performance)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- At least one LLM API key (Anthropic, OpenAI, Groq, or Gemini)
- OpenAI API key (for ChromaDB embeddings)

### Option A — Docker Compose (Recommended)

```bash
# 1. Clone and configure
git clone https://github.com/Jihaad2021/text-to-sql-chatbot.git
cd text-to-sql-chatbot
cp .env.example .env
# Edit .env with your API keys and DB URLs

# 2. Run everything
docker-compose up -d

# Access:
# Web UI  → http://localhost:8501
# API     → http://localhost:8000
# API Docs→ http://localhost:8000/docs
```

### Option B — Local Development

```bash
# 1. Clone and install
git clone https://github.com/Jihaad2021/text-to-sql-chatbot.git
cd text-to-sql-chatbot
python3.11 -m venv venv
source venv/bin/activate       # Mac/Linux
# venv\Scripts\activate        # Windows
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — set API keys and DB connection URLs

# 3. Setup PostgreSQL
psql postgres << EOF
CREATE DATABASE ecommerce_sales;
CREATE DATABASE ecommerce_products;
CREATE DATABASE ecommerce_analytics;
EOF

# 4. Index schemas for semantic search
python -m src.pipeline.index_schemas
python -m src.pipeline.build_bm25_index
python -m src.pipeline.build_graph

# 5. Run
# Terminal 1: API
uvicorn src.main:app --reload --port 8000

# Terminal 2: UI
streamlit run src/ui/app.py
```

**Access:**
- 🌐 **Web UI:** http://localhost:8501
- 📡 **API Docs:** http://localhost:8000/docs
- ❤️ **Health Check:** http://localhost:8000/health

---

## 🏗️ Architecture

### Pipeline Flow

```
Query
  │
  ▼
┌─────────────────────────────────────────┐
│ 1. IntentClassifier                     │
│    Detect: aggregation (conf: 0.95)     │
│    Early stop if ambiguous              │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 2. SchemaRetriever                      │
│    Hybrid: ChromaDB + BM25 + Graph      │
│    Fused with Reciprocal Rank Fusion    │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 3. RetrievalEvaluator                   │
│    Filter: essential / optional tables  │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 4. SQLGenerator                         │
│    NL → SQL with few-shot examples      │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 5. SQLValidator                         │
│    Syntax + Security + Whitelist + Logic│
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 6. QueryExecutor                        │
│    Safe execution with timeout & limit  │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 7. InsightGenerator                     │
│    Natural language answer in Indonesian│
└────────────────────┬────────────────────┘
                     │
                     ▼
             Formatted Response
          (SQL + Data + Insights)
```

All 7 agents are orchestrated by `TextToSQLPipeline` (`src/core/pipeline.py`), which is separate from the API layer.

### Design Philosophy

**Hybrid Approach:** Combines AI (intelligence) with Traditional (reliability)

- **LLM Agents (4/7):** IntentClassifier, RetrievalEvaluator, SQLGenerator, InsightGenerator
- **Traditional (2/7):** SchemaRetriever, QueryExecutor
- **Hybrid (1/7):** SQLValidator (rule-based + optional AI auto-fix)

### Multi-LLM Support

Each agent can use a different LLM provider, configured via `.env`:

```env
# Default for all agents
DEFAULT_LLM=openai
DEFAULT_MODEL=gpt-4o

# Per-agent override (optional)
INTENT_CLASSIFIER_LLM=groq
INTENT_CLASSIFIER_MODEL=llama3-8b-8192
SQL_GENERATOR_LLM=anthropic
SQL_GENERATOR_MODEL=claude-sonnet-4-20250514
```

Supported providers: `anthropic`, `openai`, `groq`, `gemini`

---

## 📁 Project Structure

```
text-to-sql-chatbot/
│
├── src/
│   ├── main.py                        # FastAPI app + lifespan + routes
│   │
│   ├── components/                    # 7 pipeline agents
│   │   ├── intent_classifier.py       # Agent 1: intent + ambiguity detection
│   │   ├── schema_retriever.py        # Agent 2: hybrid retrieval (ChromaDB+BM25+Graph)
│   │   ├── retrieval_evaluator.py     # Agent 3: filter essential/optional tables
│   │   ├── sql_generator.py           # Agent 4: NL → SQL
│   │   ├── sql_validator.py           # Agent 5: 4-layer validation
│   │   ├── query_executor.py          # Agent 6: safe SQL execution
│   │   └── insight_generator.py       # Agent 7: natural language insights
│   │
│   ├── core/
│   │   ├── pipeline.py                # TextToSQLPipeline orchestrator
│   │   ├── base_agent.py              # BaseAgent (metrics, error wrapping)
│   │   ├── llm_base_agent.py          # LLMBaseAgent (multi-provider LLM calls)
│   │   ├── config.py                  # Centralized config (all env vars)
│   │   └── startup.py                 # Environment validation at startup
│   │
│   ├── models/
│   │   ├── agent_state.py             # Shared pipeline state (AgentState)
│   │   └── retrieved_table.py         # Table schema model
│   │
│   ├── pipeline/                      # Indexing scripts
│   │   ├── index_schemas.py           # Index table schemas to ChromaDB
│   │   ├── build_bm25_index.py        # Build BM25 keyword index
│   │   ├── build_graph.py             # Build schema relationship graph
│   │   ├── pg_metadata_extractor.py   # Extract metadata from PostgreSQL
│   │   └── enrich_metadata.py         # Enrich schema descriptions with LLM
│   │
│   ├── utils/
│   │   ├── exceptions.py              # Domain-specific exceptions
│   │   └── logger.py                  # Structured logging (text/JSON)
│   │
│   └── ui/
│       └── app.py                     # Streamlit web interface
│
├── tests/
│   ├── unit/                          # Unit tests per component (130 tests)
│   ├── integration/                   # Pipeline integration tests (9 tests)
│   └── e2e/                           # End-to-end tests with real API+DB (25 tests)
│
├── config/
│   └── few_shot_examples.yaml         # SQL examples for prompting
│
├── data/
│   ├── bm25_index.pkl                 # BM25 index (generated)
│   └── schema_graph.json              # Schema graph (generated)
│
├── chroma_db/                         # ChromaDB vector storage (generated)
│
├── .github/workflows/ci.yml           # CI: test + lint on every push
├── Dockerfile                         # Multi-stage build for API
├── Dockerfile.ui                      # Multi-stage build for Streamlit UI
├── docker-compose.yml                 # API + UI with health checks
├── ruff.toml                          # Linter config (Python 3.11+)
├── CLAUDE.md                          # Coding standards for AI-assisted dev
├── .env.example                       # Environment template
└── requirements.txt                   # Python dependencies
```

---

## 🛠️ Tech Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **LLM** | Anthropic / OpenAI / Groq / Gemini | SQL generation, intent, insights |
| **Embeddings** | OpenAI text-embedding-3-small | Semantic search for schemas |
| **Vector DB** | ChromaDB | Store & search table embeddings |
| **Keyword Search** | BM25 (rank_bm25) | Keyword-based table retrieval |
| **Graph Search** | NetworkX | Relationship-aware retrieval |
| **Retrieval Fusion** | RRF (Reciprocal Rank Fusion) | Combine ChromaDB + BM25 + Graph |
| **Database** | PostgreSQL 14+ | Data storage (3 databases) |
| **API** | FastAPI | RESTful backend |
| **UI** | Streamlit | Web interface |
| **ORM** | SQLAlchemy 2.0 | Connection pooling + query execution |
| **SQL Parser** | sqlparse | Syntax validation |
| **Rate Limiting** | slowapi | Per-IP rate limiting on /query |
| **Linting** | ruff | Fast Python linter |
| **Language** | Python 3.11+ | All application code |

---

## ⚙️ Configuration

All configuration lives in `src/core/config.py` and is driven by `.env`. Copy `.env.example` to get started:

```bash
cp .env.example .env
```

Key variables:

```env
# LLM — at least one required
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...        # also required for ChromaDB embeddings
GROQ_API_KEY=gsk_...
GEMINI_API_KEY=AIza...

# LLM selection
DEFAULT_LLM=openai            # anthropic | openai | groq | gemini
DEFAULT_MODEL=gpt-4o

# Databases — at least one required
SALES_DB_URL=postgresql://user:pass@localhost:5432/ecommerce_sales
PRODUCTS_DB_URL=postgresql://user:pass@localhost:5432/ecommerce_products
ANALYTICS_DB_URL=postgresql://user:pass@localhost:5432/ecommerce_analytics

# API
ALLOWED_ORIGINS=http://localhost:8501
RATE_LIMIT_PER_MINUTE=30
LOG_FORMAT=text               # text | json

# Retrieval
TOP_K_RETRIEVAL=5
RRF_K=60

# Query execution
QUERY_TIMEOUT_SECONDS=30
QUERY_MAX_ROWS=10000
```

See `.env.example` for the full list.

---

## ✅ Capabilities

### What the System Can Do

| Query Type | Support | Example |
|------------|---------|---------|
| Simple SELECT | ✅ | "Show all customers" |
| COUNT/SUM/AVG | ✅ | "How many orders?" |
| WHERE Filters | ✅ | "Customers from Jakarta" |
| JOINs (2-3 tables) | ✅ | "Top 5 customers by spending" |
| Date Filtering | ✅ | "Orders this month" |
| GROUP BY | ✅ | "Revenue by payment method" |
| Indonesian Language | ✅ | "Berapa jumlah customer?" |
| English Language | ✅ | "How many customers?" |
| Ambiguity Detection | ✅ | Catches "Show me data" |
| SQL Injection Prevention | ✅ | Blocks all malicious queries |

### What the System Cannot Do

| Feature | Status | Reason |
|---------|--------|--------|
| Window Functions | ⚠️ Limited | May fail validator without AI auto-fix |
| INSERT/UPDATE/DELETE | ❌ Blocked | Read-only by design |
| Recursive CTEs | ⚠️ Limited | Too complex for current prompt |
| Cross-DB JOINs | ⚠️ Limited | PostgreSQL limitation |
| Subqueries | ⚠️ Partial | Inconsistent accuracy |

---

## 📊 Performance

| Metric | Value |
|--------|-------|
| Accuracy | ~90% (18/20 test queries) |
| Average Response Time | 4–6 seconds |
| — Intent Classification | ~1.5s |
| — SQL Generation | ~2.0s |
| — Query Execution | ~0.1s |
| — Insight Generation | ~1.5s |
| Security | 100% SQL injection prevention |
| Cost per Query | ~$0.024 (GPT-4o) |

---

## 🧪 Testing

```bash
# All 155 tests
pytest tests/ -v

# By layer
pytest tests/unit/        # Unit tests (130) — no API/DB required
pytest tests/integration/ # Integration tests (9) — mocked
pytest tests/e2e/         # E2E tests (25) — requires real API + DB

# Linting
ruff check src/ tests/
```

### Test Coverage

| Layer | Tests | Requirements |
|-------|-------|--------------|
| Unit | 130 | None (all mocked) |
| Integration | 9 | None (all mocked) |
| E2E | 25 | Real API key + PostgreSQL + ChromaDB |
| **Total** | **155** | |

### CI/CD

Every push to `main` runs automatically via GitHub Actions (`.github/workflows/ci.yml`):
- **test** job: runs unit + integration tests with dummy env vars
- **lint** job: runs `ruff check src/ tests/`

---

## 🚀 Deployment

### Docker Compose (Recommended)

```bash
cp .env.example .env
# Edit .env

docker-compose up -d

# Check health
curl http://localhost:8000/health
```

### Manual

```bash
# API
uvicorn src.main:app --host 0.0.0.0 --port 8000

# UI
streamlit run src/ui/app.py --server.port 8501
```

### Production Checklist

- [ ] Set `LOG_FORMAT=json` for structured logging
- [ ] Set `ALLOWED_ORIGINS` to your actual frontend domain
- [ ] Set `RATE_LIMIT_PER_MINUTE` appropriate for your traffic
- [ ] Configure `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`
- [ ] Set `ENABLE_AI_VALIDATION=true` for AI-assisted SQL auto-fix
- [ ] Monitor `/health` endpoint

---

## 🐛 Troubleshooting

**API startup fails**
```bash
# Check required env vars — the app validates on startup and fails fast
# Look for "Missing required" in the startup log
```

**PostgreSQL not running**
```bash
brew services start postgresql@14   # Mac
sudo systemctl start postgresql     # Linux
psql postgres -c "SELECT 1;"        # Verify
```

**ChromaDB collection not found**
```bash
python -m src.pipeline.index_schemas
```

**API connection error in UI**
```bash
curl http://localhost:8000/health
# Check API_URL in .env matches where API is running
```

---

## 📄 License

Proprietary — Technical Test Project
© 2026 All Rights Reserved

