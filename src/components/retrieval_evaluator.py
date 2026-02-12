"""
Component 3: Retrieval Evaluator

Evaluates and filters retrieved table schemas from ChromaDB.
Uses Claude Sonnet 4 to determine which tables are truly relevant.

Type: Agentic
"""

from anthropic import Anthropic
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

class EvaluationResult:
    """Result of retrieval evaluation"""
    def __init__(
        self,
        essential_tables: list,
        optional_tables: list,
        excluded_tables: list,
        evaluation_time_ms: float = 0
    ):
        self.essential_tables = essential_tables  # Must include
        self.optional_tables = optional_tables    # Nice to have
        self.excluded_tables = excluded_tables    # Not needed
        self.evaluation_time_ms = evaluation_time_ms
    
    def get_relevant_tables(self) -> list:
        """Get all relevant tables (essential + optional)"""
        return self.essential_tables + self.optional_tables

class RetrievalEvaluator:
    """
    Evaluate retrieved tables and filter to only relevant ones.
    
    This component helps reduce false positives from semantic search
    and ensures only necessary tables are passed to SQL generator.
    """
    
    def __init__(self):
        """Initialize Retrieval Evaluator with Claude client"""
        
        # Get API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env file")
        
        # Initialize Claude client
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        print(f"✓ RetrievalEvaluator initialized")
        print(f"  - Model: {self.model}")
    
    def evaluate(
        self,
        user_query: str,
        retrieved_tables: list
    ) -> EvaluationResult:
        """
        Evaluate which retrieved tables are actually relevant.
        
        Args:
            user_query: User's natural language question
            retrieved_tables: List of RetrievedTable objects from ChromaDB
        
        Returns:
            EvaluationResult with essential, optional, and excluded tables
        """
        start_time = time.time()
        
        # If only 1-2 tables, no need to evaluate
        if len(retrieved_tables) <= 2:
            elapsed_ms = (time.time() - start_time) * 1000
            return EvaluationResult(
                essential_tables=retrieved_tables,
                optional_tables=[],
                excluded_tables=[],
                evaluation_time_ms=elapsed_ms
            )
        
        # Build prompt
        prompt = self._build_prompt(user_query, retrieved_tables)
        
        try:
            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse response
            result_text = response.content[0].text.strip()
            evaluation = self._parse_response(result_text, retrieved_tables)
            
            elapsed_ms = (time.time() - start_time) * 1000
            evaluation.evaluation_time_ms = elapsed_ms
            
            return evaluation
        
        except Exception as e:
            print(f"✗ Retrieval evaluation failed: {str(e)}")
            elapsed_ms = (time.time() - start_time) * 1000
            
            # On error, return all tables as essential (safe fallback)
            return EvaluationResult(
                essential_tables=retrieved_tables,
                optional_tables=[],
                excluded_tables=[],
                evaluation_time_ms=elapsed_ms
            )
    
    def _build_prompt(self, user_query: str, tables: list) -> str:
        """Build evaluation prompt"""
        
        # Build table descriptions
        tables_info = ""
        for i, table in enumerate(tables, 1):
            tables_info += f"\nTable {i}: {table.db_name}.{table.table_name}\n"
            tables_info += f"Description: {table.description}\n"
            tables_info += f"Columns: {', '.join(table.columns[:10])}"  # First 10 columns
            if len(table.columns) > 10:
                tables_info += f"... (+{len(table.columns) - 10} more)"
            tables_info += f"\nSimilarity Score: {table.similarity_score:.3f}\n"
            
            if table.relationships:
                tables_info += f"Relationships: {'; '.join(table.relationships[:3])}\n"
        
        prompt = f"""You are a database schema analyzer. Evaluate which tables are needed to answer a user's query.

USER QUERY: "{user_query}"

RETRIEVED TABLES (from semantic search):
{tables_info}

Your task: Categorize each table as ESSENTIAL, OPTIONAL, or EXCLUDED.

Categories:
- ESSENTIAL: Absolutely required to answer the query. Contains the core data needed.
- OPTIONAL: Might provide additional context but not strictly necessary.
- EXCLUDED: Not relevant to this specific query. Would add noise.

Consider:
1. Does the query directly ask for data from this table?
2. Is this table needed to JOIN with other tables for the answer?
3. Does the table contain metrics/values the query is asking about?
4. Would excluding this table make the query incomplete?

Respond in this EXACT format:

ESSENTIAL:
- [db_name.table_name]: [brief reason]

OPTIONAL:
- [db_name.table_name]: [brief reason]

EXCLUDED:
- [db_name.table_name]: [brief reason]

Be strict: Only mark as ESSENTIAL if truly required. When in doubt between ESSENTIAL and OPTIONAL, choose OPTIONAL.

Your response:"""
        
        return prompt
    
    def _parse_response(
        self,
        response_text: str,
        tables: list
    ) -> EvaluationResult:
        """Parse Claude's evaluation response"""
        
        # Create lookup map
        table_map = {f"{t.db_name}.{t.table_name}": t for t in tables}
        
        essential = []
        optional = []
        excluded = []
        
        current_category = None
        
        for line in response_text.split('\n'):
            line = line.strip()
            
            if line.startswith("ESSENTIAL:"):
                current_category = "essential"
                continue
            elif line.startswith("OPTIONAL:"):
                current_category = "optional"
                continue
            elif line.startswith("EXCLUDED:"):
                current_category = "excluded"
                continue
            
            # Parse table entries
            if line.startswith("-") and current_category:
                # Extract table name (before colon)
                if ":" in line:
                    table_part = line.split(":")[0].strip("- ").strip()
                    
                    # Find matching table
                    for table_key, table_obj in table_map.items():
                        if table_part in table_key or table_key in table_part:
                            if current_category == "essential":
                                essential.append(table_obj)
                            elif current_category == "optional":
                                optional.append(table_obj)
                            elif current_category == "excluded":
                                excluded.append(table_obj)
                            break
        
        # Fallback: if nothing parsed, mark all as essential (safe)
        if not essential and not optional and not excluded:
            essential = tables
        
        return EvaluationResult(
            essential_tables=essential,
            optional_tables=optional,
            excluded_tables=excluded
        )


# Test function
def test_retrieval_evaluator():
    """Test Retrieval Evaluator with mock scenarios"""
    print("\n" + "="*60)
    print("TESTING RETRIEVAL EVALUATOR")
    print("="*60 + "\n")
    
    # Initialize
    evaluator = RetrievalEvaluator()
    
    # Test Scenario 1: Customer count query
    print("Scenario 1: 'How many customers are there?'")
    print("-" * 60)
    
    mock_tables_1 = [
        RetrievedTable(
            db_name="sales_db",
            table_name="customers",
            columns=["customer_id", "customer_name", "customer_email"],
            description="Customer master data",
            similarity_score=0.95
        ),
        RetrievedTable(
            db_name="sales_db",
            table_name="orders",
            columns=["order_id", "customer_id", "order_date"],
            description="Order transactions",
            similarity_score=0.68
        ),
        RetrievedTable(
            db_name="analytics_db",
            table_name="customer_segments",
            columns=["customer_id", "segment", "lifetime_value"],
            description="Customer segmentation",
            similarity_score=0.72
        )
    ]
    
    result1 = evaluator.evaluate("How many customers are there?", mock_tables_1)
    
    print(f"✓ Evaluation complete ({result1.evaluation_time_ms:.0f}ms)")
    print(f"\nESSENTIAL ({len(result1.essential_tables)}):")
    for t in result1.essential_tables:
        print(f"  - {t.db_name}.{t.table_name}")
    
    print(f"\nOPTIONAL ({len(result1.optional_tables)}):")
    for t in result1.optional_tables:
        print(f"  - {t.db_name}.{t.table_name}")
    
    print(f"\nEXCLUDED ({len(result1.excluded_tables)}):")
    for t in result1.excluded_tables:
        print(f"  - {t.db_name}.{t.table_name}")
    
    # Test Scenario 2: Top customers by spending
    print("\n\nScenario 2: 'Top 5 customers by total spending'")
    print("-" * 60)
    
    mock_tables_2 = [
        RetrievedTable(
            db_name="sales_db",
            table_name="customers",
            columns=["customer_id", "customer_name"],
            description="Customer master data",
            similarity_score=0.89
        ),
        RetrievedTable(
            db_name="sales_db",
            table_name="orders",
            columns=["order_id", "customer_id", "order_date"],
            description="Order transactions",
            similarity_score=0.85
        ),
        RetrievedTable(
            db_name="sales_db",
            table_name="payments",
            columns=["payment_id", "order_id", "payment_value"],
            description="Payment data with revenue",
            similarity_score=0.92
        ),
        RetrievedTable(
            db_name="products_db",
            table_name="products",
            columns=["product_id", "product_name", "price"],
            description="Product catalog",
            similarity_score=0.54
        )
    ]
    
    result2 = evaluator.evaluate("Top 5 customers by total spending", mock_tables_2)
    
    print(f"✓ Evaluation complete ({result2.evaluation_time_ms:.0f}ms)")
    print(f"\nESSENTIAL ({len(result2.essential_tables)}):")
    for t in result2.essential_tables:
        print(f"  - {t.db_name}.{t.table_name}")
    
    print(f"\nOPTIONAL ({len(result2.optional_tables)}):")
    for t in result2.optional_tables:
        print(f"  - {t.db_name}.{t.table_name}")
    
    print(f"\nEXCLUDED ({len(result2.excluded_tables)}):")
    for t in result2.excluded_tables:
        print(f"  - {t.db_name}.{t.table_name}")
    
    print("\n" + "="*60)
    print("TESTS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_retrieval_evaluator()