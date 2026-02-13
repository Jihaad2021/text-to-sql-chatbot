"""
Component 2: Schema Retriever

Retrieves relevant table schemas using RAG (ChromaDB semantic search).
Type: Traditional (RAG-based)
"""

import chromadb
from chromadb.utils import embedding_functions
import os
from dotenv import load_dotenv
import time

load_dotenv()

class RetrievedTable:
    """Represents a retrieved table schema"""
    def __init__(
        self,
        db_name: str,
        table_name: str,
        columns: list,
        description: str,
        similarity_score: float = 0.0,
        relationships: list = None
    ):
        self.db_name = db_name
        self.table_name = table_name
        self.columns = columns
        self.description = description
        self.similarity_score = similarity_score
        self.relationships = relationships or []

class SchemaRetrievalResult:
    """Result of schema retrieval"""
    def __init__(
        self,
        retrieved_tables: list,
        retrieval_time_ms: float = 0
    ):
        self.retrieved_tables = retrieved_tables
        self.retrieval_time_ms = retrieval_time_ms

class SchemaRetriever:
    """
    Retrieve relevant table schemas using semantic search.
    
    Uses ChromaDB with OpenAI embeddings for RAG-based table selection.
    """
    
    def __init__(self, chroma_path: str = "./chroma_db"):
        """Initialize Schema Retriever with ChromaDB"""
        
        # Get OpenAI API key
        openai_key = os.getenv('OPENAI_API_KEY')
        if not openai_key:
            raise ValueError("OPENAI_API_KEY not found in .env file")
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(path=chroma_path)
        
        # Initialize embedding function (same as indexing)
        self.embedding_function = embedding_functions.OpenAIEmbeddingFunction(
            api_key=openai_key,
            model_name="text-embedding-3-small"
        )
        
        # Get collection
        try:
            self.collection = self.client.get_collection(
                name="table_schemas",
                embedding_function=self.embedding_function
            )
            
            # Count documents
            count = self.collection.count()
            
            print(f"✓ SchemaRetriever initialized")
            print(f"  - ChromaDB path: {chroma_path}")
            print(f"  - Collection: table_schemas")
            print(f"  - Indexed tables: {count}")
            
        except Exception as e:
            raise ValueError(f"Failed to load ChromaDB collection: {str(e)}\nDid you run: python scripts/index_schemas.py ?")
    
    def retrieve(self, user_query: str, top_k: int = 5) -> SchemaRetrievalResult:
        """
        Retrieve top-K relevant tables using semantic search.
        
        Args:
            user_query: User's natural language question
            top_k: Number of tables to retrieve (1-10)
        
        Returns:
            SchemaRetrievalResult with retrieved tables
        """
        start_time = time.time()
        
        try:
            # Query ChromaDB
            results = self.collection.query(
                query_texts=[user_query],
                n_results=min(top_k, 10)  # Max 10
            )
            
            # Parse results
            retrieved_tables = []
            
            if results['ids'] and len(results['ids'][0]) > 0:
                for i in range(len(results['ids'][0])):
                    # Get metadata
                    metadata = results['metadatas'][0][i]
                    distance = results['distances'][0][i]
                    
                    # Convert distance to similarity (cosine similarity = 1 - distance)
                    similarity = 1.0 - distance
                    
                    # Parse columns (can be list or string)
                    columns_data = metadata.get('columns', [])
                    if isinstance(columns_data, list):
                        columns = columns_data
                    else:
                        columns = [col.strip() for col in str(columns_data).split(',') if col.strip()]

                    # Parse relationships (can be list or string)
                    relationships_data = metadata.get('relationships', [])
                    if isinstance(relationships_data, list):
                        relationships = relationships_data
                    else:
                        relationships = [rel.strip() for rel in str(relationships_data).split(';') if rel.strip()]                    
                                        
                    # Create RetrievedTable object
                    table = RetrievedTable(
                        db_name=metadata.get('db_name', ''),
                        table_name=metadata.get('table_name', ''),
                        columns=columns,
                        description=metadata.get('description', ''),
                        similarity_score=similarity,
                        relationships=relationships
                    )
                    
                    retrieved_tables.append(table)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return SchemaRetrievalResult(
                retrieved_tables=retrieved_tables,
                retrieval_time_ms=elapsed_ms
            )
        
        except Exception as e:
            print(f"✗ Schema retrieval failed: {str(e)}")
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Return empty result
            return SchemaRetrievalResult(
                retrieved_tables=[],
                retrieval_time_ms=elapsed_ms
            )
    
    def get_all_tables(self) -> list:
        """Get all indexed tables (for debugging)"""
        try:
            # Get all documents
            all_data = self.collection.get()
            
            tables = []
            for i in range(len(all_data['ids'])):
                metadata = all_data['metadatas'][i]
                tables.append(f"{metadata['db_name']}.{metadata['table_name']}")
            
            return tables
        except:
            return []


# Test function
def test_schema_retriever():
    """Test Schema Retriever with sample queries"""
    print("\n" + "="*60)
    print("TESTING SCHEMA RETRIEVER")
    print("="*60 + "\n")
    
    # Initialize
    retriever = SchemaRetriever()
    
    # Show all indexed tables
    all_tables = retriever.get_all_tables()
    print(f"All indexed tables: {all_tables}\n")
    
    # Test queries
    test_queries = [
        ("Customer information", 3),
        ("Revenue and sales", 3),
        ("Product catalog", 3),
        ("Top customers by spending", 5),
        ("Daily analytics", 2)
    ]
    
    print("Testing retrieval with various queries:\n")
    
    for query, top_k in test_queries:
        print(f"Query: '{query}' (top-{top_k})")
        print("-" * 60)
        
        result = retriever.retrieve(query, top_k)
        
        print(f"✓ Retrieved {len(result.retrieved_tables)} tables ({result.retrieval_time_ms:.0f}ms)")
        
        for i, table in enumerate(result.retrieved_tables, 1):
            print(f"  {i}. {table.db_name}.{table.table_name}")
            print(f"     Similarity: {table.similarity_score:.3f}")
            print(f"     Columns: {', '.join(table.columns[:5])}{'...' if len(table.columns) > 5 else ''}")
        
        print()
    
    print("="*60)
    print("TESTS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_schema_retriever()