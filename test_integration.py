"""Quick End-to-End Integration Test"""

from src.components.sql_generator import SQLGenerator, RetrievedTable
from src.components.query_executor import QueryExecutor

print("="*60)
print("END-TO-END INTEGRATION TEST")
print("="*60 + "\n")

# Initialize components
print("Initializing components...")
generator = SQLGenerator()
executor = QueryExecutor()
print()

# Mock schema (simulating Component 2)
tables = [
    RetrievedTable(
        db_name='sales_db',
        table_name='customers',
        columns=['customer_id', 'customer_name', 'customer_city'],
        description='Customer data',
        relationships=['Referenced by orders.customer_id']
    ),
    RetrievedTable(
        db_name='sales_db',
        table_name='orders',
        columns=['order_id', 'customer_id', 'order_purchase_timestamp'],
        description='Order transactions',
        relationships=['FK to customers', 'Referenced by payments']
    ),
    RetrievedTable(
        db_name='sales_db',
        table_name='payments',
        columns=['payment_id', 'order_id', 'payment_value'],
        description='Payment data',
        relationships=['FK to orders']
    )
]

# Test queries
queries = [
    "How many customers do we have?",
    "What is the total revenue?",
    "Show me the top 3 customers by spending"
]

for i, question in enumerate(queries, 1):
    print(f"\nTest {i}: {question}")
    print("-"*60)
    
    # Step 1: Generate SQL
    print("→ Generating SQL...")
    result = generator.generate(question, tables)
    
    if not result.sql:
        print("✗ Failed to generate SQL")
        continue
    
    print(f"✓ Generated SQL ({result.generation_time_ms:.0f}ms):")
    print(f"  {result.sql[:80]}...")
    
    # Step 2: Execute SQL
    print("→ Executing SQL...")
    exec_result = executor.execute(result.sql, 'sales_db')
    
    if not exec_result.success:
        print(f"✗ Execution failed: {exec_result.error}")
        continue
    
    print(f"✓ Execution successful ({exec_result.execution_time_ms:.0f}ms)")
    print(f"  Rows returned: {exec_result.row_count}")
    
    # Step 3: Show results
    if exec_result.data and exec_result.row_count > 0:
        print("  Sample data:")
        for row in exec_result.data[:3]:
            print(f"    {row}")

print("\n" + "="*60)
print("✅ INTEGRATION TEST COMPLETE!")
print("="*60)
