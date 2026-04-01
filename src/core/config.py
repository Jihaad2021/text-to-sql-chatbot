"""
Centralized Configuration
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # LLM
    MODEL = os.getenv("LLM_MODEL", None)
    MAX_TOKENS = 1000

    # Query Executor
    TIMEOUT_SECONDS = 30
    MAX_ROWS = 10000

    # Schema Retriever
    CHROMA_PATH = "./chroma_db"
    TOP_K_RETRIEVAL = 5

    # SQL Validator
    ENABLE_AI_VALIDATION = False

    # Databases
    ALLOWED_TABLES = {
        'customers', 'orders', 'payments',
        'products', 'sellers', 'order_items',
        'customer_segments', 'daily_metrics'
    }

    DANGEROUS_KEYWORDS = {
        'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE',
        'INSERT', 'UPDATE', 'GRANT', 'REVOKE', 'EXECUTE',
        'PROCEDURE', 'FUNCTION'
    }

    DB_URLS = {
        'sales_db': os.getenv('SALES_DB_URL'),
        'products_db': os.getenv('PRODUCTS_DB_URL'),
        'analytics_db': os.getenv('ANALYTICS_DB_URL')
    }