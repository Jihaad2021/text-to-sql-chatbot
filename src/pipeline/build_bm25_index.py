"""
BM25 Index Builder

Reads enriched metadata.yaml and builds a BM25 index
for keyword-based table retrieval.

BM25 is good for exact keyword matching:
- Column names (e.g. "payment_value", "customer_id")
- Indonesian terms (e.g. "saldo", "pelanggan", "pembayaran")
- Technical terms that semantic search might miss

This is Step 4 of the schema pipeline:
    pg_metadata_extractor.py → enrich_metadata.py → index_schemas.py
    → build_bm25_index.py (this file)
    → build_graph.py

Usage:
    python -m src.pipeline.build_bm25_index

Output:
    data/bm25_index.pkl — BM25 index + corpus metadata
"""

import os
import pickle
import yaml
from typing import List, Dict, Any
from rank_bm25 import BM25Okapi


METADATA_FILE = os.getenv("METADATA_YAML_FILE", "data/schemas/metadata.yaml")
OUTPUT_FILE   = os.getenv("BM25_INDEX_FILE", "data/bm25_index.pkl")


# ─────────────────────────────────────────────
# TEXT BUILDER
# ─────────────────────────────────────────────

def build_corpus_text(db_name: str, schema_name: str, table: dict) -> str:
    """
    Build text corpus for a single table.

    Combines: table name + description + column names + column descriptions + FK info
    This text will be tokenized and indexed by BM25.
    """
    parts = []

    # Table identity
    parts.append(table["table"])
    parts.append(db_name)
    parts.append(schema_name)

    # Table description
    if table.get("description"):
        parts.append(table["description"].strip())

    # Column names and descriptions
    for col in table.get("columns", []):
        parts.append(col["name"])
        if col.get("description"):
            parts.append(col["description"].strip())

    # FK relationships
    for fk in table.get("foreign_keys", []):
        ref = fk.get("references", {})
        parts.append(fk.get("column", ""))
        parts.append(ref.get("table", ""))
        parts.append(ref.get("column", ""))

    return " ".join(parts)


def tokenize(text: str) -> List[str]:
    """
    Simple tokenizer — split by whitespace and special chars.
    Lowercases all tokens.
    """
    import re
    tokens = re.findall(r'[a-zA-Z0-9]+', text.lower())
    return tokens


# ─────────────────────────────────────────────
# BUILD INDEX
# ─────────────────────────────────────────────

def build_bm25_index(metadata: dict) -> tuple:
    """
    Build BM25 index from metadata.

    Returns:
        Tuple of (bm25_index, corpus_metadata)
        corpus_metadata: list of dicts with table info per document
    """
    corpus_texts = []
    corpus_metadata = []

    for schema in metadata.get("schemas", []):
        db_name     = schema.get("db_name", "")
        schema_name = schema.get("schema", "public")

        for table in schema.get("tables", []):
            text = build_corpus_text(db_name, schema_name, table)
            tokens = tokenize(text)

            corpus_texts.append(tokens)
            corpus_metadata.append({
                "db_name": db_name,
                "schema_name": schema_name,
                "table_name": table["table"],
                "description": table.get("description", "").strip(),
                "columns": [col["name"] for col in table.get("columns", [])],
                "relationships": [
                    f"{fk['column']} → {fk['references']['schema']}.{fk['references']['table']}.{fk['references']['column']}"
                    for fk in table.get("foreign_keys", [])
                    if fk.get("references")
                ],
                "full_name": f"{db_name}.{schema_name}.{table['table']}"
            })

            print(f"  ✓ {db_name}.{table['table']} ({len(tokens)} tokens)")

    # Build BM25 index
    bm25 = BM25Okapi(corpus_texts)

    return bm25, corpus_metadata


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("BM25 INDEX BUILDER")
    print("="*60)

    # Load metadata
    print(f"\n[1/3] Loading metadata from {METADATA_FILE}...")
    if not os.path.exists(METADATA_FILE):
        raise FileNotFoundError(f"Metadata file not found: {METADATA_FILE}")

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata = yaml.safe_load(f)

    total_tables = sum(len(s.get("tables", [])) for s in metadata.get("schemas", []))
    print(f"  Found {len(metadata.get('schemas', []))} schema(s), {total_tables} table(s)")

    # Build index
    print(f"\n[2/3] Building BM25 index...")
    bm25, corpus_metadata = build_bm25_index(metadata)

    # Save
    print(f"\n[3/3] Saving index to {OUTPUT_FILE}...")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, "wb") as f:
        pickle.dump({
            "bm25": bm25,
            "corpus": corpus_metadata
        }, f)

    print(f"\n{'='*60}")
    print(f"✅ Done! BM25 index saved to: {OUTPUT_FILE}")
    print(f"   Tables indexed: {len(corpus_metadata)}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()