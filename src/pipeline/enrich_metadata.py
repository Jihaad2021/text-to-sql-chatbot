"""
Metadata Enricher — Anthropic Claude

Reads metadata.json (output from pg_metadata_extractor.py),
generates rich descriptions for schemas, tables, and columns,
then saves to metadata.yaml for ChromaDB indexing.

Usage:
    python -m src.pipeline.enrich_metadata

Flow:
    metadata.json → Claude API → metadata.yaml → ChromaDB indexer
"""

import json
import time
import os
from dotenv import load_dotenv
from anthropic import Anthropic

from src.core.config import Config

load_dotenv()

# ─────────────────────────────────────────────
# KONFIGURASI
# ─────────────────────────────────────────────

INPUT_FILE  = os.getenv("METADATA_INPUT_FILE", "metadata.json")
OUTPUT_FILE = os.getenv("METADATA_OUTPUT_FILE", "metadata.yaml")

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


# ─────────────────────────────────────────────
# PROMPT TEMPLATES
# ─────────────────────────────────────────────

SCHEMA_PROMPT = """You are a database documentation expert for a text-to-SQL retrieval system.

Write exactly ONE sentence describing this database schema.
The sentence must pack: business domain + what data it holds + what queries it answers.
Include key business synonyms a user might type (e.g. "revenue, sales, transaksi, penjualan").
Write in English. No labels, no JSON, no bullet points.

Database: {db_name}
Schema: {schema_name}
Tables: {table_list}
"""

TABLE_PROMPT = """You are a database documentation expert for a text-to-SQL retrieval system.

Write exactly TWO sentences describing this table.
Sentence 1: what real-world entity or event this table stores + its primary key + key attributes.
Sentence 2: what business questions it answers + important synonyms users might search (include Indonesian terms where natural, e.g. pelanggan, pesanan, pembayaran).
Write in English. No labels, no JSON, no bullet points.

Database: {db_name}
Schema: {schema_name}
Table: {table_name}
Columns: {column_list}
"""

COLUMN_PROMPT = """You are a database documentation expert for a text-to-SQL retrieval system.

Write exactly ONE sentence describing this column.
Pack in: what value it holds + how it is used in queries (filter/group/join/aggregate) + role (PK/FK/status/metric/timestamp if applicable) + Indonesian synonym in parentheses if relevant (e.g. saldo, status, tanggal, kota).
Write in English. No labels, no JSON, no bullet points.

Database: {db_name}
Schema: {schema_name}
Table: {table_name}
Column: {column_name}
Data type: {data_type}
Sibling columns: {sibling_columns}
"""


# ─────────────────────────────────────────────
# LLM CALLER (dengan simple retry)
# ─────────────────────────────────────────────

def call_llm(prompt: str, retries: int = 3) -> str:
    """Call Claude API with retry logic."""
    for attempt in range(retries):
        try:
            response = client.messages.create(
                model=Config.MODEL,
                max_tokens=300,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()
        except Exception as e:
            wait = 2 ** attempt
            print(f"      ⚠️  API error (attempt {attempt+1}/{retries}): {e}. Retry in {wait}s...")
            time.sleep(wait)
    return ""


# ─────────────────────────────────────────────
# YAML WRITER
# ─────────────────────────────────────────────

def block_scalar(text: str, base_indent: int) -> str:
    """Render text as YAML literal block scalar (|)."""
    pad   = " " * base_indent
    lines = text.splitlines() if text else [""]
    body  = "\n".join(pad + ln for ln in lines)
    return f"|\n{body}"


def qs(value: str) -> str:
    """Quoted YAML string."""
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def write_yaml(metadata: dict, enriched_schemas: list) -> str:
    """Write enriched metadata to YAML format compatible with ChromaDB indexer."""
    out = []

    # databases
    out.append("databases:")
    for db in metadata.get("databases", []):
        out.append(f"  - {qs(db)}")
    out.append("")

    # schemas
    out.append("schemas:")

    for schema in enriched_schemas:
        out.append(f"  - db_name: {qs(schema['db_name'])}")
        out.append(f"    schema: {qs(schema['schema'])}")
        out.append(f"    description: {block_scalar(schema['description'], 6)}")
        out.append( "    tables:")

        for table in schema["tables"]:
            out.append(f"      - table: {qs(table['table'])}")
            out.append(f"        description: {block_scalar(table['description'], 10)}")
            out.append( "        columns:")

            for col in table["columns"]:
                out.append(f"          - name: {qs(col['name'])}")
                out.append(f"            description: {block_scalar(col['description'], 14)}")
                out.append(f"            type: {qs(col['type'])}")

            # foreign_keys
            if table.get("foreign_keys"):
                out.append("        foreign_keys:")
                for fk in table["foreign_keys"]:
                    out.append(f"          - column: {qs(fk['column'])}")
                    out.append( "            references:")
                    ref = fk["references"]
                    out.append(f"              schema: {qs(ref['schema'])}")
                    out.append(f"              table:  {qs(ref['table'])}")
                    out.append(f"              column: {qs(ref['column'])}")

        out.append("")  # blank line between schemas

    return "\n".join(out)


# ─────────────────────────────────────────────
# ENRICHMENT FUNCTIONS
# ─────────────────────────────────────────────

def enrich_column(
    db_name: str,
    schema_name: str,
    table_name: str,
    column: dict,
    sibling_names: list
) -> dict:
    """Generate description for a single column."""
    siblings = ", ".join(c for c in sibling_names if c != column["name"])
    prompt   = COLUMN_PROMPT.format(
        db_name=db_name,
        schema_name=schema_name,
        table_name=table_name,
        column_name=column["name"],
        data_type=column["type"],
        sibling_columns=siblings or "-",
    )
    return {**column, "description": call_llm(prompt)}


def enrich_table(db_name: str, schema_name: str, table: dict) -> dict:
    """Generate description for a table and all its columns."""
    col_names   = [c["name"] for c in table["columns"]]
    col_summary = ", ".join(f"{c['name']} ({c['type']})" for c in table["columns"])

    table_desc = call_llm(TABLE_PROMPT.format(
        db_name=db_name,
        schema_name=schema_name,
        table_name=table["table"],
        column_list=col_summary or "-",
    ))

    enriched_cols = []
    for col in table["columns"]:
        print(f"            column: {col['name']}")
        enriched_cols.append(
            enrich_column(db_name, schema_name, table["table"], col, col_names)
        )
        time.sleep(0.3)  # rate-limit buffer

    return {**table, "description": table_desc, "columns": enriched_cols}


def enrich_schema(schema: dict) -> dict:
    """Generate description for a schema and all its tables."""
    db_name     = schema.get("db_name", "")
    schema_name = schema["schema"]
    table_names = ", ".join(t["table"] for t in schema["tables"])

    schema_desc = call_llm(SCHEMA_PROMPT.format(
        db_name=db_name,
        schema_name=schema_name,
        table_list=table_names or "-",
    ))

    enriched_tables = []
    for table in schema["tables"]:
        print(f"        table: {table['table']}")
        enriched_tables.append(enrich_table(db_name, schema_name, table))

    return {**schema, "description": schema_desc, "tables": enriched_tables}


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print(f"📂 Reading {INPUT_FILE}...")
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        metadata = json.load(f)

    total_schemas = len(metadata.get("schemas", []))
    total_tables  = sum(len(s["tables"]) for s in metadata.get("schemas", []))
    total_columns = sum(
        len(t["columns"])
        for s in metadata.get("schemas", [])
        for t in s["tables"]
    )

    print(f"📊 Target        : {total_schemas} schema(s) | {total_tables} table(s) | {total_columns} column(s)")
    print(f"🔁 Est. API calls: {total_schemas + total_tables + total_columns}")
    print(f"🤖 Model         : {Config.MODEL}\n")

    enriched_schemas = []
    for i, schema in enumerate(metadata.get("schemas", []), 1):
        print(f"  [{i}/{total_schemas}] DB: {schema.get('db_name', '')} | Schema: {schema['schema']}")
        enriched_schemas.append(enrich_schema(schema))

    yaml_out = write_yaml(metadata, enriched_schemas)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(yaml_out)

    print(f"\n✅ Done! Output saved to: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
