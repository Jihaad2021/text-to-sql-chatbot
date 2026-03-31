"""
RetrievedTable - Dataclass representing a retrieved table schema.

Used by SchemaRetriever, RetrievalEvaluator, and SQLGenerator.

Example:
    >>> table = RetrievedTable(
    ...     db_name="sales_db",
    ...     table_name="customers",
    ...     columns=["customer_id", "customer_name"],
    ...     description="Customer master data",
    ...     similarity_score=0.95
    ... )
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class RetrievedTable:
    """
    Represents a retrieved table schema from ChromaDB.

    Attributes:
        db_name: Database name (e.g., 'sales_db')
        table_name: Table name (e.g., 'customers')
        columns: List of column names
        description: Table description from YAML
        similarity_score: Cosine similarity score from ChromaDB (0.0 - 1.0)
        relationships: List of FK relationships
    """

    db_name: str
    table_name: str
    columns: List[str]
    description: str
    similarity_score: float = 0.0
    relationships: List[str] = field(default_factory=list)

    @property
    def full_name(self) -> str:
        """Return full table identifier (db.table)."""
        return f"{self.db_name}.{self.table_name}"

    def __str__(self) -> str:
        return f"{self.full_name} (score: {self.similarity_score:.3f})"