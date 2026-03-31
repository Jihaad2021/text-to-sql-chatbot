"""
PostgreSQL Metadata Extractor

Extracts database structure (schemas, tables, columns, foreign keys)
from all configured databases using Config.DB_URLS.

Output: metadata.json — used as input for enrich_metadata.py

Usage:
    python -m src.pipeline.pg_metadata_extractor

Output format:
    {
        "databases": ["sales_db", "products_db", "analytics_db"],
        "schemas": [
            {
                "db_name": "sales_db",
                "schema": "public",
                "tables": [
                    {
                        "table": "customers",
                        "columns": [...],
                        "foreign_keys": [...]
                    }
                ]
            }
        ]
    }
"""

import json
import os
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

from src.core.config import Config

load_dotenv()

OUTPUT_FILE = os.getenv("METADATA_OUTPUT_FILE", "metadata.json")


def parse_db_url(db_url: str) -> dict:
    """
    Parse SQLAlchemy-style DB URL into psycopg2 connection config.

    Example:
        postgresql://macbook@localhost:5432/ecommerce_sales
        → {"host": "localhost", "port": 5432, "dbname": "ecommerce_sales", ...}
    """
    parsed = urlparse(db_url)
    return {
        "host": parsed.hostname,
        "port": parsed.port or 5432,
        "dbname": parsed.path.lstrip("/"),
        "user": parsed.username,
        "password": parsed.password or ""
    }


def extract_schemas(cur, db_name: str) -> list:
    """Extract all non-system schemas from a database."""
    cur.execute("""
        SELECT schema_name
        FROM information_schema.schemata
        WHERE schema_name NOT IN (
            'pg_catalog', 'information_schema', 'pg_toast'
        );
    """)
    return [row["schema_name"] for row in cur.fetchall()]


def extract_tables(cur, schema: str) -> list:
    """Extract all base tables in a schema."""
    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_type = 'BASE TABLE';
    """, (schema,))
    return [row["table_name"] for row in cur.fetchall()]


def extract_columns(cur, schema: str, table: str) -> list:
    """Extract all columns for a table."""
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name = %s
        ORDER BY ordinal_position;
    """, (schema, table))
    return [
        {"name": col["column_name"], "type": col["data_type"]}
        for col in cur.fetchall()
    ]


def extract_foreign_keys(cur, schema: str, table: str) -> list:
    """Extract all foreign keys for a table."""
    cur.execute("""
        SELECT
            kcu.column_name,
            ccu.table_schema AS foreign_schema,
            ccu.table_name   AS foreign_table,
            ccu.column_name  AS foreign_column
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name
         AND tc.table_schema    = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name
         AND tc.table_schema    = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema    = %s
          AND tc.table_name      = %s;
    """, (schema, table))
    return [
        {
            "column": fk["column_name"],
            "references": {
                "schema": fk["foreign_schema"],
                "table": fk["foreign_table"],
                "column": fk["foreign_column"]
            }
        }
        for fk in cur.fetchall()
    ]


def extract_from_database(db_name: str, db_url: str) -> list:
    """
    Extract all schemas, tables, columns, and FKs from one database.

    Returns list of schema objects with db_name attached.
    """
    print(f"\n  Connecting to {db_name}...")
    conn_config = parse_db_url(db_url)
    conn = psycopg2.connect(**conn_config)
    schemas_data = []

    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        schemas = extract_schemas(cur, db_name)
        print(f"  Found {len(schemas)} schema(s): {schemas}")

        for schema in schemas:
            print(f"    Schema: {schema}")
            schema_obj = {
                "db_name": db_name,
                "schema": schema,
                "tables": []
            }

            tables = extract_tables(cur, schema)
            print(f"    Found {len(tables)} table(s)")

            for table in tables:
                print(f"      Table: {table}")
                table_obj = {
                    "table": table,
                    "columns": extract_columns(cur, schema, table),
                    "foreign_keys": extract_foreign_keys(cur, schema, table)
                }
                schema_obj["tables"].append(table_obj)

            schemas_data.append(schema_obj)

    conn.close()
    return schemas_data


def extract_metadata() -> dict:
    """
    Extract metadata from all databases in Config.DB_URLS.

    Returns:
        metadata dict with databases list and schemas list
    """
    metadata = {
        "databases": [],
        "schemas": []
    }

    db_urls = {
        db_name: url
        for db_name, url in Config.DB_URLS.items()
        if url  # skip if URL not set
    }

    print(f"Found {len(db_urls)} database(s): {list(db_urls.keys())}")

    for db_name, db_url in db_urls.items():
        metadata["databases"].append(db_name)
        schemas = extract_from_database(db_name, db_url)
        metadata["schemas"].extend(schemas)

    return metadata


if __name__ == "__main__":
    print("Starting metadata extraction...")
    print(f"Databases: {list(Config.DB_URLS.keys())}\n")

    result = extract_metadata()

    total_schemas = len(result["schemas"])
    total_tables = sum(len(s["tables"]) for s in result["schemas"])
    total_columns = sum(
        len(t["columns"])
        for s in result["schemas"]
        for t in s["tables"]
    )

    print(f"\nExtraction complete:")
    print(f"  Databases : {len(result['databases'])}")
    print(f"  Schemas   : {total_schemas}")
    print(f"  Tables    : {total_tables}")
    print(f"  Columns   : {total_columns}")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Output saved to: {OUTPUT_FILE}")