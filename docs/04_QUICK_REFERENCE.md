# Quick Reference: Text-to-SQL Chatbot

**Project:** Multi-Database Text-to-SQL Analytics Chatbot  
**Document:** Quick Reference & Developer Cheat Sheet  
**Version:** 1.0  
**Date:** February 2026  

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Common Commands](#2-common-commands)
3. [Project Structure Cheat Sheet](#3-project-structure-cheat-sheet)
4. [Configuration Quick Reference](#4-configuration-quick-reference)
5. [API Endpoints](#5-api-endpoints)
6. [Component API Reference](#6-component-api-reference)
7. [Database Queries](#7-database-queries)
8. [Testing Commands](#8-testing-commands)
9. [Troubleshooting Guide](#9-troubleshooting-guide)
10. [Code Snippets](#10-code-snippets)
11. [Performance Optimization Tips](#11-performance-optimization-tips)
12. [Deployment Checklist](#12-deployment-checklist)

---

## 1. Quick Start

### 1.1 First Time Setup (30 minutes)
```bash
# 1. Clone/Create project
git clone <repo> && cd text-to-sql-chatbot
# OR
mkdir text-to-sql-chatbot && cd text-to-sql-chatbot

# 2. Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment variables
cp .env.example .env
nano .env  # Add API keys

# 5. Start PostgreSQL
brew services start postgresql@14  # Mac
# sudo systemctl start postgresql  # Linux

# 6. Create databases
psql postgres
CREATE DATABASE ecommerce_sales;
CREATE DATABASE ecommerce_products;
CREATE DATABASE ecommerce_analytics;
\q

# 7. Load data
python scripts/setup_databases.py

# 8. Index schemas
python scripts/index_schemas.py

# 9. Run tests
python scripts/run_tests.py

# 10. Start services
# Terminal 1: API
uvicorn src.main:app --reload --port 8000

# Terminal 2: UI
streamlit run src/ui/app.py
```

**Access:**
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs
- UI: http://localhost:8501

---

### 1.2 Daily Development Workflow
```bash
# Activate environment
source venv/bin/activate

# Start API (with hot reload)
uvicorn src.main:app --reload

# In another terminal: Start UI
streamlit run src/ui/app.py

# Run tests after changes
python scripts/run_tests.py

# Check logs
tail -f logs/app.log
```

---

## 2. Common Commands

### 2.1 Environment Management
```bash
# Activate venv
source venv/bin/activate          # Mac/Linux
venv\Scripts\activate              # Windows

# Deactivate
deactivate

# Install new package
pip install <package>
pip freeze > requirements.txt      # Update requirements

# Clean install
rm -rf venv
python3.11 -m venv venv
pip install -r requirements.txt
```

---

### 2.2 Database Commands
```bash
# Connect to database
psql ecommerce_sales

# List tables
\dt

# Describe table
\d customers

# Check row count
SELECT COUNT(*) FROM customers;

# Exit psql
\q

# Backup database
pg_dump ecommerce_sales > backup.sql

# Restore database
psql ecommerce_sales < backup.sql

# Reset database
psql postgres
DROP DATABASE ecommerce_sales;
CREATE DATABASE ecommerce_sales;
\q
python scripts/setup_databases.py
```

---

### 2.3 API Commands
```bash
# Start API (development)
uvicorn src.main:app --reload --port 8000

# Start API (production)
uvicorn src.main:app --host 0.0.0.0 --port 8000 --workers 4

# Test API health
curl http://localhost:8000/health

# Test query endpoint
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many customers?"}'

# Check API logs
tail -f logs/app.log
```

---

### 2.4 Testing Commands
```bash
# Run all tests
python scripts/run_tests.py

# Run unit tests only
pytest tests/test_components.py -v

# Run integration tests
pytest tests/test_integration.py -v

# Run specific test
pytest tests/test_components.py::test_intent_classifier -v

# Run with coverage
pytest --cov=src tests/

# Generate coverage report
pytest --cov=src --cov-report=html tests/
open htmlcov/index.html
```

---

### 2.5 ChromaDB Commands
```bash
# Re-index schemas (if schemas change)
python scripts/index_schemas.py

# Check ChromaDB collection
python -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
collection = client.get_collection('table_schemas')
print(f'Total tables indexed: {collection.count()}')
"

# Clear and re-index
rm -rf chroma_db/
python scripts/index_schemas.py

# View indexed documents
python -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
collection = client.get_collection('table_schemas')
results = collection.get(limit=5)
print(results['ids'])
"
```

---

## 3. Project Structure Cheat Sheet
```
text-to-sql-chatbot/
│
├── src/                          # Source code
│   ├── main.py                   # FastAPI app (START HERE for API)
│   ├── config.py                 # Config loader
│   │
│   ├── components/               # 7 Pipeline components
│   │   ├── intent_classifier.py      # Component 1
│   │   ├── schema_retriever.py       # Component 2
│   │   ├── retrieval_evaluator.py    # Component 3
│   │   ├── sql_generator.py          # Component 4
│   │   ├── sql_validator.py          # Component 5
│   │   ├── query_executor.py         # Component 6
│   │   └── insight_generator.py      # Component 7
│   │
│   ├── models/                   # Pydantic models
│   │   ├── query_models.py
│   │   └── response_models.py
│   │
│   └── ui/                       # Streamlit UI
│       └── app.py                # START HERE for UI
│
├── scripts/                      # Setup scripts
│   ├── setup_databases.py        # Load data into DBs
│   ├── index_schemas.py          # Create ChromaDB index
│   └── run_tests.py              # Test runner
│
├── tests/                        # Test files
│   ├── test_components.py        # Unit tests
│   ├── test_integration.py       # E2E tests
│   └── test_queries.json         # 20 test queries
│
├── config/                       # Configuration
│   ├── config.yaml               # Main config
│   ├── few_shot_examples.yaml   # SQL examples
│   └── databases.yaml            # DB connections
│
├── data/                         # Data files
│   ├── raw/                      # Olist CSVs
│   └── schemas/                  # Schema descriptions
│
├── docs/                         # Documentation
│   ├── 01_DESIGN_RATIONALE.md
│   ├── 02_IMPLEMENTATION_GUIDE.md
│   ├── 03_TEST_STRATEGY.md
│   └── 04_QUICK_REFERENCE.md     # This file
│
├── .env                          # Environment variables (DON'T COMMIT!)
├── requirements.txt              # Python dependencies
└── README.md                     # Project overview
```

---

## 4. Configuration Quick Reference

### 4.1 Environment Variables (.env)
```bash
# Required
ANTHROPIC_API_KEY=sk-ant-xxxxx
OPENAI_API_KEY=sk-xxxxx

# Database URLs
SALES_DB_URL=postgresql://localhost:5432/ecommerce_sales
PRODUCTS_DB_URL=postgresql://localhost:5432/ecommerce_products
ANALYTICS_DB_URL=postgresql://localhost:5432/ecommerce_analytics

# Optional
DEBUG=true
LOG_LEVEL=INFO
```

---

### 4.2 Main Config (config/config.yaml)
```yaml
llm:
  model: claude-sonnet-4-20250514
  temperature: 0              # Deterministic
  max_tokens: 1000

embeddings:
  model: text-embedding-3-small

vector_db:
  persist_directory: ./chroma_db
  collection_name: table_schemas

validation:
  sql_timeout_seconds: 30
  max_result_rows: 10000
  max_retry_attempts: 2

api:
  host: 0.0.0.0
  port: 8000

logging:
  level: INFO
  format: json
```

---

### 4.3 Few-Shot Examples (config/few_shot_examples.yaml)
```yaml
examples:
  - question: "Show all customers"
    sql: "SELECT * FROM customers LIMIT 100;"
  
  - question: "Total sales this month"
    sql: |
      SELECT SUM(payment_value) as total_sales
      FROM payments p
      JOIN orders o ON p.order_id = o.order_id
      WHERE EXTRACT(MONTH FROM o.order_purchase_timestamp) = EXTRACT(MONTH FROM CURRENT_DATE)
        AND EXTRACT(YEAR FROM o.order_purchase_timestamp) = EXTRACT(YEAR FROM CURRENT_DATE);
  
  # Add more examples here
```

---

## 5. API Endpoints

### 5.1 POST /query

**Main endpoint for processing queries**
```bash
# cURL example
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "Top 5 customers by revenue"
  }'
```

**Request:**
```json
{
  "question": "string"
}
```

**Response (Success):**
```json
{
  "insights": "Natural language answer...",
  "sql": "SELECT ...",
  "data": [
    {"customer_id": 123, "revenue": 50000},
    ...
  ],
  "metadata": {
    "intent": "multi_table_join",
    "tables_used": ["customers", "orders", "payments"],
    "execution_time_ms": 4200,
    "row_count": 5,
    "component_times": {
      "intent_classification": 500,
      "schema_retrieval": 300,
      "sql_generation": 1200,
      "execution": 900
    }
  }
}
```

**Response (Ambiguous):**
```json
{
  "insights": "I need more information...",
  "sql": null,
  "data": null,
  "metadata": {
    "intent": "ambiguous",
    "reason": "Insufficient information"
  }
}
```

**Response (Error):**
```json
{
  "insights": "Query execution failed: ...",
  "sql": "SELECT ...",
  "data": null,
  "metadata": {
    "execution_error": "Error message"
  }
}
```

---

### 5.2 GET /health

**Health check endpoint**
```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0"
}
```

---

### 5.3 Python Client Example
```python
import requests

def query_chatbot(question: str):
    response = requests.post(
        'http://localhost:8000/query',
        json={'question': question},
        timeout=30
    )
    
    if response.status_code == 200:
        result = response.json()
        print(f"Insights: {result['insights']}")
        print(f"SQL: {result['sql']}")
        return result
    else:
        print(f"Error: {response.status_code}")
        return None

# Usage
query_chatbot("How many customers are there?")
```

---

## 6. Component API Reference

### 6.1 Intent Classifier
```python
from src.components.intent_classifier import IntentClassifier

classifier = IntentClassifier()

# Classify query
result = classifier.classify("Top 5 customers by revenue")

# Returns: IntentResult
# - intent: QueryIntent enum
# - confidence: float (0-1)
# - reason: Optional[str]

print(result.intent)        # QueryIntent.MULTI_TABLE_JOIN
print(result.confidence)    # 0.95
```

---

### 6.2 Schema Retriever
```python
from src.components.schema_retriever import SchemaRetriever

retriever = SchemaRetriever()

# Retrieve relevant tables
result = retriever.retrieve("Top customers by spending", top_k=5)

# Returns: SchemaRetrievalResult
# - retrieved_tables: List[RetrievedTable]
# - retrieval_time_ms: float

for table in result.retrieved_tables:
    print(f"{table.db_name}.{table.table_name}")
    print(f"  Columns: {table.columns}")
    print(f"  Similarity: {table.similarity_score}")
```

---

### 6.3 SQL Generator
```python
from src.components.sql_generator import SQLGenerator

generator = SQLGenerator()

# Generate SQL
result = generator.generate(
    user_query="How many customers?",
    relevant_tables=retrieved_tables
)

# Returns: SQLGenerationResult
# - sql: str
# - generation_time_ms: float

print(result.sql)
```

---

### 6.4 SQL Validator
```python
from src.components.sql_validator import SQLValidator

validator = SQLValidator()

# Validate and auto-fix
result = validator.validate_and_fix(
    sql="SELECT * FROM customers",
    user_query="Show customers"
)

# Returns: ValidationResult
# - valid: bool
# - sql: str (potentially fixed)
# - errors: List[str]
# - warnings: List[str]

if result.valid:
    print("SQL is valid!")
else:
    print(f"Errors: {result.errors}")
```

---

### 6.5 Query Executor
```python
from src.components.query_executor import QueryExecutor

executor = QueryExecutor()

# Execute SQL
result = executor.execute(
    sql="SELECT COUNT(*) FROM customers",
    db_name="sales_db"
)

# Returns: ExecutionResult
# - success: bool
# - data: Optional[List[Dict]]
# - row_count: int
# - execution_time_ms: float
# - error: Optional[str]

if result.success:
    print(f"Data: {result.data}")
    print(f"Rows: {result.row_count}")
else:
    print(f"Error: {result.error}")
```

---

### 6.6 Insight Generator
```python
from src.components.insight_generator import InsightGenerator

generator = InsightGenerator()

# Generate insights
result = generator.generate(
    user_query="How many customers?",
    sql="SELECT COUNT(*) FROM customers",
    results=[{"count": 10000}],
    row_count=1
)

# Returns: InsightResult
# - insights: str (natural language + formatted data)
# - insight_generation_time_ms: float

print(result.insights)
```

---

## 7. Database Queries

### 7.1 Quick Database Checks
```sql
-- Check data loaded correctly
SELECT 
    'customers' as table_name, 
    COUNT(*) as row_count 
FROM customers
UNION ALL
SELECT 'orders', COUNT(*) FROM orders
UNION ALL
SELECT 'payments', COUNT(*) FROM payments;

-- Verify relationships
SELECT 
    COUNT(DISTINCT c.customer_id) as total_customers,
    COUNT(DISTINCT o.order_id) as total_orders,
    COUNT(DISTINCT p.payment_id) as total_payments
FROM customers c
LEFT JOIN orders o ON c.customer_id = o.customer_id
LEFT JOIN payments p ON o.order_id = p.order_id;

-- Check date ranges
SELECT 
    MIN(order_purchase_timestamp) as earliest_order,
    MAX(order_purchase_timestamp) as latest_order,
    COUNT(*) as total_orders
FROM orders;

-- Test cross-database reference
-- (Run in sales_db)
SELECT o.order_id
FROM orders o
LIMIT 5;

-- (Run in products_db with above order_ids)
SELECT oi.order_id, p.product_name
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
WHERE oi.order_id IN (/* order_ids from above */);
```

---

### 7.2 Sample Analytical Queries
```sql
-- Top 5 customers by revenue
SELECT 
    c.customer_unique_id,
    SUM(p.payment_value) as total_revenue
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN payments p ON o.order_id = p.order_id
GROUP BY c.customer_unique_id
ORDER BY total_revenue DESC
LIMIT 5;

-- Monthly revenue trend
SELECT 
    DATE_TRUNC('month', o.order_purchase_timestamp) as month,
    SUM(p.payment_value) as revenue,
    COUNT(DISTINCT o.order_id) as order_count
FROM orders o
JOIN payments p ON o.order_id = p.order_id
GROUP BY month
ORDER BY month;

-- Customer segments distribution
SELECT 
    segment,
    COUNT(*) as customer_count,
    AVG(lifetime_value) as avg_ltv
FROM customer_segments
GROUP BY segment
ORDER BY avg_ltv DESC;
```

---

## 8. Testing Commands

### 8.1 Run Tests
```bash
# All tests
python scripts/run_tests.py

# Only passed tests
python scripts/run_tests.py | grep "✅"

# Only failed tests
python scripts/run_tests.py | grep "❌"

# Save results
python scripts/run_tests.py > test_results.txt

# Unit tests with pytest
pytest tests/test_components.py -v

# Integration tests
pytest tests/test_integration.py -v

# Specific component test
pytest tests/test_components.py::test_intent_classifier -v

# With coverage
pytest --cov=src tests/ --cov-report=term-missing
```

---

### 8.2 Quick Manual Tests
```bash
# Test API is running
curl http://localhost:8000/health

# Test simple query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many customers?"}'

# Test ambiguous query
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Show me the data"}'

# Test SQL injection
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "'\'''; DROP TABLE customers; --"}'
```

---

### 8.3 Python Test Script
```python
# quick_test.py
import requests

def test_query(question):
    print(f"\nTesting: {question}")
    response = requests.post(
        'http://localhost:8000/query',
        json={'question': question}
    )
    result = response.json()
    
    print(f"Intent: {result['metadata'].get('intent')}")
    print(f"SQL: {result.get('sql', 'None')[:100]}")
    print(f"Rows: {result['metadata'].get('row_count')}")
    print(f"Time: {result['metadata'].get('execution_time_ms')}ms")

# Run tests
test_query("How many customers?")
test_query("Top 5 customers by revenue")
test_query("Show me the data")  # Should be ambiguous
```

---

## 9. Troubleshooting Guide

### 9.1 Common Issues

#### **Issue: Import Error**
```bash
Error: ModuleNotFoundError: No module named 'anthropic'
```

**Solution:**
```bash
# Activate venv first
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

---

#### **Issue: Database Connection Refused**
```bash
Error: could not connect to server: Connection refused
```

**Solution:**
```bash
# Check PostgreSQL is running
brew services list | grep postgres  # Mac
sudo systemctl status postgresql    # Linux

# Start PostgreSQL
brew services start postgresql@14   # Mac
sudo systemctl start postgresql     # Linux

# Verify connection
psql postgres
\l  # List databases
\q
```

---

#### **Issue: API Key Not Found**
```bash
Error: ANTHROPIC_API_KEY not found in .env
```

**Solution:**
```bash
# Check .env file exists
ls -la .env

# Add API keys
echo "ANTHROPIC_API_KEY=your-key-here" >> .env
echo "OPENAI_API_KEY=your-key-here" >> .env

# Verify
cat .env | grep API_KEY
```

---

#### **Issue: ChromaDB Collection Not Found**
```bash
Error: Collection 'table_schemas' does not exist
```

**Solution:**
```bash
# Re-index schemas
python scripts/index_schemas.py

# Verify
python -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
try:
    collection = client.get_collection('table_schemas')
    print(f'✅ Collection found: {collection.count()} tables')
except:
    print('❌ Collection not found')
"
```

---

#### **Issue: Port Already in Use**
```bash
Error: [Errno 48] Address already in use
```

**Solution:**
```bash
# Find process using port 8000
lsof -i :8000

# Kill process
kill -9 <PID>

# Or use different port
uvicorn src.main:app --port 8001
```

---

#### **Issue: SQL Validation Always Fails**
```bash
Error: SECURITY: Only SELECT queries allowed
```

**Solution:**
```bash
# Check SQL contains dangerous keywords
echo "SELECT * FROM customers" | grep -E "DROP|DELETE|UPDATE|INSERT"

# If clean, check validator logic
python -c "
from src.components.sql_validator import SQLValidator
validator = SQLValidator()
result = validator.validate_and_fix('SELECT * FROM customers LIMIT 10')
print(f'Valid: {result.valid}')
print(f'Errors: {result.errors}')
"
```

---

#### **Issue: Slow Queries**
```bash
# Query takes >30 seconds
```

**Solution:**
```bash
# Check query complexity
psql ecommerce_sales
EXPLAIN ANALYZE SELECT ...;

# Add indexes if needed
CREATE INDEX idx_customer_id ON orders(customer_id);
CREATE INDEX idx_order_date ON orders(order_purchase_timestamp);

# Or increase timeout in config.yaml
validation:
  sql_timeout_seconds: 60  # Increase to 60s
```

---

#### **Issue: UI Shows "Connection Error"**
```bash
Error: ConnectionError: Failed to connect to API
```

**Solution:**
```bash
# Check API is running
curl http://localhost:8000/health

# If not running, start API
uvicorn src.main:app --reload

# Check UI config
# In src/ui/app.py, verify:
API_URL = "http://localhost:8000/query"  # Not 8001 or other port
```

---

### 9.2 Debug Mode

**Enable detailed logging:**
```python
# In src/main.py or any component
import logging

logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.debug("Debug message here")
```

**Check logs:**
```bash
# Real-time log monitoring
tail -f logs/app.log

# Filter for errors only
tail -f logs/app.log | grep ERROR

# Last 100 lines
tail -n 100 logs/app.log
```

---

### 9.3 Reset Everything

**Nuclear option when things are broken:**
```bash
# 1. Stop all services
# Ctrl+C in API and UI terminals

# 2. Remove virtual environment
rm -rf venv/

# 3. Remove ChromaDB
rm -rf chroma_db/

# 4. Remove logs
rm -rf logs/*.log

# 5. Drop and recreate databases
psql postgres
DROP DATABASE ecommerce_sales;
DROP DATABASE ecommerce_products;
DROP DATABASE ecommerce_analytics;
CREATE DATABASE ecommerce_sales;
CREATE DATABASE ecommerce_products;
CREATE DATABASE ecommerce_analytics;
\q

# 6. Fresh install
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 7. Setup from scratch
python scripts/setup_databases.py
python scripts/index_schemas.py

# 8. Test
python scripts/run_tests.py
```

---

## 10. Code Snippets

### 10.1 Add New Few-Shot Example
```yaml
# In config/few_shot_examples.yaml

examples:
  # ... existing examples ...
  
  # Add new example
  - question: "Your new question here"
    sql: |
      SELECT ...
      FROM ...
      WHERE ...;
```

**Then restart API:**
```bash
# Ctrl+C to stop
uvicorn src.main:app --reload
```

---

### 10.2 Add New Test Query
```json
// In tests/test_queries.json

{
  "queries": [
    // ... existing queries ...
    
    // Add new query
    {
      "id": "Q023",
      "question": "Your test question",
      "expected_sql": "SELECT ...",
      "intent": "aggregation",
      "tables": ["table1", "table2"],
      "database": "sales_db",
      "difficulty": "medium",
      "expected_accuracy": 0.85
    }
  ]
}
```

---

### 10.3 Add New Business Metric
```yaml
# Create config/business_metrics.yaml

metrics:
  revenue:
    definition: "Total money received (post-tax)"
    calculation: "SUM(payments.payment_value)"
    tables: [payments, orders]
    
  active_customers:
    definition: "Customers with purchase in last 30 days"
    calculation: "COUNT(DISTINCT customer_id) WHERE order_date >= CURRENT_DATE - 30"
    tables: [customers, orders]
  
  # Add your metric here
  your_metric:
    definition: "Description"
    calculation: "SQL calculation"
    tables: [table1, table2]
```

---

### 10.4 Custom Intent Category
```python
# In src/models/query_models.py

class QueryIntent(str, Enum):
    SIMPLE_SELECT = "simple_select"
    # ... existing categories ...
    
    # Add new category
    YOUR_NEW_INTENT = "your_new_intent"
```

**Update classifier prompt:**
```python
# In src/components/intent_classifier.py

def _build_prompt(self, user_query: str) -> str:
    return f"""...
    
    7. your_new_intent - Description
       Examples: "example 1", "example 2"
    
    ..."""
```

---

### 10.5 Add New Database
```yaml
# In config/databases.yaml (create if not exists)

databases:
  - name: sales_db
    url: ${SALES_DB_URL}
  
  - name: products_db
    url: ${PRODUCTS_DB_URL}
  
  # Add new database
  - name: your_new_db
    url: ${YOUR_NEW_DB_URL}
```

**Add to .env:**
```bash
YOUR_NEW_DB_URL=postgresql://localhost:5432/your_new_db
```

**Update executor:**
```python
# In src/components/query_executor.py
# No code change needed - automatically loads from config
```

---

## 11. Performance Optimization Tips

### 11.1 Reduce Latency

**1. Cache schema embeddings (already done)**
```python
# Schema embeddings only generated once during indexing
# Retrieval uses cached embeddings
```

**2. Use faster LLM for simple queries**
```python
# In src/components/intent_classifier.py
# For POC, use same model for consistency
# For production, consider:
if intent == QueryIntent.SIMPLE_SELECT:
    model = "claude-haiku-4-20250101"  # Faster, cheaper
else:
    model = "claude-sonnet-4-20250514"  # Better accuracy
```

**3. Skip evaluator for simple queries**
```python
# In src/main.py
if intent_result.intent == QueryIntent.SIMPLE_SELECT:
    # Skip retrieval evaluator (saves 0.8s)
    essential_tables = retrieval_result.retrieved_tables[:2]
else:
    eval_result = retrieval_evaluator.evaluate(...)
    essential_tables = filter_tables(eval_result)
```

**4. Add database indexes**
```sql
-- In PostgreSQL
CREATE INDEX idx_customer_id ON orders(customer_id);
CREATE INDEX idx_order_id ON payments(order_id);
CREATE INDEX idx_order_date ON orders(order_purchase_timestamp);
CREATE INDEX idx_product_id ON order_items(product_id);
```

---

### 11.2 Reduce Cost

**1. Minimize LLM calls**
```python
# Use retrieval evaluator only when needed
if len(retrieved_tables) <= 3:
    # Skip evaluator if already few tables
    pass
```

**2. Use smaller context**
```python
# In SQL generation, only include essential schema info
# Remove verbose descriptions for POC
```

**3. Implement caching (Phase 2)**
```python
# Cache identical queries
import redis
r = redis.Redis(host='localhost', port=6379)

def cached_query(question):
    cached = r.get(question)
    if cached:
        return json.loads(cached)
    
    result = process_query(question)
    r.setex(question, 300, json.dumps(result))  # 5 min TTL
    return result
```

---

### 11.3 Improve Accuracy

**1. Add more few-shot examples**
```yaml
# Target patterns that often fail
# Check failure_analysis.md for patterns
```

**2. Improve schema descriptions**
```yaml
# Add more business terminology
# Include common query patterns
# Mention relationships explicitly
```

**3. Tune retrieval top-K**
```python
# Experiment with different values
result = schema_retriever.retrieve(query, top_k=7)  # Try 7 instead of 5
```

**4. Adjust validation strictness**
```python
# In sql_validator.py
# Be less strict on warnings
# More strict on security
```

---

## 12. Deployment Checklist

### 12.1 Pre-Deployment Checks
```bash
# 1. Run all tests
python scripts/run_tests.py
# Expected: ≥75% pass rate

# 2. Check security
# All injection attempts blocked
grep "SECURITY" logs/app.log | wc -l
# Expected: 0 (no successful injections)

# 3. Check performance
# Average response time <5s
grep "execution_time_ms" logs/app.log | awk '{sum+=$NF; count++} END {print sum/count}'

# 4. Check API health
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# 5. Verify database connections
psql ecommerce_sales -c "SELECT COUNT(*) FROM customers;"
psql ecommerce_products -c "SELECT COUNT(*) FROM products;"
psql ecommerce_analytics -c "SELECT COUNT(*) FROM customer_segments;"

# 6. Check ChromaDB indexed
python -c "
import chromadb
client = chromadb.PersistentClient(path='./chroma_db')
collection = client.get_collection('table_schemas')
assert collection.count() == 9, 'Expected 9 tables'
print('✅ ChromaDB OK')
"

# 7. Test UI
# Open http://localhost:8501
# Run 3-5 test queries manually

# 8. Review logs for errors
grep ERROR logs/app.log
# Expected: 0 unexpected errors
```

---

### 12.2 Demo Preparation

**Create demo script:**
```markdown
# Demo Script

## 1. Introduction (2 min)
- Problem: Data team bottleneck
- Solution: Text-to-SQL chatbot
- Architecture: Hybrid (agentic + traditional)

## 2. Simple Query Demo (1 min)
Question: "How many customers are there?"
Expected: Shows count, fast response (<3s)

## 3. Aggregation Demo (1 min)
Question: "Total revenue this month"
Expected: Shows SQL with JOIN, correct calculation

## 4. Complex Query Demo (2 min)
Question: "Top 5 customers by total spending"
Expected: Multi-table JOIN, ranked results

## 5. Error Handling Demo (1 min)
Question: "Show me the data"
Expected: Asks for clarification (ambiguous)

## 6. Security Demo (1 min)
Question: "'; DROP TABLE customers; --"
Expected: Blocked with security message

## 7. Architecture Explanation (3 min)
- Show diagram (7 components)
- Explain why hybrid approach
- Mention RAG for 100+ tables

## 8. Results (2 min)
- Test accuracy: 18/20 = 90%
- Response time: ~4s average
- Cost: $0.025 per query

## 9. Q&A (5 min)
- Be ready for: "Why not GPT-4?", "How does it scale?", etc.
```

---

### 12.3 Known Issues to Mention

**Be transparent about limitations:**
```markdown
## Known Limitations (POC)

1. ⚠️ Complex date queries: 70% accuracy (acceptable for POC)
   - "Month-over-month growth" sometimes fails
   - Will improve with more examples in MVP

2. ⚠️ Cross-database queries: Architecture ready, not fully tested
   - Single-DB queries work well (90% accuracy)
   - Multi-DB deferred to MVP

3. ⚠️ Advanced SQL: Not supported in POC
   - Window functions, CTEs, recursive queries
   - Deferred to production (Phase 3)

4. ⚠️ Performance: 3-5s average (acceptable for ad-hoc queries)
   - Not suitable for real-time dashboards
   - Can optimize with caching in MVP
```

---

### 12.4 Post-Demo Action Items
```markdown
## If Demo is Successful

### Immediate (Week 2):
- [ ] Gather stakeholder feedback
- [ ] Prioritize improvements based on feedback
- [ ] Document additional use cases

### Short-term (Month 1 - MVP):
- [ ] Multi-database support (full implementation)
- [ ] User authentication (SSO)
- [ ] Query history & caching
- [ ] Improved UI (React)
- [ ] More few-shot examples (target 90% accuracy)

### Medium-term (Month 3 - Production):
- [ ] Advanced RBAC
- [ ] Row-level security
- [ ] Monitoring & alerting
- [ ] Performance optimization
- [ ] Advanced SQL features
```

---

**END OF QUICK REFERENCE**

---

## Quick Command Summary
```bash
# Setup
python scripts/setup_databases.py
python scripts/index_schemas.py

# Start
uvicorn src.main:app --reload
streamlit run src/ui/app.py

# Test
python scripts/run_tests.py
pytest tests/ -v

# Debug
tail -f logs/app.log
psql ecommerce_sales

# Reset
rm -rf chroma_db/ && python scripts/index_schemas.py
```

**For detailed information, see:**
- Design: `docs/01_DESIGN_RATIONALE.md`
- Implementation: `docs/02_IMPLEMENTATION_GUIDE.md`
- Testing: `docs/03_TEST_STRATEGY.md`