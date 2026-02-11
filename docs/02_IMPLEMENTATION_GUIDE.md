# Implementation Guide: Text-to-SQL Chatbot

**Project:** Multi-Database Text-to-SQL Analytics Chatbot  
**Document:** Implementation Guide  
**Version:** 1.0  
**Date:** February 2026  

---

## Table of Contents

1. [Overview](#1-overview)
2. [Project Structure](#2-project-structure)
3. [Development Environment Setup](#3-development-environment-setup)
4. [Database Setup](#4-database-setup)
5. [Component Implementation](#5-component-implementation)
6. [API Endpoints](#6-api-endpoints)
7. [Configuration Management](#7-configuration-management)
8. [Code Standards & Conventions](#8-code-standards--conventions)
9. [Testing Strategy](#9-testing-strategy)
10. [Deployment Guide](#10-deployment-guide)
11. [Troubleshooting](#11-troubleshooting)
12. [Development Workflow](#12-development-workflow)

---

## 1. Overview

### 1.1 Purpose

This document provides **step-by-step implementation instructions** for building the Text-to-SQL chatbot POC in 1 week.

**Target Audience:**
- Developers implementing the system
- Future maintainers
- Claude AI (when uploaded to new chat for code continuation)

### 1.2 Implementation Priorities

**Week 1 POC Focus:**
```
Day 1-2: Environment setup + Database setup + Schema indexing
Day 3-4: Core pipeline (Components 1-7)
Day 5: API + UI (Streamlit)
Day 6: Testing + Bug fixes
Day 7: Demo prep + Documentation
```

**Out of Scope for Week 1:**
- Authentication (single user demo)
- Caching (direct execution)
- Production deployment (local only)
- Advanced error handling (basic is OK)

### 1.3 Success Criteria

**POC is ready when:**
- ✅ All 7 components work end-to-end
- ✅ 15/20 test queries return correct results (75%+)
- ✅ Streamlit UI runs locally
- ✅ Can demo to stakeholders

---

## 2. Project Structure

### 2.1 Directory Layout
```
text-to-sql-chatbot/
│
├── src/                          # Source code
│   ├── __init__.py
│   ├── main.py                   # FastAPI application
│   ├── config.py                 # Configuration loader
│   │
│   ├── components/               # Pipeline components
│   │   ├── __init__.py
│   │   ├── intent_classifier.py
│   │   ├── schema_retriever.py
│   │   ├── retrieval_evaluator.py
│   │   ├── sql_generator.py
│   │   ├── sql_validator.py
│   │   ├── query_executor.py
│   │   └── insight_generator.py
│   │
│   ├── models/                   # Data models (Pydantic)
│   │   ├── __init__.py
│   │   ├── query_models.py
│   │   └── response_models.py
│   │
│   ├── utils/                    # Utility functions
│   │   ├── __init__.py
│   │   ├── logger.py
│   │   └── helpers.py
│   │
│   └── ui/                       # Streamlit UI
│       └── app.py
│
├── data/                         # Data files
│   ├── raw/                      # Olist CSV files
│   ├── processed/                # Cleaned data
│   └── schemas/                  # Schema metadata
│
├── scripts/                      # Setup & utility scripts
│   ├── setup_databases.py        # Create & populate DBs
│   ├── index_schemas.py          # ChromaDB indexing
│   └── run_tests.py              # Test runner
│
├── tests/                        # Test files
│   ├── __init__.py
│   ├── test_components.py
│   ├── test_integration.py
│   └── test_queries.json         # 20 test queries
│
├── config/                       # Configuration files
│   ├── config.yaml               # Main config
│   ├── databases.yaml            # DB connections
│   ├── few_shot_examples.yaml   # SQL examples
│   └── business_metrics.yaml    # Metric definitions
│
├── logs/                         # Log files
│   └── app.log
│
├── chroma_db/                    # ChromaDB storage
│
├── docs/                         # Documentation
│   ├── 01_DESIGN_RATIONALE.md
│   ├── 02_IMPLEMENTATION_GUIDE.md
│   ├── 03_TEST_STRATEGY.md
│   └── 04_QUICK_REFERENCE.md
│
├── requirements.txt              # Python dependencies
├── .env.example                  # Environment variables template
├── .gitignore
├── README.md
└── docker-compose.yml            # Optional: for databases
```

### 2.2 File Responsibilities

**Core Files:**
```
main.py                 → FastAPI app, orchestrates pipeline
config.py               → Load configs from YAML
intent_classifier.py    → Component 1 implementation
schema_retriever.py     → Component 2 implementation
...                     → (all 7 components)
```

**Configuration:**
```
config.yaml             → Main settings (LLM, ports, etc)
databases.yaml          → DB connection strings
few_shot_examples.yaml → SQL examples for Component 4
```

**Scripts:**
```
setup_databases.py      → Load Olist data into 3 PostgreSQL DBs
index_schemas.py        → Create ChromaDB embeddings
run_tests.py            → Execute 20 test queries
```

---

## 3. Development Environment Setup

### 3.1 Prerequisites

**Required:**
- Python 3.11+
- PostgreSQL 14+
- Git
- 8GB RAM minimum
- 10GB disk space

**API Keys Needed:**
```
ANTHROPIC_API_KEY       → For Claude Sonnet 4
OPENAI_API_KEY          → For embeddings (text-embedding-3-small)
```

### 3.2 Step-by-Step Setup

#### Step 1: Clone Repository (or Create)
```bash
# If starting from scratch
mkdir text-to-sql-chatbot
cd text-to-sql-chatbot
git init

# Create directory structure
mkdir -p src/{components,models,utils,ui}
mkdir -p data/{raw,processed,schemas}
mkdir -p scripts tests config logs docs
```

#### Step 2: Create Virtual Environment
```bash
# Create venv
python3.11 -m venv venv

# Activate
# On Mac/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate
```

#### Step 3: Install Dependencies

**Create `requirements.txt`:**
```txt
# Core
fastapi==0.109.0
uvicorn[standard]==0.27.0
python-dotenv==1.0.0
pydantic==2.5.0
pyyaml==6.0.1

# LLM & Embeddings
anthropic==0.18.1
openai==1.12.0

# Vector Database
chromadb==0.4.22

# Database
sqlalchemy==2.0.25
psycopg2-binary==2.9.9
pandas==2.2.0

# SQL Parsing
sqlparse==0.4.4

# UI
streamlit==1.31.0

# Utils
python-json-logger==2.0.7
```

**Install:**
```bash
pip install -r requirements.txt
```

#### Step 4: Environment Variables

**Create `.env` file:**
```bash
# API Keys
ANTHROPIC_API_KEY=your_claude_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Database URLs
SALES_DB_URL=postgresql://localhost:5432/ecommerce_sales
PRODUCTS_DB_URL=postgresql://localhost:5432/ecommerce_products
ANALYTICS_DB_URL=postgresql://localhost:5432/ecommerce_analytics

# Application
DEBUG=true
LOG_LEVEL=INFO
```

**Security:**
```bash
# Add to .gitignore
echo ".env" >> .gitignore
echo "chroma_db/" >> .gitignore
echo "logs/*.log" >> .gitignore
echo "__pycache__/" >> .gitignore
```

#### Step 5: Verify Installation
```bash
# Test imports
python -c "import anthropic; import chromadb; import sqlalchemy; print('All imports OK')"
```

---

## 4. Database Setup

### 4.1 PostgreSQL Installation

**Mac (Homebrew):**
```bash
brew install postgresql@14
brew services start postgresql@14
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql-14
sudo systemctl start postgresql
```

**Windows:**
- Download installer from postgresql.org
- Install with default settings

### 4.2 Create Databases
```bash
# Access PostgreSQL
psql postgres

# Create databases
CREATE DATABASE ecommerce_sales;
CREATE DATABASE ecommerce_products;
CREATE DATABASE ecommerce_analytics;

# Create user (optional, for production)
CREATE USER app_user WITH PASSWORD 'your_password';
GRANT CONNECT ON DATABASE ecommerce_sales TO app_user;
GRANT CONNECT ON DATABASE ecommerce_products TO app_user;
GRANT CONNECT ON DATABASE ecommerce_analytics TO app_user;

# Grant SELECT only (read-only)
\c ecommerce_sales
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_user;

\c ecommerce_products
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_user;

\c ecommerce_analytics
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_user;

\q
```

### 4.3 Download Olist Dataset
```bash
# Create data directory
mkdir -p data/raw

# Download from Kaggle
# https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce

# Expected files:
# - olist_customers_dataset.csv
# - olist_orders_dataset.csv
# - olist_order_items_dataset.csv
# - olist_order_payments_dataset.csv
# - olist_products_dataset.csv
# - olist_sellers_dataset.csv
# - olist_order_reviews_dataset.csv
# - olist_geolocation_dataset.csv
# - product_category_name_translation.csv

# Place all CSVs in data/raw/
```

### 4.4 Load Data into Databases

**Create `scripts/setup_databases.py`:**
```python
import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()

def setup_sales_db():
    """Load customers, orders, payments into sales_db"""
    engine = create_engine(os.getenv('SALES_DB_URL'))
    
    # Load customers
    customers = pd.read_csv('data/raw/olist_customers_dataset.csv')
    customers.to_sql('customers', engine, if_exists='replace', index=False)
    print(f"✓ Loaded {len(customers)} customers")
    
    # Load orders
    orders = pd.read_csv('data/raw/olist_orders_dataset.csv')
    orders.to_sql('orders', engine, if_exists='replace', index=False)
    print(f"✓ Loaded {len(orders)} orders")
    
    # Load payments
    payments = pd.read_csv('data/raw/olist_order_payments_dataset.csv')
    payments.to_sql('payments', engine, if_exists='replace', index=False)
    print(f"✓ Loaded {len(payments)} payments")

def setup_products_db():
    """Load products, sellers, order_items into products_db"""
    engine = create_engine(os.getenv('PRODUCTS_DB_URL'))
    
    # Load products
    products = pd.read_csv('data/raw/olist_products_dataset.csv')
    products.to_sql('products', engine, if_exists='replace', index=False)
    print(f"✓ Loaded {len(products)} products")
    
    # Load sellers
    sellers = pd.read_csv('data/raw/olist_sellers_dataset.csv')
    sellers.to_sql('sellers', engine, if_exists='replace', index=False)
    print(f"✓ Loaded {len(sellers)} sellers")
    
    # Load order_items
    order_items = pd.read_csv('data/raw/olist_order_items_dataset.csv')
    order_items.to_sql('order_items', engine, if_exists='replace', index=False)
    print(f"✓ Loaded {len(order_items)} order items")

def setup_analytics_db():
    """Create derived tables in analytics_db"""
    sales_engine = create_engine(os.getenv('SALES_DB_URL'))
    analytics_engine = create_engine(os.getenv('ANALYTICS_DB_URL'))
    
    # Create customer_segments (RFM analysis)
    query = """
    SELECT 
        c.customer_id,
        CASE 
            WHEN SUM(p.payment_value) > 1000 THEN 'VIP'
            WHEN SUM(p.payment_value) > 500 THEN 'Regular'
            ELSE 'Occasional'
        END as segment,
        SUM(p.payment_value) as lifetime_value,
        MAX(o.order_purchase_timestamp) as last_purchase_date,
        CURRENT_TIMESTAMP as updated_at
    FROM customers c
    JOIN orders o ON c.customer_id = o.customer_id
    JOIN payments p ON o.order_id = p.order_id
    GROUP BY c.customer_id
    """
    
    customer_segments = pd.read_sql(query, sales_engine)
    customer_segments.to_sql('customer_segments', analytics_engine, 
                            if_exists='replace', index=False)
    print(f"✓ Created customer_segments: {len(customer_segments)} records")
    
    # Create daily_metrics
    query = """
    SELECT 
        DATE(o.order_purchase_timestamp) as date,
        SUM(p.payment_value) as total_sales,
        COUNT(DISTINCT o.order_id) as total_orders,
        AVG(p.payment_value) as avg_order_value,
        COUNT(DISTINCT CASE 
            WHEN o.order_purchase_timestamp::date = c.customer_created_at::date 
            THEN c.customer_id END) as new_customers
    FROM orders o
    JOIN payments p ON o.order_id = p.order_id
    LEFT JOIN customers c ON o.customer_id = c.customer_id
    GROUP BY DATE(o.order_purchase_timestamp)
    ORDER BY date
    """
    
    # Note: Adjust column names based on actual Olist schema
    # This is a template - verify actual column names
    
    print("✓ Analytics database setup complete")

if __name__ == "__main__":
    print("Setting up databases...")
    print("\n1. Sales DB:")
    setup_sales_db()
    print("\n2. Products DB:")
    setup_products_db()
    print("\n3. Analytics DB:")
    setup_analytics_db()
    print("\n✅ All databases ready!")
```

**Run setup:**
```bash
python scripts/setup_databases.py
```

**Verify:**
```bash
# Connect to each DB and check
psql ecommerce_sales -c "SELECT COUNT(*) FROM customers;"
psql ecommerce_products -c "SELECT COUNT(*) FROM products;"
psql ecommerce_analytics -c "SELECT COUNT(*) FROM customer_segments;"
```

### 4.5 Schema Metadata

**Create `data/schemas/schema_descriptions.yaml`:**
```yaml
sales_db:
  customers:
    description: >
      Customer master data including buyer/client information, 
      contact details, and location. Use for customer lists, 
      buyer information, client data.
    columns:
      customer_id: Unique identifier for each customer/buyer/client
      name: Customer/client/buyer name
      email: Contact email for communication
      city: Location, city, area, region
      state: State, province, region
    relationships:
      - "Referenced by orders.customer_id (1:N)"
    common_queries:
      - "list customers"
      - "customers in Jakarta"
      - "customer by email"
  
  orders:
    description: >
      Sales transactions, purchase records, order history.
      Contains order dates, amounts, status for revenue analysis.
    columns:
      order_id: Unique order/transaction/purchase identifier
      customer_id: Links to customers (buyer/client)
      order_date: Purchase date, transaction timestamp
      total_amount: Order value, purchase amount
      status: Order state (completed, pending, cancelled)
    relationships:
      - "FK to customers.customer_id"
      - "Referenced by payments.order_id (1:1)"
    common_queries:
      - "sales this month"
      - "completed orders"
      - "order history"
  
  payments:
    description: >
      Payment transactions, revenue data, actual money received.
      Use payment_value for revenue calculations (not order total_amount).
    columns:
      payment_id: Unique payment transaction identifier
      order_id: Links to orders
      payment_method: How paid (credit card, bank transfer)
      payment_value: Actual revenue, money received (use for sales)
      payment_date: When payment received
    relationships:
      - "FK to orders.order_id"
    common_queries:
      - "total revenue"
      - "payments by method"
      - "sales analysis"

products_db:
  products:
    description: >
      Product catalog, item information, merchandise details.
      Contains product names, categories, prices.
    columns:
      product_id: Unique product/item identifier
      product_name: Product/item name, title
      category: Product type, classification
      price: Product price, cost
      weight_kg: Weight in kilograms
    relationships:
      - "Referenced by order_items.product_id (1:N)"
    common_queries:
      - "list products"
      - "products in category"
      - "product by name"
  
  sellers:
    description: >
      Seller/vendor/supplier information.
    columns:
      seller_id: Unique seller/vendor identifier
      seller_name: Seller/vendor name
      city: Seller location
      state: Seller state/region
      rating: Seller rating (0.00-5.00)
    relationships:
      - "Referenced by order_items.seller_id (1:N)"
    common_queries:
      - "top sellers"
      - "sellers by rating"
      - "seller performance"
  
  order_items:
    description: >
      Order line items, linking orders to products and sellers.
      Bridge table for order-product-seller relationships.
    columns:
      order_item_id: Unique line item identifier
      order_id: Links to orders (cross-database reference)
      product_id: Links to products
      seller_id: Links to sellers
      quantity: Quantity ordered
      price: Item price
    relationships:
      - "FK to products.product_id"
      - "FK to sellers.seller_id"
      - "order_id references sales_db.orders (cross-DB)"
    common_queries:
      - "items in order"
      - "products sold"

analytics_db:
  customer_segments:
    description: >
      Customer segmentation, classification into VIP/Regular/Occasional
      based on lifetime value (RFM analysis).
    columns:
      customer_id: References customers (cross-DB)
      segment: Customer tier (VIP, Regular, Occasional)
      lifetime_value: Total spending, LTV
      last_purchase_date: Most recent purchase
      updated_at: When segmentation was updated
    relationships:
      - "customer_id references sales_db.customers (cross-DB)"
    common_queries:
      - "VIP customers"
      - "customer segments"
      - "lifetime value analysis"
  
  daily_metrics:
    description: >
      Daily aggregated business metrics, KPIs, performance indicators.
      Pre-calculated for fast dashboard queries.
    columns:
      date: Metric date
      total_sales: Revenue for the day
      total_orders: Order count
      avg_order_value: Average order size
      new_customers: New customer count
    common_queries:
      - "sales by day"
      - "daily trends"
      - "business metrics"
```

---

## 5. Component Implementation

### 5.1 Base Models

**Create `src/models/query_models.py`:**
```python
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum

class QueryIntent(str, Enum):
    SIMPLE_SELECT = "simple_select"
    FILTERED_QUERY = "filtered_query"
    AGGREGATION = "aggregation"
    MULTI_TABLE_JOIN = "multi_table_join"
    COMPLEX_ANALYTICS = "complex_analytics"
    AMBIGUOUS = "ambiguous"

class IntentResult(BaseModel):
    intent: QueryIntent
    confidence: float
    reason: Optional[str] = None

class RetrievedTable(BaseModel):
    db_name: str
    table_name: str
    columns: List[str]
    column_types: Dict[str, str]
    description: str
    relationships: List[str]
    similarity_score: Optional[float] = None

class SchemaRetrievalResult(BaseModel):
    retrieved_tables: List[RetrievedTable]
    retrieval_time_ms: float

class EvaluationResult(BaseModel):
    essential_tables: List[str]
    removed_tables: List[str]
    confidence: float
    missing_warning: Optional[str] = None

class SQLGenerationResult(BaseModel):
    sql: str
    generation_time_ms: float

class ValidationResult(BaseModel):
    valid: bool
    sql: str
    errors: List[str]
    warnings: List[str] = []

class ExecutionResult(BaseModel):
    success: bool
    data: Optional[List[Dict[str, Any]]] = None
    row_count: int
    execution_time_ms: float
    error: Optional[str] = None

class InsightResult(BaseModel):
    insights: str
    insight_generation_time_ms: float
```

**Create `src/models/response_models.py`:**
```python
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class QueryResponse(BaseModel):
    """Final response to user"""
    insights: str
    sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any]

class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    details: Optional[str] = None
    suggestion: Optional[str] = None
```

### 5.2 Configuration Loader

**Create `src/config.py`:**
```python
import yaml
import os
from dotenv import load_dotenv
from typing import Dict, Any

load_dotenv()

class Config:
    """Application configuration"""
    
    def __init__(self):
        self.config = self._load_yaml('config/config.yaml')
        self.databases = self._load_yaml('config/databases.yaml')
        self.few_shot = self._load_yaml('config/few_shot_examples.yaml')
        self.metrics = self._load_yaml('config/business_metrics.yaml')
        self.schemas = self._load_yaml('data/schemas/schema_descriptions.yaml')
        
        # API Keys from environment
        self.anthropic_key = os.getenv('ANTHROPIC_API_KEY')
        self.openai_key = os.getenv('OPENAI_API_KEY')
        
        if not self.anthropic_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env")
        if not self.openai_key:
            raise ValueError("OPENAI_API_KEY not found in .env")
    
    def _load_yaml(self, path: str) -> Dict[str, Any]:
        """Load YAML file"""
        with open(path, 'r') as f:
            return yaml.safe_load(f)
    
    @property
    def llm_config(self) -> Dict[str, Any]:
        return self.config['llm']
    
    @property
    def db_urls(self) -> Dict[str, str]:
        return {
            'sales_db': os.getenv('SALES_DB_URL'),
            'products_db': os.getenv('PRODUCTS_DB_URL'),
            'analytics_db': os.getenv('ANALYTICS_DB_URL')
        }

# Global config instance
config = Config()
```

**Create `config/config.yaml`:**
```yaml
llm:
  model: claude-sonnet-4-20250514
  temperature: 0
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

**Create `config/few_shot_examples.yaml`:**
```yaml
examples:
  - question: "Show all customers"
    sql: "SELECT * FROM customers LIMIT 100;"
  
  - question: "How many orders were placed?"
    sql: "SELECT COUNT(*) as total_orders FROM orders;"
  
  - question: "Total sales this month"
    sql: |
      SELECT SUM(payment_value) as total_sales
      FROM payments p
      JOIN orders o ON p.order_id = o.order_id
      WHERE EXTRACT(MONTH FROM o.order_purchase_timestamp) = EXTRACT(MONTH FROM CURRENT_DATE)
        AND EXTRACT(YEAR FROM o.order_purchase_timestamp) = EXTRACT(YEAR FROM CURRENT_DATE);
  
  - question: "Top 5 customers by total spending"
    sql: |
      SELECT 
          c.customer_id,
          c.customer_unique_id,
          SUM(p.payment_value) as total_spent
      FROM customers c
      JOIN orders o ON c.customer_id = o.customer_id
      JOIN payments p ON o.order_id = p.order_id
      GROUP BY c.customer_id, c.customer_unique_id
      ORDER BY total_spent DESC
      LIMIT 5;
  
  - question: "Products with no sales in the last 30 days"
    sql: |
      SELECT p.*
      FROM products p
      LEFT JOIN order_items oi ON p.product_id = oi.product_id
      LEFT JOIN orders o ON oi.order_id = o.order_id 
          AND o.order_purchase_timestamp >= CURRENT_DATE - INTERVAL '30 days'
      WHERE o.order_id IS NULL;
  
  - question: "Average order value by city"
    sql: |
      SELECT 
          c.customer_city,
          AVG(p.payment_value) as avg_order_value,
          COUNT(DISTINCT o.order_id) as num_orders
      FROM customers c
      JOIN orders o ON c.customer_id = o.customer_id
      JOIN payments p ON o.order_id = p.order_id
      GROUP BY c.customer_city
      ORDER BY avg_order_value DESC;
  
  - question: "Monthly sales trend for last 6 months"
    sql: |
      SELECT 
          DATE_TRUNC('month', o.order_purchase_timestamp) as month,
          SUM(p.payment_value) as total_sales,
          COUNT(DISTINCT o.order_id) as num_orders
      FROM orders o
      JOIN payments p ON o.order_id = p.order_id
      WHERE o.order_purchase_timestamp >= CURRENT_DATE - INTERVAL '6 months'
      GROUP BY DATE_TRUNC('month', o.order_purchase_timestamp)
      ORDER BY month;
```

### 5.3 Component 1: Intent Classifier

**Create `src/components/intent_classifier.py`:**
```python
from anthropic import Anthropic
from src.models.query_models import QueryIntent, IntentResult
from src.config import config
import time

class IntentClassifier:
    """
    Classify user queries into intent categories.
    
    Agentic component using Claude Sonnet 4.
    """
    
    def __init__(self):
        self.client = Anthropic(api_key=config.anthropic_key)
        self.model = config.llm_config['model']
    
    def classify(self, user_query: str) -> IntentResult:
        """
        Classify query intent.
        
        Returns:
            IntentResult with category and confidence
        """
        start_time = time.time()
        
        prompt = self._build_prompt(user_query)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=100,
            temperature=0,  # Deterministic
            messages=[{"role": "user", "content": prompt}]
        )
        
        intent_text = response.content[0].text.strip().lower()
        
        # Parse response
        try:
            intent = QueryIntent(intent_text)
        except ValueError:
            # If LLM returns unexpected value, mark as ambiguous
            intent = QueryIntent.AMBIGUOUS
        
        # Calculate confidence (simple heuristic for POC)
        confidence = 0.95 if intent != QueryIntent.AMBIGUOUS else 0.3
        
        elapsed = (time.time() - start_time) * 1000  # ms
        
        return IntentResult(
            intent=intent,
            confidence=confidence,
            reason=None if intent != QueryIntent.AMBIGUOUS else "Insufficient information"
        )
    
    def _build_prompt(self, user_query: str) -> str:
        """Build classification prompt"""
        return f"""Classify this database query into ONE category:

Query: "{user_query}"

Categories:
1. simple_select - Basic data retrieval from single table
   Examples: "Show all customers", "List products"

2. filtered_query - Single table with WHERE conditions
   Examples: "Customers from Jakarta", "Orders above 1M"

3. aggregation - Requires SUM, COUNT, AVG, GROUP BY
   Examples: "Total sales by region", "Average order value"

4. multi_table_join - Needs JOIN across 2+ tables
   Examples: "Customers with their orders", "Top buyers"

5. complex_analytics - Multiple operations, subqueries
   Examples: "Month-over-month growth", "Customer cohort analysis"

6. ambiguous - Unclear intent, needs clarification
   Examples: "Show me the data", "What about yesterday?"

Return ONLY the category name (e.g., "multi_table_join"), nothing else.

If the query lacks critical information (no clear metric, timeframe, or entity), 
classify as "ambiguous"."""
```

### 5.4 Component 2: Schema Retriever

**Create `scripts/index_schemas.py`:**
```python
import chromadb
from chromadb.utils import embedding_functions
from src.config import config
import os

def index_schemas():
    """
    Index all table schemas into ChromaDB.
    
    Run this once during setup or when schemas change.
    """
    # Initialize ChromaDB
    client = chromadb.PersistentClient(
        path=config.vector_db['persist_directory']
    )
    
    # Embedding function
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=config.openai_key,
        model_name=config.embeddings['model']
    )
    
    # Create or get collection
    try:
        collection = client.get_collection(
            name=config.vector_db['collection_name'],
            embedding_function=openai_ef
        )
        # Delete existing collection to re-index
        client.delete_collection(config.vector_db['collection_name'])
    except:
        pass
    
    collection = client.create_collection(
        name=config.vector_db['collection_name'],
        embedding_function=openai_ef
    )
    
    # Index all tables
    schemas = config.schemas
    
    documents = []
    metadatas = []
    ids = []
    
    for db_name, tables in schemas.items():
        for table_name, table_info in tables.items():
            # Create rich description
            description = f"""Table: {table_name} in {db_name}

Business Purpose: {table_info['description']}

Columns:
"""
            for col_name, col_desc in table_info['columns'].items():
                description += f"- {col_name}: {col_desc}\n"
            
            description += f"\nRelationships:\n"
            for rel in table_info.get('relationships', []):
                description += f"- {rel}\n"
            
            description += f"\nCommon Queries:\n"
            for query in table_info.get('common_queries', []):
                description += f"- {query}\n"
            
            # Prepare for ChromaDB
            doc_id = f"{db_name}.{table_name}"
            
            documents.append(description)
            metadatas.append({
                "db_name": db_name,
                "table_name": table_name,
                "columns": list(table_info['columns'].keys())
            })
            ids.append(doc_id)
    
    # Add to collection
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    
    print(f"✅ Indexed {len(documents)} tables into ChromaDB")
    print(f"Collection: {config.vector_db['collection_name']}")

if __name__ == "__main__":
    print("Indexing schemas...")
    index_schemas()
```

**Run indexing:**
```bash
python scripts/index_schemas.py
```

**Create `src/components/schema_retriever.py`:**
```python
import chromadb
from chromadb.utils import embedding_functions
from typing import List
from src.models.query_models import RetrievedTable, SchemaRetrievalResult
from src.config import config
import time

class SchemaRetriever:
    """
    Retrieve relevant tables using RAG (semantic search).
    
    Traditional component (deterministic vector search).
    """
    
    def __init__(self):
        # Connect to ChromaDB
        client = chromadb.PersistentClient(
            path=config.vector_db['persist_directory']
        )
        
        # Embedding function
        openai_ef = embedding_functions.OpenAIEmbeddingFunction(
            api_key=config.openai_key,
            model_name=config.embeddings['model']
        )
        
        # Get collection
        self.collection = client.get_collection(
            name=config.vector_db['collection_name'],
            embedding_function=openai_ef
        )
    
    def retrieve(self, user_query: str, top_k: int = 5) -> SchemaRetrievalResult:
        """
        Retrieve top-K most relevant tables.
        
        Args:
            user_query: User's question
            top_k: Number of tables to retrieve
        
        Returns:
            SchemaRetrievalResult with retrieved tables
        """
        start_time = time.time()
        
        # Semantic search
        results = self.collection.query(
            query_texts=[user_query],
            n_results=top_k
        )
        
        # Parse results
        retrieved_tables = []
        
        for i in range(len(results['ids'][0])):
            metadata = results['metadatas'][0][i]
            
            # Get full schema info from config
            db_name = metadata['db_name']
            table_name = metadata['table_name']
            
            table_info = config.schemas[db_name][table_name]
            
            retrieved_tables.append(RetrievedTable(
                db_name=db_name,
                table_name=table_name,
                columns=metadata['columns'],
                column_types={},  # Not stored in ChromaDB for POC
                description=table_info['description'],
                relationships=table_info.get('relationships', []),
                similarity_score=results['distances'][0][i] if results['distances'] else None
            ))
        
        elapsed = (time.time() - start_time) * 1000
        
        return SchemaRetrievalResult(
            retrieved_tables=retrieved_tables,
            retrieval_time_ms=elapsed
        )
```

### 5.5 Component 3: Retrieval Evaluator

**Create `src/components/retrieval_evaluator.py`:**
```python
from anthropic import Anthropic
from typing import List
from src.models.query_models import RetrievedTable, EvaluationResult
from src.config import config
import time
import json

class RetrievalEvaluator:
    """
    Evaluate and filter retrieved tables.
    
    Agentic component using Claude Sonnet 4.
    """
    
    def __init__(self):
        self.client = Anthropic(api_key=config.anthropic_key)
        self.model = config.llm_config['model']
    
    def evaluate(
        self, 
        user_query: str, 
        retrieved_tables: List[RetrievedTable]
    ) -> EvaluationResult:
        """
        Evaluate which tables are actually needed.
        
        Returns:
            EvaluationResult with filtered tables
        """
        start_time = time.time()
        
        prompt = self._build_prompt(user_query, retrieved_tables)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        response_text = response.content[0].text.strip()
        
        # Parse JSON response
        try:
            result_json = json.loads(response_text)
            
            return EvaluationResult(
                essential_tables=result_json.get('essential_tables', []),
                removed_tables=result_json.get('removed', []),
                confidence=result_json.get('confidence', 0.5),
                missing_warning=result_json.get('missing_warning')
            )
        except json.JSONDecodeError:
            # Fallback: use all retrieved tables
            return EvaluationResult(
                essential_tables=[t.table_name for t in retrieved_tables],
                removed_tables=[],
                confidence=0.5,
                missing_warning="Could not parse evaluation"
            )
    
    def _build_prompt(self, user_query: str, tables: List[RetrievedTable]) -> str:
        """Build evaluation prompt"""
        
        tables_text = ""
        for i, table in enumerate(tables, 1):
            tables_text += f"{i}. {table.table_name} ({table.db_name})\n"
            tables_text += f"   Description: {table.description}\n"
            tables_text += f"   Columns: {', '.join(table.columns)}\n\n"
        
        return f"""Evaluate which tables are ACTUALLY needed for this query.

User Query: "{user_query}"

Retrieved Tables:
{tables_text}

Task:
1. Rate each table's relevance (1-5 scale)
2. Identify tables that are essential (score >= 3)
3. Detect if critical tables are missing
4. Return confidence score (0-1)

Return ONLY a JSON object with this structure:
{{
  "essential_tables": ["table1", "table2"],
  "removed": ["table3", "table4"],
  "confidence": 0.95,
  "missing_warning": null
}}

Be strict: Only include tables that are directly needed for the query.
If essential tables seem missing, note it in missing_warning."""
```

### 5.6 Component 4: SQL Generator

**Create `src/components/sql_generator.py`:**
```python
from anthropic import Anthropic
from typing import List
from src.models.query_models import RetrievedTable, SQLGenerationResult
from src.config import config
import time
import re

class SQLGenerator:
    """
    Generate SQL from natural language.
    
    Agentic component with few-shot prompting.
    """
    
    def __init__(self):
        self.client = Anthropic(api_key=config.anthropic_key)
        self.model = config.llm_config['model']
        self.examples = config.few_shot['examples']
    
    def generate(
        self, 
        user_query: str, 
        relevant_tables: List[RetrievedTable]
    ) -> SQLGenerationResult:
        """
        Generate SQL query.
        
        Returns:
            SQLGenerationResult with SQL string
        """
        start_time = time.time()
        
        prompt = self._build_prompt(user_query, relevant_tables)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            temperature=0,  # Deterministic
            messages=[{"role": "user", "content": prompt}]
        )
        
        sql = response.content[0].text.strip()
        
        # Clean SQL (remove markdown if present)
        sql = self._clean_sql(sql)
        
        elapsed = (time.time() - start_time) * 1000
        
        return SQLGenerationResult(
            sql=sql,
            generation_time_ms=elapsed
        )
    
    def _build_prompt(self, user_query: str, tables: List[RetrievedTable]) -> str:
        """Build SQL generation prompt with few-shot examples"""
        
        # Schema context
        schema_text = "Available Tables:\n\n"
        for table in tables:
            schema_text += f"Table: {table.table_name}\n"
            schema_text += f"Columns: {', '.join(table.columns)}\n"
            if table.relationships:
                schema_text += f"Relationships:\n"
                for rel in table.relationships:
                    schema_text += f"  - {rel}\n"
            schema_text += "\n"
        
        # Few-shot examples
        examples_text = "Example Queries:\n\n"
        for ex in self.examples[:7]:  # Use first 7 examples
            examples_text += f"Question: {ex['question']}\n"
            examples_text += f"SQL: {ex['sql']}\n\n"
        
        # Final prompt
        prompt = f"""You are a PostgreSQL SQL expert. Generate accurate SQL queries.

{schema_text}

{examples_text}

Now convert this question to SQL:

Question: {user_query}

Return ONLY the SQL query, no explanation.
Use PostgreSQL syntax.
Always add LIMIT clause for SELECT queries (default: LIMIT 100).
"""
        
        return prompt
    
    def _clean_sql(self, sql: str) -> str:
        """Remove markdown formatting if present"""
        # Remove ```sql and ``` markers
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*', '', sql)
        return sql.strip()
```

### 5.7 Component 5: SQL Validator

**Create `src/components/sql_validator.py`:**
```python
import sqlparse
from anthropic import Anthropic
from src.models.query_models import ValidationResult
from src.config import config
import re

class SQLValidator:
    """
    Validate and auto-fix SQL queries.
    
    Hybrid component: Traditional checks + Agentic auto-fix.
    """
    
    def __init__(self):
        self.client = Anthropic(api_key=config.anthropic_key)
        self.model = config.llm_config['model']
        self.max_retries = config.validation['max_retry_attempts']
    
    def validate_and_fix(self, sql: str, user_query: str = "") -> ValidationResult:
        """
        Validate SQL with auto-fix retry.
        
        Returns:
            ValidationResult with validity status
        """
        for attempt in range(self.max_retries):
            errors = []
            warnings = []
            
            # Check 1: Syntax
            syntax_errors = self._check_syntax(sql)
            if syntax_errors:
                errors.extend(syntax_errors)
            
            # Check 2: Security
            security_errors = self._check_security(sql)
            if security_errors:
                errors.extend(security_errors)
                # Security errors are NON-FIXABLE
                return ValidationResult(
                    valid=False,
                    sql=sql,
                    errors=security_errors,
                    warnings=[]
                )
            
            # Check 3: Performance warnings
            perf_warnings = self._check_performance(sql)
            warnings.extend(perf_warnings)
            
            # If no errors, success
            if not errors:
                return ValidationResult(
                    valid=True,
                    sql=sql,
                    errors=[],
                    warnings=warnings
                )
            
            # Try auto-fix
            if attempt < self.max_retries - 1:
                sql = self._auto_fix(sql, errors, user_query)
            else:
                # Max retries reached
                return ValidationResult(
                    valid=False,
                    sql=sql,
                    errors=errors,
                    warnings=warnings
                )
        
        return ValidationResult(valid=False, sql=sql, errors=errors, warnings=warnings)
    
    def _check_syntax(self, sql: str) -> List[str]:
        """Check SQL syntax"""
        errors = []
        try:
            parsed = sqlparse.parse(sql)
            if not parsed:
                errors.append("SQL parsing failed - invalid syntax")
        except Exception as e:
            errors.append(f"Syntax error: {str(e)}")
        return errors
    
    def _check_security(self, sql: str) -> List[str]:
        """Check for SQL injection patterns"""
        errors = []
        
        sql_upper = sql.upper()
        
        # Dangerous patterns
        patterns = [
            (r"DROP\s+TABLE", "DROP TABLE detected"),
            (r"DELETE\s+FROM", "DELETE FROM detected"),
            (r"UPDATE\s+", "UPDATE detected"),
            (r"INSERT\s+INTO", "INSERT INTO detected"),
            (r"--", "SQL comment detected"),
            (r"/\*", "Block comment detected"),
        ]
        
        for pattern, msg in patterns:
            if re.search(pattern, sql_upper):
                errors.append(f"SECURITY: {msg} - only SELECT allowed")
        
        # Must start with SELECT
        if not sql_upper.strip().startswith('SELECT'):
            errors.append("SECURITY: Only SELECT queries are allowed")
        
        return errors
    
    def _check_performance(self, sql: str) -> List[str]:
        """Performance warnings"""
        warnings = []
        
        # SELECT * without LIMIT
        if re.search(r'SELECT\s+\*', sql, re.IGNORECASE):
            if not re.search(r'LIMIT\s+\d+', sql, re.IGNORECASE):
                warnings.append("Consider adding LIMIT clause")
        
        return warnings
    
    def _auto_fix(self, sql: str, errors: List[str], user_query: str) -> str:
        """Attempt to fix SQL using LLM"""
        
        prompt = f"""Fix this SQL query.

User Question: {user_query}

Current SQL:
{sql}

Errors Found:
{chr(10).join(f"- {e}" for e in errors)}

Return ONLY the corrected SQL query, no explanation."""
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1000,
            temperature=0,
            messages=[{"role": "user", "content": prompt}]
        )
        
        fixed_sql = response.content[0].text.strip()
        
        # Clean
        fixed_sql = re.sub(r'```sql\s*', '', fixed_sql)
        fixed_sql = re.sub(r'```\s*', '', fixed_sql)
        
        return fixed_sql.strip()
```

### 5.8 Component 6: Query Executor

**Create `src/components/query_executor.py`:**
```python
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from src.models.query_models import ExecutionResult
from src.config import config
import time

class QueryExecutor:
    """
    Execute SQL queries safely.
    
    Traditional component (deterministic execution).
    """
    
    def __init__(self):
        # Create database engines
        self.engines = {
            db_name: create_engine(
                db_url,
                pool_size=5,
                max_overflow=10
            )
            for db_name, db_url in config.db_urls.items()
        }
        
        self.timeout = config.validation['sql_timeout_seconds']
        self.max_rows = config.validation['max_result_rows']
    
    def execute(self, sql: str, db_name: str = 'sales_db') -> ExecutionResult:
        """
        Execute SQL with safety controls.
        
        Args:
            sql: SQL query to execute
            db_name: Target database
        
        Returns:
            ExecutionResult with data or error
        """
        start_time = time.time()
        
        try:
            engine = self.engines.get(db_name)
            if not engine:
                return ExecutionResult(
                    success=False,
                    data=None,
                    row_count=0,
                    execution_time_ms=0,
                    error=f"Database '{db_name}' not found"
                )
            
            with engine.connect() as conn:
                # Set timeout (PostgreSQL)
                conn.execute(text(f"SET statement_timeout = {self.timeout * 1000}"))
                
                # Execute query
                result = conn.execute(text(sql))
                
                # Fetch results (with row limit)
                rows = result.fetchmany(self.max_rows)
                
                # Convert to list of dicts
                columns = result.keys()
                data = [dict(zip(columns, row)) for row in rows]
                
                elapsed = (time.time() - start_time) * 1000
                
                return ExecutionResult(
                    success=True,
                    data=data,
                    row_count=len(data),
                    execution_time_ms=elapsed,
                    error=None
                )
        
        except SQLAlchemyError as e:
            elapsed = (time.time() - start_time) * 1000
            return ExecutionResult(
                success=False,
                data=None,
                row_count=0,
                execution_time_ms=elapsed,
                error=str(e)
            )
```

### 5.9 Component 7: Insight Generator

**Create `src/components/insight_generator.py`:**
```python
from anthropic import Anthropic
from typing import List, Dict, Any
from src.models.query_models import InsightResult
from src.config import config
import time

class InsightGenerator:
    """
    Generate human-readable insights from query results.
    
    Agentic component with conservative language.
    """
    
    def __init__(self):
        self.client = Anthropic(api_key=config.anthropic_key)
        self.model = config.llm_config['model']
    
    def generate(
        self, 
        user_query: str,
        sql: str,
        results: List[Dict[str, Any]],
        row_count: int
    ) -> InsightResult:
        """
        Generate insights from query results.
        
        Returns:
            InsightResult with natural language insights
        """
        start_time = time.time()
        
        # Format results
        results_text = self._format_results(results, row_count)
        
        prompt = self._build_prompt(user_query, sql, results_text)
        
        response = self.client.messages.create(
            model=self.model,
            max_tokens=500,
            temperature=0.3,  # Slightly creative
            messages=[{"role": "user", "content": prompt}]
        )
        
        insights = response.content[0].text.strip()
        
        # Combine with formatted data
        output = f"{insights}\n\n### Detailed Results\n\n{results_text}"
        
        elapsed = (time.time() - start_time) * 1000
        
        return InsightResult(
            insights=output,
            insight_generation_time_ms=elapsed
        )
    
    def _format_results(self, results: List[Dict[str, Any]], row_count: int) -> str:
        """Format results as markdown table"""
        if not results:
            return "No results found."
        
        # Get columns
        columns = list(results[0].keys())
        
        # Build table (show max 10 rows)
        display_results = results[:10]
        
        table = "| " + " | ".join(columns) + " |\n"
        table += "| " + " | ".join(["---"] * len(columns)) + " |\n"
        
        for row in display_results:
            values = [str(row[col]) for col in columns]
            table += "| " + " | ".join(values) + " |\n"
        
        if row_count > 10:
            table += f"\n... and {row_count - 10} more rows"
        
        return table
    
    def _build_prompt(self, user_query: str, sql: str, results_text: str) -> str:
        """Build insight generation prompt"""
        
        return f"""Generate a concise, business-friendly summary.

User Question: "{user_query}"

SQL Used:
{sql}

Results:
{results_text}

Instructions:
1. Provide a direct answer (2-3 sentences, grounded in data)
2. Highlight key observations (patterns visible in results)
3. Use conservative language: "suggests", "indicates", "appears"
   NOT: "proves", "shows definitively"
4. Do not imply causality without evidence
5. Do not give recommendations unless explicitly asked
6. Include any caveats or limitations

Be helpful but conservative. Focus on facts from the data."""
```

---

## 6. API Endpoints

### 6.1 FastAPI Application

**Create `src/main.py`:**
```python
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import time
import logging

# Import components
from src.components.intent_classifier import IntentClassifier
from src.components.schema_retriever import SchemaRetriever
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.components.query_executor import QueryExecutor
from src.components.insight_generator import InsightGenerator

from src.models.query_models import QueryIntent
from src.models.response_models import QueryResponse, ErrorResponse
from src.config import config

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI(title="Text-to-SQL Chatbot API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components
intent_classifier = IntentClassifier()
schema_retriever = SchemaRetriever()
retrieval_evaluator = RetrievalEvaluator()
sql_generator = SQLGenerator()
sql_validator = SQLValidator()
query_executor = QueryExecutor()
insight_generator = InsightGenerator()

# Request model
class QueryRequest(BaseModel):
    question: str

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Main endpoint: Process natural language query.
    """
    start_time = time.time()
    
    try:
        user_query = request.question
        logger.info(f"Processing query: {user_query}")
        
        # Component 1: Intent Classification
        intent_result = intent_classifier.classify(user_query)
        logger.info(f"Intent: {intent_result.intent}, Confidence: {intent_result.confidence}")
        
        if intent_result.intent == QueryIntent.AMBIGUOUS:
            return QueryResponse(
                insights="I need more information to answer your question. Could you clarify:\n"
                       "- What specific data are you interested in?\n"
                       "- For what time period?\n"
                       "- Any specific filters or criteria?",
                sql=None,
                data=None,
                metadata={
                    "intent": "ambiguous",
                    "reason": intent_result.reason
                }
            )
        
        # Component 2: Schema Retrieval
        retrieval_result = schema_retriever.retrieve(user_query, top_k=5)
        logger.info(f"Retrieved {len(retrieval_result.retrieved_tables)} tables")
        
        # Component 3: Retrieval Evaluation
        eval_result = retrieval_evaluator.evaluate(user_query, retrieval_result.retrieved_tables)
        logger.info(f"Essential tables: {eval_result.essential_tables}")
        
        # Filter tables
        essential_tables = [
            t for t in retrieval_result.retrieved_tables 
            if t.table_name in eval_result.essential_tables
        ]
        
        # Component 4: SQL Generation
        sql_result = sql_generator.generate(user_query, essential_tables)
        logger.info(f"Generated SQL: {sql_result.sql[:100]}...")
        
        # Component 5: SQL Validation
        validation_result = sql_validator.validate_and_fix(sql_result.sql, user_query)
        
        if not validation_result.valid:
            return QueryResponse(
                insights=f"I couldn't generate valid SQL. Errors:\n" + 
                        "\n".join(f"- {e}" for e in validation_result.errors),
                sql=validation_result.sql,
                data=None,
                metadata={
                    "errors": validation_result.errors,
                    "stage": "validation"
                }
            )
        
        # Component 6: Query Execution
        # Determine database (default: sales_db, can be improved with logic)
        db_name = 'sales_db'
        execution_result = query_executor.execute(validation_result.sql, db_name)
        
        if not execution_result.success:
            return QueryResponse(
                insights=f"Query execution failed: {execution_result.error}",
                sql=validation_result.sql,
                data=None,
                metadata={
                    "execution_error": execution_result.error
                }
            )
        
        # Component 7: Insight Generation
        insight_result = insight_generator.generate(
            user_query,
            validation_result.sql,
            execution_result.data,
            execution_result.row_count
        )
        
        total_time = (time.time() - start_time) * 1000
        
        return QueryResponse(
            insights=insight_result.insights,
            sql=validation_result.sql,
            data=execution_result.data,
            metadata={
                "intent": intent_result.intent.value,
                "tables_used": eval_result.essential_tables,
                "execution_time_ms": total_time,
                "row_count": execution_result.row_count,
                "component_times": {
                    "intent_classification": intent_result.confidence,  # Placeholder
                    "schema_retrieval": retrieval_result.retrieval_time_ms,
                    "sql_generation": sql_result.generation_time_ms,
                    "execution": execution_result.execution_time_ms,
                    "insight_generation": insight_result.insight_generation_time_ms
                }
            }
        )
    
    except Exception as e:
        logger.error(f"Error processing query: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### 6.2 Streamlit UI

**Create `src/ui/app.py`:**
```python
import streamlit as st
import requests
import json

# Page config
st.set_page_config(
    page_title="Text-to-SQL Chatbot",
    page_icon="🤖",
    layout="wide"
)

st.title("🤖 Text-to-SQL Analytics Chatbot")
st.write("Ask questions about your data in natural language!")

# API endpoint
API_URL = "http://localhost:8000/query"

# Initialize session state
if 'history' not in st.session_state:
    st.session_state.history = []

# Query input
user_question = st.text_input(
    "Your question:",
    placeholder="e.g., Who are the top 5 customers by revenue this month?"
)

if st.button("Ask", type="primary") and user_question:
    with st.spinner("Thinking..."):
        try:
            # Call API
            response = requests.post(
                API_URL,
                json={"question": user_question}
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Display insights
                st.markdown("### 💡 Answer")
                st.write(result['insights'])
                
                # Show SQL (collapsible)
                with st.expander("🔍 View SQL Query"):
                    if result['sql']:
                        st.code(result['sql'], language='sql')
                
                # Show raw data (collapsible)
                with st.expander("📊 View Raw Data"):
                    if result['data']:
                        st.json(result['data'])
                
                # Show metadata (collapsible)
                with st.expander("⚙️ Metadata"):
                    st.json(result['metadata'])
                
                # Add to history
                st.session_state.history.append({
                    "question": user_question,
                    "insights": result['insights'],
                    "sql": result['sql']
                })
            else:
                st.error(f"Error: {response.status_code}")
                st.write(response.text)
        
        except Exception as e:
            st.error(f"Error: {str(e)}")

# Sidebar: Query history
with st.sidebar:
    st.header("📜 Query History")
    
    if st.session_state.history:
        for i, item in enumerate(reversed(st.session_state.history)):
            with st.expander(f"Q{len(st.session_state.history) - i}: {item['question'][:50]}..."):
                st.write("**Question:**", item['question'])
                st.write("**SQL:**")
                st.code(item['sql'], language='sql')
    else:
        st.write("No queries yet")
    
    if st.button("Clear History"):
        st.session_state.history = []
        st.rerun()

# Footer
st.markdown("---")
st.markdown("*POC v1.0 - Text-to-SQL Chatbot*")
```

---

## 7. Configuration Management

All configs already covered in Section 5.2 (Config Loader).

**Files created:**
- `config/config.yaml` ✓
- `config/databases.yaml` → Create with DB URLs
- `config/few_shot_examples.yaml` ✓
- `config/business_metrics.yaml` → Optional for POC
- `data/schemas/schema_descriptions.yaml` ✓

---

## 8. Code Standards & Conventions

### 8.1 Python Style

**Follow:**
- PEP 8 style guide
- Type hints for all functions
- Docstrings for all classes/functions
- Max line length: 100 characters

**Example:**
```python
def process_query(user_query: str, max_retries: int = 2) -> QueryResponse:
    """
    Process natural language query through pipeline.
    
    Args:
        user_query: User's natural language question
        max_retries: Maximum retry attempts for failed components
    
    Returns:
        QueryResponse with insights, SQL, and metadata
    
    Raises:
        ValueError: If query is empty
        RuntimeError: If all components fail
    """
    pass
```

### 8.2 Naming Conventions
```
Classes: PascalCase (IntentClassifier)
Functions: snake_case (classify_intent)
Constants: UPPER_SNAKE_CASE (MAX_RETRY_ATTEMPTS)
Private methods: _leading_underscore (_build_prompt)
```

### 8.3 Error Handling
```python
# Always use specific exceptions
try:
    result = component.process(data)
except ValueError as e:
    logger.error(f"Invalid input: {e}")
    raise
except RuntimeError as e:
    logger.error(f"Processing failed: {e}")
    # Fallback logic
    result = default_value
```

### 8.4 Logging
```python
import logging

logger = logging.getLogger(__name__)

# Use appropriate levels
logger.debug("Detailed debug info")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)  # Include traceback
```

---

## 9. Testing Strategy

**(Detailed testing covered in 03_TEST_STRATEGY.md)**

**Quick reference:**
```bash
# Run all tests
python scripts/run_tests.py

# Run specific component tests
pytest tests/test_components.py::test_intent_classifier

# Run integration tests
pytest tests/test_integration.py
```

---

## 10. Deployment Guide

### 10.1 Local Development
```bash
# Terminal 1: Run API
uvicorn src.main:app --reload --port 8000

# Terminal 2: Run UI
streamlit run src/ui/app.py
```

### 10.2 Production (Docker - Optional)
```yaml
# docker-compose.yml
version: '3.8'

services:
  api:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
    depends_on:
      - postgres
  
  postgres:
    image: postgres:14
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_PASSWORD=postgres
    volumes:
      - pgdata:/var/lib/postgresql/data

volumes:
  pgdata:
```

---

## 11. Troubleshooting

### Common Issues

**Issue: ChromaDB collection not found**
```bash
# Solution: Re-run indexing
python scripts/index_schemas.py
```

**Issue: Database connection refused**
```bash
# Check PostgreSQL is running
brew services list  # Mac
sudo systemctl status postgresql  # Linux

# Check connection string in .env
psql $SALES_DB_URL
```

**Issue: API key errors**
```bash
# Verify keys are set
echo $ANTHROPIC_API_KEY
echo $OPENAI_API_KEY

# Check .env file exists
cat .env
```

**Issue: SQL validation always fails**
```bash
# Check logs
tail -f logs/app.log

# Test component directly
python -c "from src.components.sql_validator import SQLValidator; v = SQLValidator(); print(v.validate_and_fix('SELECT * FROM customers LIMIT 10'))"
```

---

## 12. Development Workflow

### Day-by-Day Plan

**Day 1-2: Setup**
- ✓ Environment setup
- ✓ Database creation & data loading
- ✓ Schema indexing
- ✓ Config files

**Day 3-4: Core Pipeline**
- ✓ Implement all 7 components
- ✓ Wire together in main.py
- ✓ Test each component individually

**Day 5: API & UI**
- ✓ FastAPI endpoints
- ✓ Streamlit UI
- ✓ End-to-end testing

**Day 6: Testing & Fixes**
- ✓ Run 20 test queries
- ✓ Fix bugs
- ✓ Improve accuracy

**Day 7: Demo Prep**
- ✓ Polish UI
- ✓ Prepare demo script
- ✓ Documentation cleanup

---

**END OF IMPLEMENTATION GUIDE**

---

**Next Steps:**
1. Follow setup instructions (Sections 3-4)
2. Implement components (Section 5)
3. Test thoroughly (Section 9)
4. Deploy locally (Section 10)
5. Prepare demo (Section 12)

**For questions or issues, refer to Section 11 (Troubleshooting).**