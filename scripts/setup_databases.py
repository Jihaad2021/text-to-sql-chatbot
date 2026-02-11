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
