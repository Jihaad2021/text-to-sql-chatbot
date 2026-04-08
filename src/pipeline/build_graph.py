"""
Graph Index Builder

Reads enriched metadata.yaml and builds a NetworkX graph
representing the relationships between databases, schemas,
tables, and columns (including FK relationships).

Graph is useful for:
- Finding JOIN paths between tables
- Navigating database hierarchy (DB → Schema → Table → Column)
- Discovering related tables via FK relationships

This is Step 5 of the schema pipeline:
    pg_metadata_extractor.py → enrich_metadata.py → index_schemas.py
    → build_bm25_index.py → build_graph.py (this file)

Usage:
    python -m src.pipeline.build_graph

Output:
    data/schema_graph.json — NetworkX graph serialized as JSON
"""

import os
import json
import yaml
import networkx as nx
from typing import Dict, Any

METADATA_FILE = os.getenv("METADATA_YAML_FILE", "data/schemas/metadata.yaml")
OUTPUT_FILE   = os.getenv("GRAPH_INDEX_FILE", "data/schema_graph.json")


# ─────────────────────────────────────────────
# GRAPH BUILDER
# ─────────────────────────────────────────────

def build_graph(metadata: dict) -> nx.DiGraph:
    """
    Build a directed graph from metadata.

    Node types:
    - database: e.g. "sales_db"
    - schema:   e.g. "sales_db.public"
    - table:    e.g. "sales_db.public.customers"
    - column:   e.g. "sales_db.public.customers.customer_id"

    Edge types:
    - contains: database → schema → table → column
    - fk:       column → column (foreign key relationship)
    - joins_with: table → table (inferred from FK)
    """
    G = nx.DiGraph()

    for schema in metadata.get("schemas", []):
        db_name     = schema.get("db_name", "")
        schema_name = schema.get("schema", "public")

        # Node IDs
        db_node     = db_name
        schema_node = f"{db_name}.{schema_name}"

        # Add database node
        if not G.has_node(db_node):
            G.add_node(db_node, type="database", name=db_name)

        # Add schema node
        G.add_node(schema_node, type="schema", name=schema_name, db=db_name)
        G.add_edge(db_node, schema_node, type="contains")

        for table in schema.get("tables", []):
            table_name = table["table"]
            table_node = f"{db_name}.{schema_name}.{table_name}"

            # Add table node
            G.add_node(
                table_node,
                type="table",
                name=table_name,
                db=db_name,
                schema=schema_name,
                description=table.get("description", "").strip(),
                columns=[col["name"] for col in table.get("columns", [])]
            )
            G.add_edge(schema_node, table_node, type="contains")

            # Add column nodes
            for col in table.get("columns", []):
                col_node = f"{table_node}.{col['name']}"
                G.add_node(
                    col_node,
                    type="column",
                    name=col["name"],
                    data_type=col.get("type", ""),
                    description=col.get("description", "").strip(),
                    table=table_name,
                    db=db_name,
                    schema=schema_name
                )
                G.add_edge(table_node, col_node, type="contains")

            # Add FK edges
            for fk in table.get("foreign_keys", []):
                ref = fk.get("references", {})
                if not ref:
                    continue

                src_col_node = f"{table_node}.{fk['column']}"
                ref_table_node = f"{db_name}.{ref['schema']}.{ref['table']}"
                ref_col_node = f"{ref_table_node}.{ref['column']}"

                # FK edge between columns
                if G.has_node(src_col_node) and G.has_node(ref_col_node):
                    G.add_edge(
                        src_col_node,
                        ref_col_node,
                        type="fk",
                        from_table=table_name,
                        to_table=ref["table"]
                    )

                # joins_with edge between tables (for quick lookup)
                if G.has_node(table_node) and G.has_node(ref_table_node):
                    G.add_edge(
                        table_node,
                        ref_table_node,
                        type="joins_with",
                        via=f"{fk['column']} → {ref['column']}"
                    )

            print(f"  ✓ {db_name}.{table_name} "
                  f"({len(table.get('columns', []))} columns, "
                  f"{len(table.get('foreign_keys', []))} FKs)")

    return G


def get_join_path(G: nx.DiGraph, table_a: str, table_b: str) -> list:
    """
    Find shortest join path between two tables.

    Args:
        G: Schema graph
        table_a: Full table node ID (e.g. 'sales_db.public.orders')
        table_b: Full table node ID (e.g. 'sales_db.public.customers')

    Returns:
        List of table node IDs representing the join path
    """
    try:
        path = nx.shortest_path(G, table_a, table_b)
        return [n for n in path if G.nodes[n].get("type") == "table"]
    except (nx.NetworkXNoPath, nx.NodeNotFound):
        return []


# ─────────────────────────────────────────────
# SERIALIZATION
# ─────────────────────────────────────────────

def graph_to_json(G: nx.DiGraph) -> dict:
    """Serialize NetworkX graph to JSON-compatible dict."""
    return nx.node_link_data(G)


def graph_from_json(data: dict) -> nx.DiGraph:
    """Deserialize NetworkX graph from JSON dict."""
    return nx.node_link_graph(data, directed=True)


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    print("\n" + "="*60)
    print("GRAPH INDEX BUILDER")
    print("="*60)

    # Load metadata
    print(f"\n[1/3] Loading metadata from {METADATA_FILE}...")
    if not os.path.exists(METADATA_FILE):
        raise FileNotFoundError(f"Metadata file not found: {METADATA_FILE}")

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        metadata = yaml.safe_load(f)

    total_tables = sum(len(s.get("tables", [])) for s in metadata.get("schemas", []))
    print(f"  Found {len(metadata.get('schemas', []))} schema(s), {total_tables} table(s)")

    # Build graph
    print(f"\n[2/3] Building graph...")
    G = build_graph(metadata)

    print(f"\n  Graph summary:")
    print(f"  Nodes: {G.number_of_nodes()}")
    print(f"  Edges: {G.number_of_edges()}")

    # Count by type
    node_types = {}
    for _, data in G.nodes(data=True):
        t = data.get("type", "unknown")
        node_types[t] = node_types.get(t, 0) + 1

    for node_type, count in node_types.items():
        print(f"  {node_type}: {count}")

    edge_types = {}
    for _, _, data in G.edges(data=True):
        t = data.get("type", "unknown")
        edge_types[t] = edge_types.get(t, 0) + 1

    for edge_type, count in edge_types.items():
        print(f"  edge({edge_type}): {count}")

    # Save
    print(f"\n[3/3] Saving graph to {OUTPUT_FILE}...")
    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    graph_data = graph_to_json(G)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(graph_data, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"✅ Done! Graph saved to: {OUTPUT_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
