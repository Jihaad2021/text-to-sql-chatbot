# Text-to-SQL Analytics Chatbot

AI-powered chatbot that converts natural language questions (Indonesian or English) into SQL queries, executes them against PostgreSQL, and returns human-readable insights. Built for Telkomsel financial payment analytics.

[![Python](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![CI](https://github.com/Jihaad2021/text-to-sql-chatbot/actions/workflows/ci.yml/badge.svg)](https://github.com/Jihaad2021/text-to-sql-chatbot/actions)
[![License](https://img.shields.io/badge/license-Proprietary-red.svg)](LICENSE)

---

## Features

- **Natural language queries** — Ask in Indonesian or English
- **8-agent pipeline** — Parallel intent + planning, hybrid retrieval, SQL generation, validation, execution, insights
- **Multi-step analytical queries** — Complex questions are automatically decomposed into sequential sub-queries
- **Conversational memory** — Context from previous questions is carried into each new query
- **Hybrid retrieval** — ChromaDB (semantic) + BM25 (keyword) + NetworkX graph, fused via Reciprocal Rank Fusion
- **SQL self-correction** — If execution fails, the error is fed back to SQLGenerator for up to 2 automatic retries
- **In-memory query cache** — Identical queries served instantly (10-minute TTL, configurable)
- **Multi-layer SQL validation** — Syntax, security, table whitelist, and optional LLM logic check
- **Production ready** — Rate limiting, connection pooling, structured JSON logging, startup validation

---

## Architecture

### Pipeline Flow

```
User Query
    │
    ├─────────────────────────────────────────(parallel)──────────────┐
    │                                                                  │
    ▼                                                                  ▼
┌────────────────────────┐                              ┌─────────────────────────┐
│ 1. IntentClassifier    │                              │ 2. QueryPlanner         │
│                        │                              │                         │
│  Classifies query into │                              │  Decomposes complex     │
│  aggregation/filter/   │                              │  questions into ordered │
│  join/trend/ambiguous  │                              │  sub-queries (steps)    │
│                        │                              │                         │
│  ⚡ Early stop if       │                              │  Simple → 1 step        │
│  ambiguous             │                              │  Complex → N steps      │
└──────────┬─────────────┘                              └─────────────┬───────────┘
           │                                                          │
           └──────────────────────── merge ──────────────────────────┘
                                        │
                          (per step if multi-step)
                                        │
                                        ▼
                        ┌───────────────────────────────┐
                        │ 3. SchemaRetriever             │
                        │                               │
                        │  Finds relevant tables using  │
                        │  three fused retrievers:      │
                        │  • ChromaDB — semantic search │
                        │  • BM25     — keyword match   │
                        │  • Graph    — FK traversal    │
                        │  Combined via RRF (k=60)      │
                        └────────────────┬──────────────┘
                                         │
                                         ▼
                        ┌───────────────────────────────┐
                        │ 4. RetrievalEvaluator          │
                        │                               │
                        │  LLM filters candidates into  │
                        │  ESSENTIAL / OPTIONAL /       │
                        │  EXCLUDED for this query      │
                        └────────────────┬──────────────┘
                                         │
                             ┌───────────┴──────────────┐
                             │  retry loop (max 2×)     │
                             ▼                          │
                        ┌───────────────────────────────┐  QueryExecutionError
                        │ 5. SQLGenerator               │◄─── (error + failed SQL
                        │                               │      fed back as context)
                        │  Converts NL → SQL using:     │
                        │  table schemas, column types, │
                        │  FK relationships, few-shot   │
                        │  examples, conversation       │
                        │  history, and any prior error │
                        └────────────────┬──────────────┘
                                         │
                                         ▼
                        ┌───────────────────────────────┐
                        │ 6. SQLValidator               │
                        │                               │
                        │  3-layer deterministic check: │
                        │  1. Syntax  (sqlparse)        │
                        │  2. Security (blocklist)      │
                        │  3. Whitelist (allowed tables)│
                        │  + optional LLM logic layer   │
                        └────────────────┬──────────────┘
                                         │
                                         ▼
                        ┌───────────────────────────────┐
                        │ 7. QueryExecutor              │
                        │                               │
                        │  Executes SQL via SQLAlchemy  │
                        │  connection pool with timeout │
                        │  and row-count cap            │
                        └────────────────┬──────────────┘
                                         │
                        (all step results collected)
                                         │
                                         ▼
                        ┌───────────────────────────────┐
                        │ 8. InsightGenerator           │
                        │                               │
                        │  Generates 2–4 sentence       │
                        │  Indonesian summary with      │
                        │  formatted numbers and        │
                        │  business context             │
                        └───────────────────────────────┘
                                         │
                                         ▼
                            SQL + Data Table + Insights
```

### Agent Classification

| Type | Agents |
|------|--------|
| LLM | IntentClassifier, QueryPlanner, RetrievalEvaluator, SQLGenerator, InsightGenerator |
| Traditional | SchemaRetriever, QueryExecutor |
| Hybrid (rules + optional LLM) | SQLValidator |

### Key Design Decisions

**Parallel start** — IntentClassifier and QueryPlanner run concurrently via `ThreadPoolExecutor` because both only need `state.query`. Results are merged before the SQL sub-pipeline begins.

**Multi-step execution** — When QueryPlanner returns more than one step, `_run_multi_step()` runs the full SQL sub-pipeline (agents 3–7) once per step and collects `StepResult` objects. InsightGenerator receives all results and synthesises a unified answer.

**Error self-correction** — If QueryExecutor raises `QueryExecutionError` (e.g. wrong column name), the error message and failed SQL are written back to `AgentState.sql_error` and the loop retries from SQLGenerator, up to `_SQL_RETRY_LIMIT = 2` times.

**Query caching** — The original query (before any sub-query substitution) is used as the cache key. Results are stored for `CACHE_TTL_SECONDS` (default 600s). Cache is keyed by `(query.strip().lower(), database)`.

**Shared state** — All agents read from and write to a single `AgentState` dataclass. No agent creates a new state. The pipeline owns sequencing; agents own logic.

---

## Domain: Telkomsel Financial Payment Analytics

The system is configured for `financial_db`, a PostgreSQL database containing Telkomsel digital payment transaction data.

### Tables (10)

| Table | Description |
|-------|-------------|
| `daily_master` | Daily transaction aggregates — volume, value, unique users per product/channel |
| `financial_internal` | Internal financial records — revenue, fees, settlements |
| `product_summary` | Per-product performance summary |
| `channel_payment` | Payment channel breakdown (GoPay, OVO, Dana, LinkAja, etc.) |
| `product_price_list` | Product pricing and fee structure |
| `anomalies` | Detected anomalies in transaction patterns |
| `daily_unique_users` | Daily active user counts |
| `daily_user_partner` | User activity by partner/merchant |
| `hourly_pattern_daily` | Intraday hourly transaction patterns |
| `daily_product_channel` | Cross-tabulation of products and payment channels |

### Example Questions

```
"Berapa total transaksi bulan April 2026?"
"Top 5 payment channel berdasarkan volume transaksi?"
"Bandingkan revenue GoPay vs OVO selama Q1 2026"
"Tunjukkan anomali yang terjadi minggu ini"
"Berapa rata-rata daily active users per produk?"
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL 14+
- OpenAI API key (required for ChromaDB embeddings)
- At least one LLM provider key

### 1. Clone and install

```bash
git clone https://github.com/Jihaad2021/text-to-sql-chatbot.git
cd text-to-sql-chatbot
python3.11 -m venv venv
source venv/bin/activate        # Mac/Linux
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# Edit .env — set OPENAI_API_KEY and FINANCIAL_DB_URL at minimum
```

Minimum required variables:

```env
OPENAI_API_KEY=sk-...
FINANCIAL_DB_URL=postgresql://user:pass@localhost:5432/financial_db
DEFAULT_LLM=openai
DEFAULT_MODEL=gpt-4o
```

### 3. Load financial data

```bash
# Create schema and load data into PostgreSQL
psql $FINANCIAL_DB_URL -f sql/setup_all.sql
python scripts/load_financial_data.py
```

### 4. Index schemas for retrieval

```bash
# Extract metadata from PostgreSQL
python scripts/pg_metadata_extractor.py

# Enrich descriptions with LLM (optional but recommended)
python scripts/enrich_metadata.py

# Build ChromaDB, BM25, and graph indexes
python scripts/index_schemas.py
python scripts/build_bm25_index.py
python scripts/build_graph.py
```

### 5. Run

```bash
# Terminal 1: API
uvicorn src.main:app --port 8000

# Terminal 2: UI
streamlit run src/ui/app.py
```

- Web UI: http://localhost:8501
- API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Docker Compose

```bash
cp .env.example .env
# Edit .env

docker-compose up -d
```

---

## Configuration

All configuration is in `src/core/config.py` and driven by `.env`. See `.env.example` for the full list.

Key variables:

```env
# LLM
OPENAI_API_KEY=sk-...          # required for embeddings
ANTHROPIC_API_KEY=sk-ant-...   # optional alternative
DEFAULT_LLM=openai
DEFAULT_MODEL=gpt-4o

# Database
FINANCIAL_DB_URL=postgresql://user:pass@localhost:5432/financial_db

# SQL Validator (optional LLM logic layer — cheap model)
ENABLE_AI_VALIDATION=true
SQL_VALIDATOR_MODEL=gpt-4o-mini

# Cache
CACHE_TTL_SECONDS=600          # 0 to disable

# API
ALLOWED_ORIGINS=http://localhost:8501
RATE_LIMIT_PER_MINUTE=30
LOG_FORMAT=text                # text | json

# Query execution
QUERY_TIMEOUT_SECONDS=30
QUERY_MAX_ROWS=10000

# Connection pool
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=10
DB_POOL_RECYCLE=1800
```

---

## API

### POST /query

Run the full 8-agent pipeline.

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Berapa total transaksi bulan April 2026?",
    "database": "financial_db",
    "conversation_history": []
  }'
```

Response:

```json
{
  "question": "Berapa total transaksi bulan April 2026?",
  "sql": "SELECT SUM(total_trx) FROM daily_master WHERE periode = '2026-04'",
  "data": [{"sum": 4823910}],
  "insights": "Total transaksi pada April 2026 mencapai 4,82 juta transaksi...",
  "row_count": 1,
  "execution_time_ms": 10234.5,
  "is_multi_step": false,
  "conversation_history": [...],
  "metadata": {
    "request_id": "...",
    "intent": {"category": "aggregation"},
    "tables_used": 1,
    "timing": {...}
  }
}
```

Pass `conversation_history` from a previous response back in the next request to maintain context across questions.

### GET /health

Deep health check — verifies real connectivity to PostgreSQL and ChromaDB.

```bash
curl http://localhost:8000/health
```

### GET /databases

Lists available databases and total indexed tables.

---

## Project Structure

```
text-to-sql-chatbot/
│
├── src/
│   ├── main.py                        # FastAPI app, lifespan, routes
│   │
│   ├── components/                    # 8 pipeline agents
│   │   ├── intent_classifier.py       # Agent 1: intent + ambiguity detection
│   │   ├── query_planner.py           # Agent 2: multi-step query decomposition
│   │   ├── schema_retriever.py        # Agent 3: hybrid retrieval (ChromaDB+BM25+Graph)
│   │   ├── retrieval_evaluator.py     # Agent 4: filter essential tables
│   │   ├── sql_generator.py           # Agent 5: NL → SQL with error context
│   │   ├── sql_validator.py           # Agent 6: 3-layer + optional LLM validation
│   │   ├── query_executor.py          # Agent 7: safe SQL execution
│   │   └── insight_generator.py       # Agent 8: natural language insights
│   │
│   ├── core/
│   │   ├── pipeline.py                # TextToSQLPipeline orchestrator
│   │   ├── query_cache.py             # In-memory TTL cache
│   │   ├── base_agent.py              # BaseAgent (metrics, error wrapping)
│   │   ├── llm_base_agent.py          # LLMBaseAgent (multi-provider LLM calls)
│   │   ├── config.py                  # All constants and env var reads
│   │   └── startup.py                 # Fail-fast environment validation
│   │
│   ├── models/
│   │   ├── agent_state.py             # Shared pipeline state (AgentState)
│   │   └── retrieved_table.py         # Table schema model
│   │
│   ├── pipeline/                      # One-time setup scripts
│   │   ├── index_schemas.py           # Index table schemas to ChromaDB
│   │   ├── build_bm25_index.py        # Build BM25 keyword index
│   │   ├── build_graph.py             # Build FK relationship graph
│   │   ├── pg_metadata_extractor.py   # Extract metadata from PostgreSQL
│   │   └── enrich_metadata.py         # Enrich descriptions with LLM
│   │
│   ├── utils/
│   │   ├── exceptions.py              # Domain-specific exceptions
│   │   └── logger.py                  # Structured logging (text/JSON)
│   │
│   └── ui/
│       └── app.py                     # Streamlit web interface
│
├── tests/
│   ├── conftest.py                    # Shared fixtures (financial_db domain)
│   ├── unit/                          # Per-component unit tests
│   ├── integration/                   # Pipeline integration tests
│   └── e2e/                           # End-to-end tests (requires real API + DB)
│
├── scripts/
│   └── load_financial_data.py         # One-time DB data load
│
├── sql/
│   └── setup_all.sql                  # PostgreSQL schema DDL
│
├── data/
│   ├── bm25_index.pkl                 # Generated BM25 index
│   ├── schema_graph.json              # Generated FK graph
│   └── schemas/metadata.yaml          # Enriched table descriptions
│
├── config/
│   └── few_shot_examples.yaml         # SQL examples for prompting
│
├── .github/workflows/ci.yml           # CI: test + lint on every push
├── Dockerfile                         # Multi-stage API image
├── Dockerfile.ui                      # Multi-stage Streamlit UI image
├── docker-compose.yml                 # API + UI with health checks
├── CLAUDE.md                          # Coding standards for AI-assisted dev
├── .env.example                       # Environment template
└── requirements.txt                   # Python dependencies
```

---

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | OpenAI GPT-4o (default), Anthropic Claude, Groq, Google Gemini |
| Embeddings | OpenAI text-embedding-3-small |
| Vector DB | ChromaDB |
| Keyword Search | BM25 (rank_bm25) |
| Graph Search | NetworkX |
| Retrieval Fusion | RRF (Reciprocal Rank Fusion, k=60) |
| Database | PostgreSQL 14+ |
| API | FastAPI |
| UI | Streamlit |
| ORM | SQLAlchemy 2.0 |
| SQL Parsing | sqlparse |
| Rate Limiting | slowapi |
| Linting | ruff |
| Language | Python 3.11+ |

---

## Performance

| Metric | Value |
|--------|-------|
| Cold query (no cache) | ~8–12 seconds |
| Cache hit | ~0 ms |
| Cache TTL | 10 minutes (configurable) |
| Rate limit | 30 req/min per IP |
| SQL self-correction retries | up to 2 |
| Max rows returned | 10,000 |
| Query timeout | 30 seconds |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# By layer
pytest tests/unit/        # Unit — no external services required
pytest tests/integration/ # Integration — all mocked
pytest tests/e2e/         # E2E — requires real API key + PostgreSQL + ChromaDB

# With coverage
pytest tests/unit/ tests/integration/ --cov=src --cov-report=term-missing

# Linting
ruff check src/ tests/
```

| Layer | Tests | Requirements |
|-------|-------|--------------|
| Unit | ~110 | None (all mocked) |
| Integration | ~12 | None (all mocked) |
| E2E | ~10 | Real API + PostgreSQL + ChromaDB |
| **Total** | **~132** | |

Every push to `main` runs unit + integration tests and linting automatically via GitHub Actions.

---

## Deployment

### Production checklist

- [ ] Set `LOG_FORMAT=json` for structured logging
- [ ] Set `ALLOWED_ORIGINS` to your actual frontend URL
- [ ] Set `ENABLE_AI_VALIDATION=true`
- [ ] Configure `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_RECYCLE`
- [ ] Set `CACHE_TTL_SECONDS` to match your query refresh needs
- [ ] Monitor `/health` endpoint

### Manual

```bash
uvicorn src.main:app --host 0.0.0.0 --port 8000
streamlit run src/ui/app.py --server.port 8501
```

---

## Troubleshooting

**Startup fails with "Missing required"**
The app validates all required env vars before initializing any agent. Check `OPENAI_API_KEY`, `FINANCIAL_DB_URL`, `DEFAULT_LLM`, and `DEFAULT_MODEL` are set in `.env`.

**ChromaDB collection empty**
Run the indexing pipeline:
```bash
python scripts/index_schemas.py
```

**SQL execution keeps failing**
The pipeline retries automatically up to 2 times with error context. If it still fails, check:
1. `/health` to verify DB connectivity
2. Table names — only tables in `ALLOWED_TABLES` can be queried
3. Query timeout — increase `QUERY_TIMEOUT_SECONDS` for complex aggregations

**UI cannot reach API**
```bash
curl http://localhost:8000/health
# Check API_URL in .env matches where the API is running
```

---

## License

Proprietary — Internal Project
© 2026 All Rights Reserved
