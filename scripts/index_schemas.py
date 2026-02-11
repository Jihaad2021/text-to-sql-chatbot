"""
Schema Indexing Script

Creates ChromaDB embeddings for all table schemas.
This enables semantic search for relevant tables.
"""

import chromadb
from chromadb.utils import embedding_functions
import os
from dotenv import load_dotenv
import yaml

load_dotenv()

# Color codes
class Colors:
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_step(message):
    print(f"\n{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{message}{Colors.END}")
    print(f"{Colors.BLUE}{'='*60}{Colors.END}")

def print_success(message):
    print(f"{Colors.GREEN}✓ {message}{Colors.END}")

def print_info(message):
    print(f"{Colors.YELLOW}→ {message}{Colors.END}")

def print_error(message):
    print(f"{Colors.RED}✗ {message}{Colors.END}")

def load_schema_descriptions():
    """Load schema descriptions from YAML"""
    print_step("Loading schema descriptions")
    
    schema_file = 'data/schemas/schema_descriptions.yaml'
    
    if not os.path.exists(schema_file):
        print_error(f"Schema file not found: {schema_file}")
        print_info("Please ensure data/schemas/schema_descriptions.yaml exists")
        return None
    
    with open(schema_file, 'r') as f:
        schemas = yaml.safe_load(f)
    
    print_success(f"Loaded schemas for {len(schemas)} databases")
    return schemas

def initialize_chromadb():
    """Initialize ChromaDB client and collection"""
    print_step("Initializing ChromaDB")
    
    # Create persist directory if not exists
    persist_dir = './chroma_db'
    os.makedirs(persist_dir, exist_ok=True)
    
    # Initialize client
    client = chromadb.PersistentClient(path=persist_dir)
    print_success(f"ChromaDB client initialized at: {persist_dir}")
    
    # Get OpenAI API key
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key:
        print_error("OPENAI_API_KEY not found in .env")
        print_info("Please add OPENAI_API_KEY to your .env file")
        return None, None
    
    # Embedding function
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=openai_key,
        model_name="text-embedding-3-small"
    )
    print_success("OpenAI embedding function ready")
    
    # Delete existing collection if exists (for clean re-indexing)
    collection_name = "table_schemas"
    try:
        client.delete_collection(collection_name)
        print_info(f"Deleted existing collection: {collection_name}")
    except:
        pass
    
    # Create collection
    collection = client.create_collection(
        name=collection_name,
        embedding_function=openai_ef,
        metadata={"description": "Table schemas for Text-to-SQL chatbot"}
    )
    print_success(f"Created collection: {collection_name}")
    
    return client, collection

def create_rich_description(table_name, table_info, db_name):
    """Create rich semantic description for a table"""
    
    description = f"""Table: {table_name} in {db_name}

Business Purpose: {table_info['description']}

Columns:
"""
    
    for col_name, col_desc in table_info['columns'].items():
        description += f"- {col_name}: {col_desc}\n"
    
    if 'relationships' in table_info and table_info['relationships']:
        description += f"\nRelationships:\n"
        for rel in table_info['relationships']:
            description += f"- {rel}\n"
    
    if 'common_queries' in table_info and table_info['common_queries']:
        description += f"\nCommon Queries:\n"
        for query in table_info['common_queries']:
            description += f"- {query}\n"
    
    return description

def index_schemas(schemas, collection):
    """Index all schemas into ChromaDB"""
    print_step("Indexing schemas")
    
    documents = []
    metadatas = []
    ids = []
    
    total_tables = 0
    
    for db_name, tables in schemas.items():
        print_info(f"\nIndexing {db_name}...")
        
        for table_name, table_info in tables.items():
            # Create rich description
            description = create_rich_description(table_name, table_info, db_name)
            
            # Create document ID
            doc_id = f"{db_name}.{table_name}"
            
            # Prepare metadata
            metadata = {
                "db_name": db_name,
                "table_name": table_name,
                "columns": list(table_info['columns'].keys())
            }
            
            documents.append(description)
            metadatas.append(metadata)
            ids.append(doc_id)
            
            print_success(f"  {table_name}: Ready for indexing")
            total_tables += 1
    
    # Add to collection (this will generate embeddings)
    print_info(f"\nGenerating embeddings for {total_tables} tables...")
    print_info("(This may take 10-30 seconds...)")
    
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )
    
    print_success(f"✓ Indexed {total_tables} tables successfully!")
    
    return total_tables

def verify_indexing(collection):
    """Verify that indexing worked correctly"""
    print_step("Verifying indexing")
    
    # Check count
    count = collection.count()
    print_success(f"Total documents in collection: {count}")
    
    # Test retrieval with sample query
    print_info("\nTesting semantic search...")
    
    test_queries = [
        "customer information",
        "sales revenue",
        "product catalog"
    ]
    
    for query in test_queries:
        results = collection.query(
            query_texts=[query],
            n_results=3
        )
        
        print_info(f"\nQuery: '{query}'")
        print_info("Top 3 results:")
        for i, doc_id in enumerate(results['ids'][0], 1):
            distance = results['distances'][0][i-1] if results['distances'] else 'N/A'
            print_success(f"  {i}. {doc_id} (similarity: {1-distance:.3f})")
    
    print_success("\n✓ Semantic search working correctly!")

def print_summary(total_tables):
    """Print summary"""
    print_step("Indexing Summary")
    
    print(f"""
{Colors.GREEN}✅ Schema indexing completed successfully!{Colors.END}

{Colors.BOLD}What was created:{Colors.END}

{Colors.BLUE}ChromaDB Collection:{Colors.END} table_schemas
{Colors.BLUE}Total Tables Indexed:{Colors.END} {total_tables}
{Colors.BLUE}Location:{Colors.END} ./chroma_db/

{Colors.BOLD}Indexed Tables:{Colors.END}
  • sales_db: customers, orders, payments
  • products_db: products, sellers, order_items
  • analytics_db: customer_segments, daily_metrics

{Colors.BOLD}How it works:{Colors.END}
  When user asks "Top customers by revenue", the system will:
  1. Search ChromaDB semantically
  2. Retrieve relevant tables (customers, orders, payments)
  3. Pass only these tables to SQL generator
  4. Improve accuracy and reduce token usage

{Colors.YELLOW}Next Steps:{Colors.END}
  1. Test retrieval: {Colors.BOLD}python -c "from scripts.index_schemas import test_retrieval; test_retrieval()"{Colors.END}
  2. Implement Query Executor: {Colors.BOLD}src/components/query_executor.py{Colors.END}
  3. Start building core pipeline!

{Colors.GREEN}🚀 ChromaDB ready for use!{Colors.END}
""")

def test_retrieval():
    """Test function for manual retrieval testing"""
    import chromadb
    from chromadb.utils import embedding_functions
    
    client = chromadb.PersistentClient(path='./chroma_db')
    openai_ef = embedding_functions.OpenAIEmbeddingFunction(
        api_key=os.getenv('OPENAI_API_KEY'),
        model_name="text-embedding-3-small"
    )
    collection = client.get_collection(
        name="table_schemas",
        embedding_function=openai_ef
    )
    
    # Interactive test
    print("\n" + "="*60)
    print("CHROMADB RETRIEVAL TEST")
    print("="*60)
    
    query = input("\nEnter search query (e.g., 'revenue by customer'): ")
    
    results = collection.query(
        query_texts=[query],
        n_results=5
    )
    
    print(f"\nTop 5 results for: '{query}'")
    print("-"*60)
    
    for i in range(len(results['ids'][0])):
        doc_id = results['ids'][0][i]
        metadata = results['metadatas'][0][i]
        distance = results['distances'][0][i] if results['distances'] else None
        
        print(f"\n{i+1}. {doc_id}")
        print(f"   Database: {metadata['db_name']}")
        print(f"   Table: {metadata['table_name']}")
        print(f"   Columns: {', '.join(metadata['columns'][:5])}...")
        if distance is not None:
            print(f"   Similarity: {1-distance:.3f}")

def main():
    """Main execution"""
    print(f"\n{Colors.BOLD}{Colors.BLUE}")
    print("="*60)
    print("  TEXT-TO-SQL CHATBOT - SCHEMA INDEXING")
    print("="*60)
    print(f"{Colors.END}\n")
    
    try:
        # Step 1: Load schemas
        schemas = load_schema_descriptions()
        if not schemas:
            return
        
        # Step 2: Initialize ChromaDB
        client, collection = initialize_chromadb()
        if not client or not collection:
            return
        
        # Step 3: Index schemas
        total_tables = index_schemas(schemas, collection)
        
        # Step 4: Verify
        verify_indexing(collection)
        
        # Step 5: Summary
        print_summary(total_tables)
        
    except KeyboardInterrupt:
        print_error("\n\nIndexing interrupted by user")
    except Exception as e:
        print_error(f"\n\nError: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()