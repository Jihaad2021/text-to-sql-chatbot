#!/bin/bash

echo "🚀 Setting up Text-to-SQL Chatbot Project Structure..."
echo ""

# Create main directories
echo "📁 Creating directories..."
mkdir -p src/{components,models,utils,ui}
mkdir -p data/{raw,processed,schemas}
mkdir -p scripts
mkdir -p tests
mkdir -p config
mkdir -p logs
mkdir -p docs
mkdir -p chroma_db

echo "✅ Directories created"
echo ""

# Create source files (empty for now)
echo "📄 Creating source files..."

# src/__init__.py
touch src/__init__.py

# src/main.py
cat > src/main.py << 'MAIN'
"""
FastAPI Application - Main Entry Point

This is the main API server that orchestrates the 7-component pipeline.
"""

from fastapi import FastAPI

app = FastAPI(title="Text-to-SQL Chatbot API")

@app.get("/")
def root():
    return {"message": "Text-to-SQL Chatbot API"}

@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "1.0.0"}

# TODO: Add /query endpoint
MAIN

# src/config.py
cat > src/config.py << 'CONFIG'
"""
Configuration Loader

Loads configuration from YAML files and environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    
    def __init__(self):
        # TODO: Load YAML configs
        pass
    
    @property
    def anthropic_key(self) -> str:
        return os.getenv('ANTHROPIC_API_KEY')
    
    @property
    def openai_key(self) -> str:
        return os.getenv('OPENAI_API_KEY')

# Global config instance
config = Config()
CONFIG

# Create component files
echo "Creating component files..."
touch src/components/__init__.py

# Component 1
cat > src/components/intent_classifier.py << 'COMP1'
"""
Component 1: Intent Classifier

Classifies user queries into intent categories using Claude Sonnet 4.
Type: Agentic
"""

class IntentClassifier:
    """Classify user query intent"""
    
    def __init__(self):
        # TODO: Initialize Claude client
        pass
    
    def classify(self, user_query: str):
        """Classify query intent"""
        # TODO: Implement classification
        pass
COMP1

# Component 2
cat > src/components/schema_retriever.py << 'COMP2'
"""
Component 2: Schema Retriever

Retrieves relevant table schemas using RAG (ChromaDB).
Type: Traditional
"""

class SchemaRetriever:
    """Retrieve relevant tables using semantic search"""
    
    def __init__(self):
        # TODO: Initialize ChromaDB
        pass
    
    def retrieve(self, user_query: str, top_k: int = 5):
        """Retrieve top-K relevant tables"""
        # TODO: Implement retrieval
        pass
COMP2

# Component 3
cat > src/components/retrieval_evaluator.py << 'COMP3'
"""
Component 3: Retrieval Evaluator

Evaluates and filters retrieved tables using Claude Sonnet 4.
Type: Agentic
"""

class RetrievalEvaluator:
    """Evaluate and filter retrieved tables"""
    
    def __init__(self):
        # TODO: Initialize Claude client
        pass
    
    def evaluate(self, user_query: str, retrieved_tables: list):
        """Evaluate relevance of retrieved tables"""
        # TODO: Implement evaluation
        pass
COMP3

# Component 4
cat > src/components/sql_generator.py << 'COMP4'
"""
Component 4: SQL Generator

Generates SQL from natural language using few-shot prompting.
Type: Agentic
"""

class SQLGenerator:
    """Generate SQL queries from natural language"""
    
    def __init__(self):
        # TODO: Initialize Claude client
        # TODO: Load few-shot examples
        pass
    
    def generate(self, user_query: str, relevant_tables: list):
        """Generate SQL query"""
        # TODO: Implement generation
        pass
COMP4

# Component 5
cat > src/components/sql_validator.py << 'COMP5'
"""
Component 5: SQL Validator

Validates SQL and attempts auto-fix using hybrid approach.
Type: Hybrid (Traditional + Agentic)
"""

class SQLValidator:
    """Validate and auto-fix SQL queries"""
    
    def __init__(self):
        # TODO: Initialize Claude client for auto-fix
        pass
    
    def validate_and_fix(self, sql: str, user_query: str = ""):
        """Validate SQL with auto-fix retry"""
        # TODO: Implement validation
        # TODO: Implement auto-fix
        pass
COMP5

# Component 6
cat > src/components/query_executor.py << 'COMP6'
"""
Component 6: Query Executor

Executes SQL queries with safety controls.
Type: Traditional
"""

class QueryExecutor:
    """Execute SQL queries safely"""
    
    def __init__(self):
        # TODO: Initialize database engines
        pass
    
    def execute(self, sql: str, db_name: str = 'sales_db'):
        """Execute SQL with safety controls"""
        # TODO: Implement execution
        pass
COMP6

# Component 7
cat > src/components/insight_generator.py << 'COMP7'
"""
Component 7: Insight Generator

Generates human-readable insights from query results.
Type: Agentic
"""

class InsightGenerator:
    """Generate natural language insights"""
    
    def __init__(self):
        # TODO: Initialize Claude client
        pass
    
    def generate(self, user_query: str, sql: str, results: list, row_count: int):
        """Generate insights from results"""
        # TODO: Implement insight generation
        pass
COMP7

# Create model files
echo "Creating model files..."
touch src/models/__init__.py

cat > src/models/query_models.py << 'MODELS'
"""
Pydantic Models for Query Pipeline

Defines data structures used throughout the pipeline.
"""

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

# TODO: Add more models (IntentResult, RetrievedTable, etc.)
MODELS

cat > src/models/response_models.py << 'RESPONSE'
"""
Response Models

Defines API response structures.
"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class QueryResponse(BaseModel):
    """Final response to user"""
    insights: str
    sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any]

# TODO: Add ErrorResponse model
RESPONSE

# Create utils files
echo "Creating utility files..."
touch src/utils/__init__.py

cat > src/utils/logger.py << 'LOGGER'
"""
Logging Configuration

Sets up application logging.
"""

import logging

def setup_logger(name: str):
    """Setup logger with formatting"""
    logger = logging.getLogger(name)
    # TODO: Configure logging format
    return logger
LOGGER

cat > src/utils/helpers.py << 'HELPERS'
"""
Helper Functions

Utility functions used across the application.
"""

# TODO: Add helper functions
HELPERS

# Create UI file
echo "Creating UI file..."
cat > src/ui/app.py << 'UI'
"""
Streamlit User Interface

Simple web interface for the chatbot.
"""

import streamlit as st

st.title("🤖 Text-to-SQL Analytics Chatbot")
st.write("Ask questions about your data in natural language!")

# TODO: Add UI components
UI

# Create script files
echo "Creating script files..."

cat > scripts/setup_databases.py << 'SETUPDB'
"""
Database Setup Script

Loads Olist dataset into 3 PostgreSQL databases.
"""

import pandas as pd
from sqlalchemy import create_engine
import os
from dotenv import load_dotenv

load_dotenv()

def setup_sales_db():
    """Load customers, orders, payments into sales_db"""
    # TODO: Implement
    print("Setting up sales_db...")
    pass

def setup_products_db():
    """Load products, sellers, order_items into products_db"""
    # TODO: Implement
    print("Setting up products_db...")
    pass

def setup_analytics_db():
    """Create derived tables in analytics_db"""
    # TODO: Implement
    print("Setting up analytics_db...")
    pass

if __name__ == "__main__":
    print("🗄️  Setting up databases...")
    setup_sales_db()
    setup_products_db()
    setup_analytics_db()
    print("✅ Database setup complete!")
SETUPDB

cat > scripts/index_schemas.py << 'INDEXSCH'
"""
Schema Indexing Script

Creates ChromaDB embeddings for all table schemas.
"""

import chromadb

def index_schemas():
    """Index all table schemas into ChromaDB"""
    # TODO: Implement
    print("📊 Indexing schemas...")
    pass

if __name__ == "__main__":
    print("Starting schema indexing...")
    index_schemas()
    print("✅ Schema indexing complete!")
INDEXSCH

cat > scripts/run_tests.py << 'RUNTESTS'
"""
Test Runner

Runs all 20 test queries and generates report.
"""

import json

def run_all_tests():
    """Run complete test suite"""
    # TODO: Implement
    print("🧪 Running tests...")
    pass

if __name__ == "__main__":
    print("="*60)
    print("TEXT-TO-SQL CHATBOT - TEST SUITE")
    print("="*60)
    run_all_tests()
RUNTESTS

# Create test files
echo "Creating test files..."
touch tests/__init__.py

cat > tests/test_components.py << 'TESTCOMP'
"""
Component Unit Tests

Tests each of the 7 components individually.
"""

import pytest

# TODO: Add component tests

def test_intent_classifier():
    """Test intent classification"""
    pass

def test_schema_retriever():
    """Test schema retrieval"""
    pass

# TODO: Add more tests
TESTCOMP

cat > tests/test_integration.py << 'TESTINT'
"""
Integration Tests

Tests end-to-end pipeline.
"""

import pytest

# TODO: Add integration tests

def test_end_to_end_simple_query():
    """Test complete pipeline with simple query"""
    pass

def test_end_to_end_join_query():
    """Test complete pipeline with JOIN query"""
    pass

# TODO: Add more tests
TESTINT

cat > tests/test_queries.json << 'TESTJSON'
{
  "test_suite": "POC Test Queries v1.0",
  "total_queries": 20,
  "queries": [
    {
      "id": "Q001",
      "question": "Show all customers",
      "expected_sql": "SELECT * FROM customers LIMIT 100;",
      "intent": "simple_select",
      "tables": ["customers"],
      "database": "sales_db",
      "difficulty": "simple",
      "expected_accuracy": 1.0
    }
  ]
}
TESTJSON

# Create config files
echo "Creating config files..."

cat > config/config.yaml << 'CONFIGYAML'
# Main Configuration

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
CONFIGYAML

cat > config/databases.yaml << 'DBYAML'
# Database Connections

databases:
  - name: sales_db
    description: Transactional data (customers, orders, payments)
  
  - name: products_db
    description: Product catalog (products, sellers, order_items)
  
  - name: analytics_db
    description: Derived analytics (segments, metrics)
DBYAML

cat > config/few_shot_examples.yaml << 'FEWSHOT'
# Few-Shot SQL Examples

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

# TODO: Add more examples (target: 7-10 examples)
FEWSHOT

# Create schema descriptions
cat > data/schemas/schema_descriptions.yaml << 'SCHEMAS'
# Schema Descriptions for RAG

sales_db:
  customers:
    description: >
      Customer master data including buyer/client information,
      contact details, and location.
    columns:
      customer_id: Unique identifier for each customer
      name: Customer/client/buyer name
      email: Contact email
      city: Location, city, area
      state: State, province, region
    relationships:
      - "Referenced by orders.customer_id (1:N)"
    common_queries:
      - "list customers"
      - "customers in Jakarta"

  orders:
    description: >
      Sales transactions, purchase records, order history.
    columns:
      order_id: Unique order identifier
      customer_id: Links to customers
      order_date: Purchase timestamp
      total_amount: Order value
      status: Order state
    relationships:
      - "FK to customers.customer_id"
      - "Referenced by payments.order_id"
    common_queries:
      - "sales this month"
      - "order history"

  payments:
    description: >
      Payment transactions, revenue data.
    columns:
      payment_id: Payment identifier
      order_id: Links to orders
      payment_method: Payment type
      payment_value: Actual revenue
      payment_date: Payment timestamp
    relationships:
      - "FK to orders.order_id"
    common_queries:
      - "total revenue"
      - "payments by method"

# TODO: Add products_db and analytics_db schemas
SCHEMAS

# Create environment template
cat > .env.example << 'ENVEXAMPLE'
# API Keys
ANTHROPIC_API_KEY=your_claude_api_key_here
OPENAI_API_KEY=your_openai_api_key_here

# Database URLs
SALES_DB_URL=postgresql://localhost:5432/ecommerce_sales
PRODUCTS_DB_URL=postgresql://localhost:5432/ecommerce_products
ANALYTICS_DB_URL=postgresql://localhost:5432/ecommerce_analytics

# Application Settings
DEBUG=true
LOG_LEVEL=INFO
ENVEXAMPLE

# Create requirements.txt
cat > requirements.txt << 'REQUIREMENTS'
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

# Testing
pytest==7.4.3
pytest-cov==4.1.0
requests==2.31.0

# Utils
python-json-logger==2.0.7
REQUIREMENTS

# Create README.md
cat > README.md << 'README'
# Text-to-SQL Analytics Chatbot

AI-powered chatbot for multi-database analytics using natural language.

## Quick Start

\`\`\`bash
# 1. Setup environment
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Setup databases
python scripts/setup_databases.py
python scripts/index_schemas.py

# 4. Run tests
python scripts/run_tests.py

# 5. Start services
uvicorn src.main:app --reload        # Terminal 1: API
streamlit run src/ui/app.py          # Terminal 2: UI
\`\`\`

## Documentation

- [Design Rationale](docs/01_DESIGN_RATIONALE.md)
- [Implementation Guide](docs/02_IMPLEMENTATION_GUIDE.md)
- [Test Strategy](docs/03_TEST_STRATEGY.md)
- [Quick Reference](docs/04_QUICK_REFERENCE.md)

## Architecture

Hybrid modular system with 7 components:
1. Intent Classifier (Agentic)
2. Schema Retriever (Traditional - RAG)
3. Retrieval Evaluator (Agentic)
4. SQL Generator (Agentic)
5. SQL Validator (Hybrid)
6. Query Executor (Traditional)
7. Insight Generator (Agentic)

## Project Structure

\`\`\`
src/                 # Source code
├── components/      # 7 pipeline components
├── models/          # Pydantic models
├── utils/           # Utilities
└── ui/              # Streamlit UI

scripts/             # Setup & testing
├── setup_databases.py
├── index_schemas.py
└── run_tests.py

tests/               # Test suite
config/              # Configuration files
docs/                # Documentation
\`\`\`

## Tech Stack

- **LLM:** Claude Sonnet 4
- **Vector DB:** ChromaDB
- **Database:** PostgreSQL
- **API:** FastAPI
- **UI:** Streamlit

## License

Proprietary - Technical Test Project
README

# Update .gitignore
cat >> .gitignore << 'GITIGNORE'

# Project specific
.env
chroma_db/
logs/*.log
data/raw/*.csv
*.pyc
__pycache__/
.pytest_cache/
.coverage
htmlcov/
test_results.json
GITIGNORE

echo ""
echo "✅ Project structure created successfully!"
echo ""
echo "📂 Project Structure:"
tree -L 2 -I '__pycache__|*.pyc|.git' || ls -R

echo ""
echo "🎯 Next Steps:"
echo "1. Copy .env.example to .env and add your API keys"
echo "2. Install dependencies: pip install -r requirements.txt"
echo "3. Download Olist dataset to data/raw/"
echo "4. Run: python scripts/setup_databases.py"
echo "5. Run: python scripts/index_schemas.py"
echo ""
echo "🚀 Ready to start development!"
