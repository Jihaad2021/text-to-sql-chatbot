"""
Component 4: SQL Generator

Generates SQL queries from natural language using Claude Sonnet 4.
Uses few-shot prompting for better accuracy.

Type: Agentic
"""

from anthropic import Anthropic
import os
from dotenv import load_dotenv
import time
import re
import yaml

load_dotenv()

class SQLGenerationResult:
    """Result of SQL generation"""
    def __init__(self, sql: str, generation_time_ms: float):
        self.sql = sql
        self.generation_time_ms = generation_time_ms

class RetrievedTable:
    """Represents a retrieved table schema"""
    def __init__(self, db_name: str, table_name: str, columns: list, description: str, relationships: list = None):
        self.db_name = db_name
        self.table_name = table_name
        self.columns = columns
        self.description = description
        self.relationships = relationships or []

class SQLGenerator:
    """
    Generate SQL queries from natural language.
    
    Uses Claude Sonnet 4 with few-shot prompting for high accuracy.
    """
    
    def __init__(self):
        """Initialize SQL Generator with Claude client and few-shot examples"""
        
        # Get API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env file")
        
        # Initialize Claude client
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        # Load few-shot examples
        self.examples = self._load_few_shot_examples()
        
        print(f"✓ SQLGenerator initialized")
        print(f"  - Model: {self.model}")
        print(f"  - Few-shot examples: {len(self.examples)}")
    
    def _load_few_shot_examples(self) -> list:
        """Load few-shot examples from YAML file"""
        try:
            with open('config/few_shot_examples.yaml', 'r') as f:
                config = yaml.safe_load(f)
                return config.get('examples', [])
        except FileNotFoundError:
            print("⚠️  Warning: few_shot_examples.yaml not found, using default examples")
            return self._get_default_examples()
    
    def _get_default_examples(self) -> list:
        """Default few-shot examples if YAML not found"""
        return [
            {
                'question': 'Show all customers',
                'sql': 'SELECT * FROM customers LIMIT 100;'
            },
            {
                'question': 'How many orders were placed?',
                'sql': 'SELECT COUNT(*) as total_orders FROM orders;'
            },
            {
                'question': 'Total sales this month',
                'sql': '''SELECT SUM(payment_value) as total_sales
FROM payments p
JOIN orders o ON p.order_id = o.order_id
WHERE EXTRACT(MONTH FROM o.order_purchase_timestamp) = EXTRACT(MONTH FROM CURRENT_DATE)
  AND EXTRACT(YEAR FROM o.order_purchase_timestamp) = EXTRACT(YEAR FROM CURRENT_DATE);'''
            },
            {
                'question': 'Top 5 customers by total spending',
                'sql': '''SELECT c.customer_id, c.customer_name, SUM(p.payment_value) as total_spent
FROM customers c
JOIN orders o ON c.customer_id = o.customer_id
JOIN payments p ON o.order_id = p.order_id
GROUP BY c.customer_id, c.customer_name
ORDER BY total_spent DESC
LIMIT 5;'''
            }
        ]
    
    def generate(self, user_query: str, relevant_tables: list) -> SQLGenerationResult:
        """
        Generate SQL query from natural language.
        
        Args:
            user_query: User's natural language question
            relevant_tables: List of RetrievedTable objects with schema info
        
        Returns:
            SQLGenerationResult with generated SQL
        """
        start_time = time.time()
        
        # Build prompt
        prompt = self._build_prompt(user_query, relevant_tables)
        
        # Call Claude
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0,  # Deterministic for SQL generation
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract SQL from response
            sql = response.content[0].text.strip()
            
            # Clean SQL (remove markdown if present)
            sql = self._clean_sql(sql)
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return SQLGenerationResult(
                sql=sql,
                generation_time_ms=elapsed_ms
            )
        
        except Exception as e:
            print(f"✗ SQL generation failed: {str(e)}")
            # Return empty result
            elapsed_ms = (time.time() - start_time) * 1000
            return SQLGenerationResult(
                sql="",
                generation_time_ms=elapsed_ms
            )
    
    def _build_prompt(self, user_query: str, tables: list) -> str:
        """Build comprehensive prompt for SQL generation"""
        
        # Part 1: System context
        system_context = """You are a PostgreSQL SQL expert. Generate accurate, safe SQL queries.

IMPORTANT RULES:
1. Use PostgreSQL syntax only
2. Always add LIMIT clause for SELECT queries (default: LIMIT 100)
3. Return ONLY the SQL query, no explanation
4. Use proper JOINs when querying multiple tables
5. Handle dates with EXTRACT() or DATE_TRUNC() functions
6. Use snake_case for all identifiers
"""
        
        # Part 2: Available schemas
        schema_context = "AVAILABLE TABLES:\n\n"
        for table in tables:
            schema_context += f"Table: {table.table_name} (in {table.db_name})\n"
            schema_context += f"Description: {table.description}\n"
            schema_context += f"Columns: {', '.join(table.columns)}\n"
            
            if table.relationships:
                schema_context += "Relationships:\n"
                for rel in table.relationships:
                    schema_context += f"  - {rel}\n"
            
            schema_context += "\n"
        
        # Part 3: Few-shot examples
        examples_context = "EXAMPLE QUERIES:\n\n"
        for i, example in enumerate(self.examples[:7], 1):  # Use first 7 examples
            examples_context += f"Example {i}:\n"
            examples_context += f"Question: {example['question']}\n"
            examples_context += f"SQL:\n{example['sql']}\n\n"
        
        # Part 4: User query
        user_context = f"""NOW GENERATE SQL FOR THIS QUESTION:

Question: {user_query}

Remember:
- Use only the tables provided above
- Add LIMIT clause
- Return only the SQL, no explanation
- Use PostgreSQL syntax

SQL:"""
        
        # Combine all parts
        full_prompt = f"{system_context}\n\n{schema_context}\n{examples_context}\n{user_context}"
        
        return full_prompt
    
    def _clean_sql(self, sql: str) -> str:
        """Clean SQL by removing markdown formatting"""
        # Remove ```sql and ``` markers
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*', '', sql)
        
        # Remove leading/trailing whitespace
        sql = sql.strip()
        
        return sql


# Test function
def test_sql_generator():
    """Test SQL Generator with sample queries"""
    print("\n" + "="*60)
    print("TESTING SQL GENERATOR")
    print("="*60 + "\n")
    
    # Initialize
    generator = SQLGenerator()
    
    # Mock retrieved tables (simulating Component 2 output)
    mock_tables = [
        RetrievedTable(
            db_name='sales_db',
            table_name='customers',
            columns=['customer_id', 'customer_name', 'customer_email', 'customer_city', 'customer_state'],
            description='Customer master data including contact information',
            relationships=['Referenced by orders.customer_id (1:N)']
        ),
        RetrievedTable(
            db_name='sales_db',
            table_name='orders',
            columns=['order_id', 'customer_id', 'order_status', 'order_purchase_timestamp'],
            description='Sales transactions and order history',
            relationships=['FK to customers.customer_id', 'Referenced by payments.order_id']
        ),
        RetrievedTable(
            db_name='sales_db',
            table_name='payments',
            columns=['payment_id', 'order_id', 'payment_type', 'payment_value'],
            description='Payment transactions and revenue data',
            relationships=['FK to orders.order_id']
        )
    ]
    
    # Test queries
    test_queries = [
        "How many customers are there?",
        "Show the first 5 customers",
        "What is the total revenue?",
        "Top 3 customers by spending",
        "Orders placed this month"
    ]
    
    print("Testing SQL generation with various queries:\n")
    
    for i, query in enumerate(test_queries, 1):
        print(f"Test {i}: {query}")
        print("-" * 60)
        
        result = generator.generate(query, mock_tables)
        
        if result.sql:
            print(f"✓ Generated SQL ({result.generation_time_ms:.0f}ms):")
            print(result.sql)
        else:
            print("✗ Failed to generate SQL")
        
        print("\n")
    
    print("="*60)
    print("TESTS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_sql_generator()