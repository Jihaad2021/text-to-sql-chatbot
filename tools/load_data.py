"""
Database Loader

Loads CSV data from data/raw/ into PostgreSQL databases.
Run this script after setting up PostgreSQL databases.

Usage:
    python tools/load_data.py

Requirements:
    - PostgreSQL running
    - .env configured with DB URLs
    - data/raw/ contains all 8 CSV files
"""

import os
import pandas as pd
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────

RAW_DATA_DIR = "data/raw"

DB_URLS = {
    "sales_db": os.getenv("SALES_DB_URL"),
    "products_db": os.getenv("PRODUCTS_DB_URL"),
    "analytics_db": os.getenv("ANALYTICS_DB_URL")
}

# Mapping: database → list of (csv_file, table_name)
DB_TABLES = {
    "sales_db": [
        ("customers.csv", "customers"),
        ("orders.csv", "orders"),
        ("payments.csv", "payments"),
    ],
    "products_db": [
        ("products.csv", "products"),
        ("sellers.csv", "sellers"),
        ("order_items.csv", "order_items"),
    ],
    "analytics_db": [
        ("customer_segments.csv", "customer_segments"),
        ("daily_metrics.csv", "daily_metrics"),
    ]
}


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def check_csv_files() -> bool:
    """Check all required CSV files exist."""
    print("\n[1/4] Checking CSV files...")
    all_exist = True

    for db_name, tables in DB_TABLES.items():
        for csv_file, _ in tables:
            filepath = os.path.join(RAW_DATA_DIR, csv_file)
            if os.path.exists(filepath):
                print(f"  ✓ {csv_file}")
            else:
                print(f"  ✗ {csv_file} NOT FOUND")
                all_exist = False

    return all_exist


def check_db_connections() -> bool:
    """Check all database connections."""
    print("\n[2/4] Checking database connections...")
    all_connected = True

    for db_name, url in DB_URLS.items():
        if not url:
            print(f"  ✗ {db_name}: URL not set in .env")
            all_connected = False
            continue

        try:
            engine = create_engine(url)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"  ✓ {db_name}: Connected")
            engine.dispose()
        except Exception as e:
            print(f"  ✗ {db_name}: {str(e)}")
            all_connected = False

    return all_connected


def load_csv_to_db(csv_file: str, table_name: str, db_url: str, db_name: str):
    """Load a single CSV file into a database table."""
    filepath = os.path.join(RAW_DATA_DIR, csv_file)

    # Read CSV
    df = pd.read_csv(filepath)
    print(f"    → {csv_file}: {len(df)} rows, {len(df.columns)} columns")

    # Load to PostgreSQL
    engine = create_engine(db_url)
    df.to_sql(
        name=table_name,
        con=engine,
        if_exists="replace",  # replace if exists
        index=False,
        method="multi",       # faster batch insert
        chunksize=1000
    )
    engine.dispose()
    print(f"    ✓ Loaded into {db_name}.{table_name}")


def add_constraints(db_name: str, db_url: str):
    """Add PK and FK constraints after data is loaded."""
    engine = create_engine(db_url)

    constraints = {
        "sales_db": [
            "ALTER TABLE customers ADD CONSTRAINT pk_customers PRIMARY KEY (customer_id);",
            "ALTER TABLE orders ADD CONSTRAINT pk_orders PRIMARY KEY (order_id);",
            "ALTER TABLE payments ADD CONSTRAINT pk_payments PRIMARY KEY (payment_id);",
            "ALTER TABLE orders ADD CONSTRAINT fk_orders_customer FOREIGN KEY (customer_id) REFERENCES customers (customer_id);",
            "ALTER TABLE payments ADD CONSTRAINT fk_payments_order FOREIGN KEY (order_id) REFERENCES orders (order_id);"
        ],
        "products_db": [
            "ALTER TABLE products ADD CONSTRAINT pk_products PRIMARY KEY (product_id);",
            "ALTER TABLE sellers ADD CONSTRAINT pk_sellers PRIMARY KEY (seller_id);",
            "ALTER TABLE order_items ADD CONSTRAINT pk_order_items PRIMARY KEY (order_id, order_item_id);",
            "ALTER TABLE order_items ADD CONSTRAINT fk_order_items_product FOREIGN KEY (product_id) REFERENCES products (product_id);",
            "ALTER TABLE order_items ADD CONSTRAINT fk_order_items_seller FOREIGN KEY (seller_id) REFERENCES sellers (seller_id);"
        ],
        "analytics_db": []
    }

    sqls = constraints.get(db_name, [])
    if not sqls:
        return

    with engine.connect() as conn:
        for sql in sqls:
            try:
                conn.execute(text(sql))
                conn.commit()
                print(f"    ✓ {sql[:60]}...")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print(f"    ⚠ Already exists, skipping")
                else:
                    print(f"    ✗ Failed: {str(e)}")

    engine.dispose()


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("=" * 60)
    print("DATABASE LOADER")
    print("=" * 60)

    # Step 1: Check CSV files
    if not check_csv_files():
        print("\n✗ Some CSV files missing. Please check data/raw/ folder.")
        return

    # Step 2: Check DB connections
    if not check_db_connections():
        print("\n✗ Some databases not reachable. Please check .env and PostgreSQL.")
        return

    # Step 3: Load data
    print("\n[3/4] Loading data...")
    for db_name, tables in DB_TABLES.items():
        db_url = DB_URLS[db_name]
        print(f"\n  {db_name}:")
        for csv_file, table_name in tables:
            try:
                load_csv_to_db(csv_file, table_name, db_url, db_name)
            except Exception as e:
                print(f"    ✗ Failed to load {csv_file}: {str(e)}")

    # Step 4: Add constraints
    print("\n[4/4] Adding PK & FK constraints...")
    for db_name, db_url in DB_URLS.items():
        if db_url:
            print(f"\n  {db_name}:")
            add_constraints(db_name, db_url)

    print("\n" + "=" * 60)
    print("✅ Done! All data loaded successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()