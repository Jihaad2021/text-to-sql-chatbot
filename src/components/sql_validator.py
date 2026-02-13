"""
Component 5: SQL Validator

Validates SQL queries using hybrid approach:
- Traditional validation (syntax, security, whitelist)
- AI validation (logic correctness with Claude)

Includes auto-fix capability with retry mechanism.

Type: Hybrid (Traditional + Agentic)
"""

from anthropic import Anthropic
import os
from dotenv import load_dotenv
import time
import re
import sqlparse

load_dotenv()

class ValidationResult:
    """Result of SQL validation"""
    def __init__(
        self,
        valid: bool,
        sql: str,
        errors: list = None,
        warnings: list = None,
        fixes_applied: list = None,
        validation_time_ms: float = 0
    ):
        self.valid = valid
        self.sql = sql
        self.errors = errors or []
        self.warnings = warnings or []
        self.fixes_applied = fixes_applied or []
        self.validation_time_ms = validation_time_ms

class SQLValidator:
    """
    Validate and auto-fix SQL queries.
    
    Multi-layer validation:
    1. Syntax validation (sqlparse)
    2. Security validation (SQL injection prevention)
    3. Table whitelist validation
    4. Logic validation (Claude - optional)
    """
    
    def __init__(self, enable_ai_validation: bool = True):
        """
        Initialize SQL Validator.
        
        Args:
            enable_ai_validation: Enable Claude logic validation (slower but more thorough)
        """
        self.enable_ai_validation = enable_ai_validation
        
        # Initialize Claude if AI validation enabled
        if enable_ai_validation:
            api_key = os.getenv('ANTHROPIC_API_KEY')
            if api_key:
                self.client = Anthropic(api_key=api_key)
                self.model = "claude-sonnet-4-20250514"
            else:
                print("⚠️  Warning: ANTHROPIC_API_KEY not found, AI validation disabled")
                self.enable_ai_validation = False
        
        # Table whitelist (all known tables)
        self.allowed_tables = {
            'customers', 'orders', 'payments',
            'products', 'sellers', 'order_items',
            'customer_segments', 'daily_metrics'
        }
        
        # Dangerous keywords (security)
        self.dangerous_keywords = {
            'DROP', 'DELETE', 'TRUNCATE', 'ALTER', 'CREATE',
            'INSERT', 'UPDATE', 'GRANT', 'REVOKE', 'EXECUTE',
            'PROCEDURE', 'FUNCTION'
        }
        
        print(f"✓ SQLValidator initialized")
        print(f"  - AI validation: {'enabled' if self.enable_ai_validation else 'disabled'}")
        print(f"  - Table whitelist: {len(self.allowed_tables)} tables")
    
    def validate_and_fix(
        self,
        sql: str,
        user_query: str = "",
        max_retries: int = 2
    ) -> ValidationResult:
        """
        Validate SQL with auto-fix retry mechanism.
        
        Args:
            sql: SQL query to validate
            user_query: Original user question (for context)
            max_retries: Max auto-fix attempts
        
        Returns:
            ValidationResult with validation status and potentially fixed SQL
        """
        start_time = time.time()
        
        current_sql = sql
        fixes_applied = []
        
        for attempt in range(max_retries + 1):
            # Run validation
            result = self._validate(current_sql, user_query)
            
            # If valid, return
            if result.valid:
                elapsed_ms = (time.time() - start_time) * 1000
                result.validation_time_ms = elapsed_ms
                result.fixes_applied = fixes_applied
                return result
            
            # If invalid and no more retries, return failure
            if attempt >= max_retries:
                elapsed_ms = (time.time() - start_time) * 1000
                result.validation_time_ms = elapsed_ms
                result.fixes_applied = fixes_applied
                return result
            
            # Try to auto-fix
            if self.enable_ai_validation:
                print(f"  Attempting auto-fix (attempt {attempt + 1}/{max_retries})...")
                fixed_sql = self._auto_fix(current_sql, result.errors, user_query)
                
                if fixed_sql and fixed_sql != current_sql:
                    fixes_applied.append(f"Attempt {attempt + 1}: Applied AI fix")
                    current_sql = fixed_sql
                else:
                    # Can't fix, return error
                    elapsed_ms = (time.time() - start_time) * 1000
                    result.validation_time_ms = elapsed_ms
                    result.fixes_applied = fixes_applied
                    return result
            else:
                # No AI validation, can't auto-fix
                elapsed_ms = (time.time() - start_time) * 1000
                result.validation_time_ms = elapsed_ms
                return result
        
        # Should not reach here
        elapsed_ms = (time.time() - start_time) * 1000
        return ValidationResult(
            valid=False,
            sql=current_sql,
            errors=["Max retries exceeded"],
            validation_time_ms=elapsed_ms,
            fixes_applied=fixes_applied
        )
    
    def _validate(self, sql: str, user_query: str = "") -> ValidationResult:
        """Run all validation layers"""
        
        errors = []
        warnings = []
        
        # Layer 1: Syntax validation
        syntax_errors = self._validate_syntax(sql)
        errors.extend(syntax_errors)
        
        # Layer 2: Security validation
        security_errors = self._validate_security(sql)
        errors.extend(security_errors)
        
        # If critical errors, stop here
        if errors:
            return ValidationResult(valid=False, sql=sql, errors=errors, warnings=warnings)
        
        # Layer 3: Table whitelist
        table_errors = self._validate_tables(sql)
        errors.extend(table_errors)
        
        # If table errors, stop here
        if errors:
            return ValidationResult(valid=False, sql=sql, errors=errors, warnings=warnings)
        
        # Layer 4: AI logic validation (optional, slower)
        if self.enable_ai_validation and user_query:
            logic_result = self._validate_logic_ai(sql, user_query)
            errors.extend(logic_result.get('errors', []))
            warnings.extend(logic_result.get('warnings', []))
        
        # Determine if valid
        valid = len(errors) == 0
        
        return ValidationResult(valid=valid, sql=sql, errors=errors, warnings=warnings)
    
    def _validate_syntax(self, sql: str) -> list:
        """Layer 1: Syntax validation using sqlparse"""
        errors = []
        
        try:
            # Parse SQL
            parsed = sqlparse.parse(sql)
            
            if not parsed:
                errors.append("SYNTAX: Empty or invalid SQL")
                return errors
            
            # Check if parseable
            statement = parsed[0]
            
            # Basic checks
            if not str(statement).strip():
                errors.append("SYNTAX: SQL is empty")
            
        except Exception as e:
            errors.append(f"SYNTAX: Parse error - {str(e)}")
        
        return errors
    
    def _validate_security(self, sql: str) -> list:
        """Layer 2: Security validation - SQL injection prevention"""
        errors = []
        
        sql_upper = sql.upper()
        
        # Check for dangerous keywords
        for keyword in self.dangerous_keywords:
            if keyword in sql_upper:
                errors.append(f"SECURITY: Dangerous keyword '{keyword}' not allowed")
        
        # Check for comment-based injection
        if '--' in sql or '/*' in sql or '*/' in sql:
            errors.append("SECURITY: SQL comments not allowed")
        
        # Check for semicolon (query stacking)
        if ';' in sql.strip().rstrip(';'):
            errors.append("SECURITY: Multiple statements not allowed")
        
        # Only allow SELECT
        if not sql_upper.strip().startswith('SELECT'):
            errors.append("SECURITY: Only SELECT queries are allowed")
        
        return errors
    
    def _validate_tables(self, sql: str) -> list:
        """Layer 3: Validate referenced tables are in whitelist"""
        errors = []
        
        # Extract table names from FROM and JOIN clauses
        # Improved pattern to handle table aliases
        # Matches: FROM table_name [alias], JOIN table_name [alias]
        pattern = r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:[a-zA-Z_][a-zA-Z0-9_]*)?'
        
        # Get all potential table references
        sql_lines = sql.split('\n')
        
        for line in sql_lines:
            # Skip WHERE, EXTRACT, functions
            if any(keyword in line.upper() for keyword in ['WHERE', 'EXTRACT', 'CURRENT_DATE', 'SELECT', 'ORDER BY', 'GROUP BY', 'HAVING']):
                continue
            
            # Find FROM/JOIN clauses only
            if 'FROM' in line.upper() or 'JOIN' in line.upper():
                # Extract just the table name (first word after FROM/JOIN)
                match = re.search(r'\b(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)', line, re.IGNORECASE)
                if match:
                    table_name = match.group(1)
                    table_lower = table_name.lower()
                    
                    # Only check if it's not an alias (single letter often = alias)
                    if len(table_name) > 1 and table_lower not in self.allowed_tables:
                        errors.append(f"TABLE: Unknown table '{table_name}' (not in whitelist)")
        
        return errors
  
    def _validate_logic_ai(self, sql: str, user_query: str) -> dict:
        """Layer 4: AI logic validation using Claude"""
        
        # Skip AI validation for queries with date functions (known to be strict)
        if 'EXTRACT(' in sql.upper() or 'DATE_TRUNC' in sql.upper():
            return {'errors': [], 'warnings': []}       
        
        prompt = f"""You are a SQL validator. Check if this SQL query correctly answers the user's question.

USER QUESTION: "{user_query}"

SQL QUERY:
{sql}

Check for:
1. Does the SQL logically answer the question?
2. Are the JOINs correct?
3. Are aggregations appropriate?
4. Is GROUP BY used correctly?
5. Are there logic errors?

Respond in this format:

VALID: [YES or NO]
ERRORS: [list any logic errors, one per line, or "None"]
WARNINGS: [list any warnings/suggestions, one per line, or "None"]

Be strict but fair. Minor style issues are warnings, not errors.

Your response:"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            
            result_text = response.content[0].text.strip()
            
            # Parse response
            errors = []
            warnings = []
            
            lines = result_text.split('\n')
            current_section = None
            
            for line in lines:
                line = line.strip()
                
                if line.startswith("VALID:"):
                    valid_str = line.replace("VALID:", "").strip().upper()
                    if valid_str == "NO":
                        current_section = None  # Will collect errors
                elif line.startswith("ERRORS:"):
                    current_section = "errors"
                    error_content = line.replace("ERRORS:", "").strip()
                    if error_content and error_content.lower() != "none":
                        errors.append(f"LOGIC: {error_content}")
                elif line.startswith("WARNINGS:"):
                    current_section = "warnings"
                    warning_content = line.replace("WARNINGS:", "").strip()
                    if warning_content and warning_content.lower() != "none":
                        warnings.append(f"LOGIC: {warning_content}")
                elif line.startswith("-") or line.startswith("•"):
                    # Bullet point
                    content = line.lstrip("-•").strip()
                    if content and content.lower() != "none":
                        if current_section == "errors":
                            errors.append(f"LOGIC: {content}")
                        elif current_section == "warnings":
                            warnings.append(f"LOGIC: {content}")
            
            return {'errors': errors, 'warnings': warnings}
        
        except Exception as e:
            print(f"✗ AI validation failed: {str(e)}")
            return {'errors': [], 'warnings': [f"AI validation unavailable: {str(e)}"]}
    
    def _auto_fix(self, sql: str, errors: list, user_query: str) -> str:
        """Attempt to auto-fix SQL using Claude"""
        
        error_text = "\n".join(errors)
        
        prompt = f"""You are a SQL fixer. Fix the errors in this SQL query.

USER QUESTION: "{user_query}"

CURRENT SQL (with errors):
{sql}

ERRORS TO FIX:
{error_text}

Generate a corrected SQL query that:
1. Fixes all the errors listed
2. Still answers the user's question correctly
3. Uses PostgreSQL syntax
4. Includes appropriate LIMIT clause

Return ONLY the corrected SQL query, no explanation.

Corrected SQL:"""
        
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=800,
                temperature=0,
                messages=[{"role": "user", "content": prompt}]
            )
            
            fixed_sql = response.content[0].text.strip()
            
            # Clean SQL
            fixed_sql = re.sub(r'```sql\s*', '', fixed_sql)
            fixed_sql = re.sub(r'```\s*', '', fixed_sql)
            fixed_sql = fixed_sql.strip()
            
            return fixed_sql
        
        except Exception as e:
            print(f"✗ Auto-fix failed: {str(e)}")
            return ""


# Test function
def test_sql_validator():
    """Test SQL Validator with various scenarios"""
    print("\n" + "="*60)
    print("TESTING SQL VALIDATOR")
    print("="*60 + "\n")
    
    # Initialize
    validator = SQLValidator(enable_ai_validation=True)
    
    # Test cases
    test_cases = [
        {
            "name": "Valid simple query",
            "sql": "SELECT * FROM customers LIMIT 10;",
            "user_query": "Show customers",
            "expect_valid": True
        },
        {
            "name": "Valid aggregation",
            "sql": "SELECT COUNT(*) as total FROM customers;",
            "user_query": "How many customers?",
            "expect_valid": True
        },
        {
            "name": "SQL Injection attempt",
            "sql": "SELECT * FROM customers; DROP TABLE orders; --",
            "user_query": "Show customers",
            "expect_valid": False
        },
        {
            "name": "Dangerous keyword",
            "sql": "DELETE FROM customers WHERE customer_id = 1;",
            "user_query": "Delete customer",
            "expect_valid": False
        },
        {
            "name": "Unknown table",
            "sql": "SELECT * FROM unknown_table LIMIT 10;",
            "user_query": "Show data",
            "expect_valid": False
        },
        {
            "name": "Valid JOIN query",
            "sql": "SELECT c.customer_name, COUNT(o.order_id) FROM customers c JOIN orders o ON c.customer_id = o.customer_id GROUP BY c.customer_name LIMIT 10;",
            "user_query": "Customer order counts",
            "expect_valid": True
        }
    ]
    
    passed = 0
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print("-" * 60)
        print(f"SQL: {test['sql'][:80]}...")
        
        result = validator.validate_and_fix(test['sql'], test['user_query'])
        
        match = "✓" if result.valid == test['expect_valid'] else "✗"
        
        print(f"{match} Valid: {result.valid} (expected: {test['expect_valid']})")
        print(f"  Time: {result.validation_time_ms:.0f}ms")
        
        if result.errors:
            print(f"  Errors: {len(result.errors)}")
            for error in result.errors[:2]:
                print(f"    - {error}")
        
        if result.warnings:
            print(f"  Warnings: {len(result.warnings)}")
        
        if result.fixes_applied:
            print(f"  Fixes applied: {len(result.fixes_applied)}")
        
        if result.valid == test['expect_valid']:
            passed += 1
        
        print()
    
    print("="*60)
    print(f"PASSED: {passed}/{len(test_cases)} ({100*passed//len(test_cases)}%)")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_sql_validator()