"""
Component 6: Query Executor

Executes SQL queries safely with timeout and row limits.
Type: Traditional (Deterministic)
"""

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError, OperationalError, ProgrammingError
from sqlalchemy.pool import NullPool
import os
from dotenv import load_dotenv
import time
from typing import Dict, List, Any, Optional

load_dotenv()

class ExecutionResult:
    """Result of SQL execution"""
    def __init__(
        self,
        success: bool,
        data: Optional[List[Dict[str, Any]]] = None,
        row_count: int = 0,
        execution_time_ms: float = 0,
        error: Optional[str] = None
    ):
        self.success = success
        self.data = data
        self.row_count = row_count
        self.execution_time_ms = execution_time_ms
        self.error = error

class QueryExecutor:
    """
    Execute SQL queries safely with:
    - Timeout protection (30s default)
    - Row limit enforcement (10K default)
    - Connection pooling
    - Error handling
    """
    
    def __init__(
        self,
        timeout_seconds: int = 30,
        max_rows: int = 10000
    ):
        """
        Initialize executor with database connections.
        
        Args:
            timeout_seconds: Query timeout (default 30s)
            max_rows: Maximum rows to return (default 10K)
        """
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows
        
        # Create database engines
        self.engines = self._create_engines()
        
        print(f"✓ QueryExecutor initialized")
        print(f"  - Timeout: {timeout_seconds}s")
        print(f"  - Max rows: {max_rows:,}")
        print(f"  - Databases: {list(self.engines.keys())}")
    
    def _create_engines(self) -> Dict[str, Any]:
        """Create SQLAlchemy engines for all databases"""
        db_configs = {
            'sales_db': os.getenv('SALES_DB_URL'),
            'products_db': os.getenv('PRODUCTS_DB_URL'),
            'analytics_db': os.getenv('ANALYTICS_DB_URL')
        }
        
        engines = {}
        
        for db_name, db_url in db_configs.items():
            if not db_url:
                print(f"⚠️  Warning: {db_name} URL not found in .env")
                continue
            
            try:
                # Simple engine without pooling conflicts
                engine = create_engine(
                    db_url,
                    pool_pre_ping=True,  # Verify connections
                    echo=False           # Don't log SQL
                )
                
                # Test connection
                with engine.connect() as conn:
                    conn.execute(text("SELECT 1"))
                
                engines[db_name] = engine
                
            except Exception as e:
                print(f"✗ Failed to connect to {db_name}: {str(e)}")
        
        if not engines:
            raise ValueError("No database connections available!")
        
        return engines
    
    def execute(
        self,
        sql: str,
        db_name: str = 'sales_db'
    ) -> ExecutionResult:
        """
        Execute SQL query with safety controls.
        
        Args:
            sql: SQL query to execute
            db_name: Target database (sales_db, products_db, analytics_db)
        
        Returns:
            ExecutionResult with data or error
        """
        start_time = time.time()
        
        # Validate database
        if db_name not in self.engines:
            return ExecutionResult(
                success=False,
                error=f"Database '{db_name}' not available. Available: {list(self.engines.keys())}"
            )
        
        engine = self.engines[db_name]
        
        try:
            with engine.connect() as conn:
                # Set statement timeout (PostgreSQL specific)
                timeout_ms = self.timeout_seconds * 1000
                conn.execute(text(f"SET statement_timeout = {timeout_ms}"))
                
                # Execute query
                result = conn.execute(text(sql))
                
                # Fetch results with row limit
                rows = result.fetchmany(self.max_rows)
                
                # Convert to list of dicts
                if rows:
                    columns = result.keys()
                    data = [dict(zip(columns, row)) for row in rows]
                else:
                    data = []
                
                elapsed_ms = (time.time() - start_time) * 1000
                
                return ExecutionResult(
                    success=True,
                    data=data,
                    row_count=len(data),
                    execution_time_ms=elapsed_ms
                )
        
        except OperationalError as e:
            # Timeout or connection issues
            elapsed_ms = (time.time() - start_time) * 1000
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            
            if 'timeout' in error_msg.lower():
                error_msg = f"Query timeout after {self.timeout_seconds}s. Try narrowing your query."
            elif 'connection' in error_msg.lower():
                error_msg = f"Database connection error: {error_msg}"
            
            return ExecutionResult(
                success=False,
                error=error_msg,
                execution_time_ms=elapsed_ms
            )
        
        except ProgrammingError as e:
            # SQL syntax errors
            elapsed_ms = (time.time() - start_time) * 1000
            error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
            
            return ExecutionResult(
                success=False,
                error=f"SQL error: {error_msg}",
                execution_time_ms=elapsed_ms
            )
        
        except SQLAlchemyError as e:
            # Other SQLAlchemy errors
            elapsed_ms = (time.time() - start_time) * 1000
            
            return ExecutionResult(
                success=False,
                error=f"Database error: {str(e)}",
                execution_time_ms=elapsed_ms
            )
        
        except Exception as e:
            # Unexpected errors
            elapsed_ms = (time.time() - start_time) * 1000
            
            return ExecutionResult(
                success=False,
                error=f"Unexpected error: {str(e)}",
                execution_time_ms=elapsed_ms
            )
    
    def test_connection(self, db_name: str = 'sales_db') -> bool:
        """
        Test database connection.
        
        Args:
            db_name: Database to test
        
        Returns:
            True if connection successful
        """
        try:
            result = self.execute("SELECT 1 as test", db_name)
            return result.success
        except:
            return False
    
    def get_table_info(self, table_name: str, db_name: str = 'sales_db') -> ExecutionResult:
        """
        Get information about a table.
        
        Args:
            table_name: Name of table
            db_name: Database name
        
        Returns:
            ExecutionResult with table structure
        """
        sql = f"""
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_name = '{table_name}'
        ORDER BY ordinal_position
        """
        
        return self.execute(sql, db_name)
    
    def close(self):
        """Close all database connections"""
        for db_name, engine in self.engines.items():
            try:
                engine.dispose()
                print(f"✓ Closed connection to {db_name}")
            except Exception as e:
                print(f"✗ Error closing {db_name}: {str(e)}")


# Test function
def test_query_executor():
    """Test QueryExecutor with sample queries"""
    print("\n" + "="*60)
    print("TESTING QUERY EXECUTOR")
    print("="*60 + "\n")
    
    # Initialize
    executor = QueryExecutor()
    
    # Test 1: Simple count
    print("Test 1: Count customers")
    result = executor.execute("SELECT COUNT(*) as total FROM customers", "sales_db")
    
    if result.success:
        print(f"✓ Success! Customers: {result.data[0]['total']}")
        print(f"  Execution time: {result.execution_time_ms:.0f}ms")
    else:
        print(f"✗ Failed: {result.error}")
    
    # Test 2: Sample data
    print("\nTest 2: Sample customers")
    result = executor.execute(
        "SELECT customer_name, customer_city FROM customers LIMIT 5",
        "sales_db"
    )
    
    if result.success:
        print(f"✓ Success! Retrieved {result.row_count} rows")
        for i, row in enumerate(result.data, 1):
            print(f"  {i}. {row['customer_name']} from {row['customer_city']}")
    else:
        print(f"✗ Failed: {result.error}")
    
    # Test 3: Aggregation
    print("\nTest 3: Total revenue")
    result = executor.execute(
        "SELECT SUM(payment_value) as total_revenue FROM payments",
        "sales_db"
    )
    
    if result.success:
        revenue = result.data[0]['total_revenue']
        print(f"✓ Success! Total revenue: Rp {revenue:,.2f}")
    else:
        print(f"✗ Failed: {result.error}")
    
    # Test 4: JOIN query
    print("\nTest 4: Top 3 customers by spending")
    result = executor.execute(
        """
        SELECT c.customer_name, SUM(p.payment_value) as total_spent
        FROM customers c
        JOIN orders o ON c.customer_id = o.customer_id
        JOIN payments p ON o.order_id = p.order_id
        GROUP BY c.customer_name
        ORDER BY total_spent DESC
        LIMIT 3
        """,
        "sales_db"
    )
    
    if result.success:
        print(f"✓ Success! Top spenders:")
        for i, row in enumerate(result.data, 1):
            print(f"  {i}. {row['customer_name']}: Rp {row['total_spent']:,.2f}")
    else:
        print(f"✗ Failed: {result.error}")
    
    # Test 5: Error handling (invalid table)
    print("\nTest 5: Error handling (invalid table)")
    result = executor.execute("SELECT * FROM nonexistent_table", "sales_db")
    
    if not result.success:
        print(f"✓ Correctly handled error: {result.error[:80]}...")
    else:
        print("✗ Should have failed!")
    
    # Test 6: Multi-database
    print("\nTest 6: Products database")
    result = executor.execute("SELECT COUNT(*) as total FROM products", "products_db")
    
    if result.success:
        print(f"✓ Success! Products: {result.data[0]['total']}")
    else:
        print(f"✗ Failed: {result.error}")
    
    print("\n" + "="*60)
    print("TESTS COMPLETE")
    print("="*60 + "\n")
    
    # Cleanup
    executor.close()


if __name__ == "__main__":
    # Run tests
    test_query_executor()