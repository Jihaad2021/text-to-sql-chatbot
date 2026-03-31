"""
Schema Indexer

Reads enriched metadata.yaml and indexes all table schemas
into ChromaDB for semantic search (RAG).

This is Step 3 of the schema pipeline:
    pg_metadata_extractor.py → enrich_metadata.py → index_schemas.py

Usage:
    python -m src.pipeline.index_schemas

Flow:
    data/schemas/metadata.yaml → ChromaDB (table_schemas collection)
"""

import os
import yaml
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv

load_dotenv()

METADATA_FILE  = os.getenv("METADATA_YAML_FILE", "data/schemas/metadata.yaml")
CHROMA_PATH    = os.getenv("CHROMA_PATH", "./chroma_db")
COLLECTION_NAME = "table_schemas"


def load_metadata(filepath: str) -> dict:
    """Load enriched metadata from YAML file."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Metadata file not found: {filepath}")

    with open(filepath, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def init_chromadb(chroma_path: str, openai_key: str):
    """Initialize ChromaDB client and create fresh collection."""
    os.makedirs(chroma_path, exist_ok=True)

    client = chromadb.PersistentClient(path=chroma_path)

    embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
        api_key=openai_key,
        model_name="text-embedding-3-small"
    )

    # Delete existing collection for clean re-indexing
    try:
        client.delete_collection(COLLECTION_NAME)
        print(f"  Deleted existing collection: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_fn,
        metadata={"description": "Table schemas for Text-to-SQL retrieval"}
    )
    print(f"  Created collection: {COLLECTION_NAME}")

    return collection


def build_document(db_name: str, schema_name: str, table: dict) -> str:
    """
    Build rich text document for embedding.

    Combines table description + column descriptions + FK info
    into a single text for ChromaDB indexing.
    """
    lines = []

    # Table context
    lines.append(f"Table: {table['table']} in {db_name}.{schema_name}")
    lines.append(f"Description: {table.get('description', '').strip()}")

    # Column descriptions
    if table.get("columns"):
        lines.append("Columns:")
        for col in table["columns"]:
            col_desc = col.get("description", "").strip()
            lines.append(f"- {col['name']} ({col['type']}): {col_desc}")

    # Foreign keys
    if table.get("foreign_keys"):
        lines.append("Relationships:")
        for fk in table["foreign_keys"]:
            ref = fk["references"]
            lines.append(
                f"- {fk['column']} → {ref['schema']}.{ref['table']}.{ref['column']}"
            )

    return "\n".join(lines)


def build_metadata(db_name: str, schema_name: str, table: dict) -> dict:
    """
    Build metadata dict stored alongside the document in ChromaDB.
    Used for filtering and returning structured info to the pipeline.
    """
    columns = [col["name"] for col in table.get("columns", [])]

    relationships = []
    for fk in table.get("foreign_keys", []):
        ref = fk["references"]
        relationships.append(
            f"{fk['column']} → {ref['schema']}.{ref['table']}.{ref['column']}"
        )

    return {
        "db_name": db_name,
        "schema_name": schema_name,
        "table_name": table["table"],
        "description": table.get("description", "").strip(),
        "columns": ", ".join(columns),
        "relationships": "; ".join(relationships) if relationships else ""
    }


def index_metadata(metadata: dict, collection) -> int:
    """Index all tables from metadata into ChromaDB."""
    documents = []
    metadatas = []
    ids = []

    for schema in metadata.get("schemas", []):
        db_name     = schema.get("db_name", "")
        schema_name = schema.get("schema", "public")

        for table in schema.get("tables", []):
            doc_id   = f"{db_name}.{schema_name}.{table['table']}"
            document = build_document(db_name, schema_name, table)
            meta     = build_metadata(db_name, schema_name, table)

            documents.append(document)
            metadatas.append(meta)
            ids.append(doc_id)

            print(f"    ✓ {doc_id}")

    print(f"\n  Generating embeddings for {len(documents)} tables...")
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    return len(documents)


def verify(collection) -> None:
    """Verify indexing with sample queries."""
    print("\n  Running verification queries...")

    test_queries = [
        "customer information",
        "revenue and payments",
        "product catalog"
    ]

    for query in test_queries:
        results = collection.query(query_texts=[query], n_results=3)
        top = results["ids"][0][0] if results["ids"][0] else "none"
        score = 1 - results["distances"][0][0] if results["distances"][0] else 0
        print(f"    '{query}' → {top} (score: {score:.3f})")


def main():
    print("\n" + "="*60)
    print("SCHEMA INDEXER")
    print("="*60)

    # Check OpenAI key
    openai_key = os.getenv("OPENAI_API_KEY")
    if not openai_key:
        raise ValueError("OPENAI_API_KEY not found in .env")

    # Step 1: Load metadata
    print(f"\n[1/3] Loading metadata from {METADATA_FILE}...")
    metadata = load_metadata(METADATA_FILE)
    total_schemas = len(metadata.get("schemas", []))
    total_tables  = sum(len(s.get("tables", [])) for s in metadata.get("schemas", []))
    print(f"  Found {total_schemas} schema(s), {total_tables} table(s)")

    # Step 2: Init ChromaDB
    print(f"\n[2/3] Initializing ChromaDB at {CHROMA_PATH}...")
    collection = init_chromadb(CHROMA_PATH, openai_key)

    # Step 3: Index
    print(f"\n[3/3] Indexing tables...")
    total_indexed = index_metadata(metadata, collection)

    # Verify
    verify(collection)

    print(f"\n{'='*60}")
    print(f"✅ Done! {total_indexed} tables indexed into ChromaDB.")
    print(f"   Collection : {COLLECTION_NAME}")
    print(f"   Location   : {CHROMA_PATH}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()