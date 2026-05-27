"""
Load Financial Data to PostgreSQL

Creates the 'financial_db' database and loads all CSV files from raw/.
Run once after adding FINANCIAL_DB_URL to .env.

Usage:
    python scripts/load_financial_data.py
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, text

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

load_dotenv()

RAW_DIR = Path(__file__).parent.parent / "data" / "raw"
DB_URL = os.getenv("FINANCIAL_DB_URL", "postgresql://galaxymacbook@localhost:5432/financial_db")

# ── Table DDL ─────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS financial_internal (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    payment_provider    TEXT,
    transaction_type    TEXT,
    item_type           TEXT,
    total_trx           BIGINT,
    total_net_revenue   DOUBLE PRECISION,
    net_gap             DOUBLE PRECISION,
    total_platform_fee  DOUBLE PRECISION,
    total_admin_fee     DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS daily_master (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    partner         TEXT,
    total_trx       BIGINT,
    success_trx     DOUBLE PRECISION,
    failed_trx      DOUBLE PRECISION,
    total_revenue   DOUBLE PRECISION,
    success_rate_pct DOUBLE PRECISION,
    unique_users    BIGINT
);

CREATE TABLE IF NOT EXISTS daily_product_channel (
    id          SERIAL PRIMARY KEY,
    date        DATE NOT NULL,
    product_name TEXT,
    a0_trx      BIGINT,
    a0_revenue  DOUBLE PRECISION,
    b3_trx      BIGINT,
    b3_revenue  DOUBLE PRECISION,
    f0_trx      BIGINT,
    f0_revenue  DOUBLE PRECISION,
    f4_trx      BIGINT,
    f4_revenue  DOUBLE PRECISION,
    f5_trx      BIGINT,
    f5_revenue  DOUBLE PRECISION,
    i1_trx      BIGINT,
    i1_revenue  DOUBLE PRECISION,
    ig_trx      BIGINT,
    ig_revenue  DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS channel_payment (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    partner         TEXT,
    channel         TEXT,
    purchase_mode   TEXT,
    total_trx       BIGINT,
    total_revenue   DOUBLE PRECISION,
    success_rate_pct DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS product_price_list (
    id              SERIAL PRIMARY KEY,
    product_id      TEXT UNIQUE,
    product_name    TEXT,
    price           DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS anomalies (
    id                  SERIAL PRIMARY KEY,
    date                DATE,
    check_type          TEXT,
    status              TEXT,
    entity_type         TEXT,
    entity_id           TEXT,
    anomaly_type        TEXT,
    severity            TEXT,
    total_trx           DOUBLE PRECISION,
    total_revenue       DOUBLE PRECISION,
    avg_revenue         DOUBLE PRECISION,
    zscore              DOUBLE PRECISION,
    threshold_value     DOUBLE PRECISION,
    actual_value        DOUBLE PRECISION,
    expected_value      DOUBLE PRECISION,
    deviation_pct       DOUBLE PRECISION,
    description         TEXT,
    recommended_action  TEXT,
    impact_estimate     DOUBLE PRECISION,
    payment_provider    TEXT,
    partner             TEXT,
    product_name        TEXT,
    service_code        TEXT,
    first_detected      DATE,
    last_detected       DATE,
    frequency_days      INTEGER
);

CREATE TABLE IF NOT EXISTS daily_unique_users (
    id                  SERIAL PRIMARY KEY,
    date                DATE NOT NULL,
    unique_users        BIGINT,
    daily_unique_users  BIGINT
);

CREATE TABLE IF NOT EXISTS daily_user_partner (
    id          SERIAL PRIMARY KEY,
    date        DATE NOT NULL,
    partner     TEXT,
    unique_users BIGINT
);

CREATE TABLE IF NOT EXISTS hourly_pattern_daily (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    hour            INTEGER,
    total_trx       BIGINT,
    success_rate_pct DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS product_summary (
    id              SERIAL PRIMARY KEY,
    date            DATE NOT NULL,
    product_id      TEXT,
    product_name    TEXT,
    item_type       TEXT,
    type_of_payment TEXT,
    payment_provider TEXT,
    total_trx       BIGINT,
    total_revenue   DOUBLE PRECISION,
    success_trx     DOUBLE PRECISION,
    success_rate_pct DOUBLE PRECISION,
    unique_buyers   BIGINT,
    repeat_buyers   BIGINT,
    settlement_gap  DOUBLE PRECISION
);
"""

# ── CSV → table mapping ────────────────────────────────────────────────────────

CSV_TABLE_MAP = [
    ("financial_internal.csv",   "financial_internal"),
    ("daily_master.csv",         "daily_master"),
    ("daily_product_channel.csv","daily_product_channel"),
    ("channel_payment.csv",      "channel_payment"),
    ("product_price_list.csv",   "product_price_list"),
    ("anomalies.csv",            "anomalies"),
    ("daily_unique_users.csv",   "daily_unique_users"),
    ("daily_user_partner.csv",   "daily_user_partner"),
    ("hourly_pattern_daily.csv", "hourly_pattern_daily"),
    ("product_summary.csv",      "product_summary"),
]


def create_database(db_url: str) -> None:
    """Create the database if it doesn't exist."""
    parsed = urlparse(db_url)
    db_name = parsed.path.lstrip("/")
    admin_url = db_url.replace(f"/{db_name}", "/postgres")

    parsed_admin = urlparse(admin_url)
    conn = psycopg2.connect(
        host=parsed_admin.hostname,
        port=parsed_admin.port or 5432,
        dbname="postgres",
        user=parsed_admin.username,
        password=parsed_admin.password or "",
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db_name,))
        if cur.fetchone():
            print(f"  Database '{db_name}' already exists, skipping creation.")
        else:
            cur.execute(f'CREATE DATABASE "{db_name}"')  # nosec B608
            print(f"  Database '{db_name}' created.")

    conn.close()


def create_tables(engine) -> None:
    """Create all tables via DDL."""
    with engine.begin() as conn:
        conn.execute(text(DDL))
    print("  Tables created.")


def load_csv(engine, csv_file: str, table: str) -> None:
    """Load a single CSV file into a table."""
    path = RAW_DIR / csv_file
    if not path.exists():
        print(f"  [SKIP] {csv_file} not found.")
        return

    df = pd.read_csv(path)

    # Normalize date columns
    for col in df.columns:
        if "date" in col.lower() and df[col].dtype == object:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # product_price_list: drop nulls and duplicates on product_id before upsert
    if table == "product_price_list":
        df = df.dropna(subset=["product_id"])
        df = df.drop_duplicates(subset=["product_id"], keep="last")
        with engine.begin() as conn:
            df.to_sql("_tmp_price", conn, if_exists="replace", index=False)
            conn.execute(text("""
                INSERT INTO product_price_list (product_id, product_name, price)
                SELECT product_id::TEXT, product_name, price FROM _tmp_price
                ON CONFLICT (product_id) DO UPDATE
                    SET product_name = EXCLUDED.product_name,
                        price        = EXCLUDED.price;
                DROP TABLE IF EXISTS _tmp_price;
            """))
        print(f"  {table}: {len(df):,} rows upserted.")
        return

    # Drop auto-generated 'id' column from CSV if present
    if "id" in df.columns:
        df = df.drop(columns=["id"])

    df.to_sql(table, engine, if_exists="append", index=False, chunksize=5000, method="multi")
    print(f"  {table}: {len(df):,} rows loaded.")


def main() -> None:
    print("=== Financial Data Loader ===\n")
    print(f"Target DB: {DB_URL}\n")

    print("[1/3] Creating database...")
    create_database(DB_URL)

    engine = create_engine(DB_URL)

    print("\n[2/3] Creating tables...")
    create_tables(engine)

    print("\n[3/3] Loading CSV files...")
    for csv_file, table in CSV_TABLE_MAP:
        load_csv(engine, csv_file, table)

    engine.dispose()
    print("\n✅ Done! All data loaded into financial_db.")
    print("\nNext steps:")
    print("  1. python scripts/pg_metadata_extractor.py")
    print("  2. python scripts/index_schemas.py")
    print("  3. python scripts/build_bm25_index.py")
    print("  4. python scripts/build_graph.py")


if __name__ == "__main__":
    main()
