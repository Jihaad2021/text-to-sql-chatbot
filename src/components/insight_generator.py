"""
Component 7: Insight Generator

Generates natural language insights from query results.
Uses Claude Sonnet 4 to create user-friendly explanations.

Type: Agentic
"""

from anthropic import Anthropic
import os
from dotenv import load_dotenv
import time
import json

load_dotenv()

class InsightResult:
    """Result of insight generation"""
    def __init__(
        self,
        insights: str,
        insight_generation_time_ms: float = 0
    ):
        self.insights = insights
        self.insight_generation_time_ms = insight_generation_time_ms

class InsightGenerator:
    """
    Generate natural language insights from SQL query results.
    
    Makes data more accessible by:
    - Formatting numbers as currency, percentages
    - Highlighting key findings
    - Providing context and interpretation
    - Using conversational Indonesian
    """
    
    def __init__(self):
        """Initialize Insight Generator with Claude client"""
        
        # Get API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env file")
        
        # Initialize Claude client
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        print(f"✓ InsightGenerator initialized")
        print(f"  - Model: {self.model}")
    
    def generate(
        self,
        user_query: str,
        sql: str,
        results: list,
        row_count: int
    ) -> InsightResult:
        """
        Generate insights from query results.
        
        Args:
            user_query: Original user question
            sql: SQL that was executed
            results: Query results (list of dicts)
            row_count: Number of rows returned
        
        Returns:
            InsightResult with formatted insights
        """
        start_time = time.time()
        
        # Build prompt
        prompt = self._build_prompt(user_query, sql, results, row_count)
        
        try:
            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1000,
                temperature=0.3,  # Slightly creative for natural phrasing
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            insights = response.content[0].text.strip()
            
            elapsed_ms = (time.time() - start_time) * 1000
            
            return InsightResult(
                insights=insights,
                insight_generation_time_ms=elapsed_ms
            )
        
        except Exception as e:
            print(f"✗ Insight generation failed: {str(e)}")
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Fallback to basic formatting
            insights = self._basic_formatting(user_query, results, row_count)
            
            return InsightResult(
                insights=insights,
                insight_generation_time_ms=elapsed_ms
            )
    
    def _build_prompt(
        self,
        user_query: str,
        sql: str,
        results: list,
        row_count: int
    ) -> str:
        """Build insight generation prompt"""
        
        # Convert results to readable format
        if results and row_count > 0:
            # Show first 10 rows
            results_text = json.dumps(results[:10], indent=2, default=str)
            if row_count > 10:
                results_text += f"\n... and {row_count - 10} more rows"
        else:
            results_text = "No results returned"
        
        prompt = f"""You are a data analyst assistant. Generate insights from query results in conversational Indonesian.

USER QUESTION: "{user_query}"

SQL EXECUTED:
{sql}

RESULTS ({row_count} rows):
{results_text}

Generate insights that:
1. **Directly answer the user's question** in clear Indonesian
2. **Format numbers properly - BE VERY CAREFUL WITH SCALE**:
   - CRITICAL: Check magnitude before formatting!
   - Under 1 million: "Rp 500.000" or "Rp 500 ribu"
   - 1 million to 999 million: "Rp 252,3 juta" (NOT miliar!)
   - 1 billion and above: "Rp 1,2 miliar"
   
   **Examples of CORRECT formatting:**
   - 252,263,971 = "Rp 252,3 juta" (NOT miliar!)
   - 1,308,666,175 = "Rp 1,3 miliar" (correct)
   - 50,000,000 = "Rp 50 juta" (NOT miliar!)
   - 5,000,000,000 = "Rp 5 miliar" (correct)
   
   **Rule: Only use "miliar" if value >= 1,000,000,000 (9 zeros)**
   **Rule: Use "juta" if value >= 1,000,000 and < 1,000,000,000**
   
   - Percentages: "25%" or "25 persen"
3. **Highlight key findings**:
   - Use "tertinggi", "terendah", "rata-rata" for emphasis
   - Point out notable patterns or trends
4. **Be conversational but professional**:
   - Use "Anda memiliki...", "Terdapat...", "Hasil menunjukkan..."
   - Avoid overly technical jargon
5. **Keep it concise**: 2-4 sentences typically enough
6. **Ground in data**: Only state what's in the results, don't speculate

IMPORTANT RULES:
- State ONLY what the data shows
- Use probabilistic language ("menunjukkan", "mengindikasikan") not certainty
- Never imply causality without evidence
- Don't make recommendations unless query asks for them
- Highlight data limitations if relevant
- **CRITICAL: Always double-check number scale before using "miliar"!**

**CRITICAL - NO DATA SCENARIO:**
If results are empty (0 rows) or query returns NULL/zero values:
- DON'T just say "tidak ada data"
- Instead, provide helpful context:
  * Explain WHEN data might be available (date ranges if time-based query)
  * Suggest what user can query instead
  * Example: "Data untuk bulan Januari tidak tersedia. Data yang ada mencakup periode Februari-November 2024. Coba query untuk bulan-bulan tersebut."

**TIME-BASED QUERIES:**
If query asks for specific month/date but returns nothing:
- Explain the available data period
- Suggest alternative time ranges
- Example: "Revenue bulan Januari: Data tidak tersedia untuk periode tersebut. Database memiliki data transaksi dari tanggal X hingga Y. Coba query untuk periode ini."

Format:
- Start with direct answer to the question
- Add 1-2 supporting details if helpful
- If no data: Explain available date range and suggest alternatives
- Keep total under 150 words

Your insights in Indonesian:"""
        
        return prompt
    
    def _basic_formatting(
        self,
        user_query: str,
        results: list,
        row_count: int
    ) -> str:
        """Fallback: Basic formatting without Claude"""
        
        if not results or row_count == 0:
            return f"Query untuk '{user_query}' tidak mengembalikan hasil."
        
        # Try to format single value results
        if row_count == 1 and len(results[0]) == 1:
            key = list(results[0].keys())[0]
            value = results[0][key]
            
            # Format based on value type
            if isinstance(value, (int, float)):
                if value > 1_000_000:
                    formatted = f"Rp {value:,.0f}" if 'value' in key.lower() or 'revenue' in key.lower() else f"{value:,}"
                else:
                    formatted = f"{value:,}"
                return f"Hasil: {formatted}"
            else:
                return f"Hasil: {value}"
        
        # Multiple rows
        return f"Query mengembalikan {row_count} baris data."


# Test function
def test_insight_generator():
    """Test Insight Generator with various scenarios"""
    print("\n" + "="*60)
    print("TESTING INSIGHT GENERATOR")
    print("="*60 + "\n")
    
    # Initialize
    generator = InsightGenerator()
    
    # Test scenarios
    test_cases = [
        {
            "name": "Simple count",
            "user_query": "Berapa jumlah customer?",
            "sql": "SELECT COUNT(*) as total FROM customers;",
            "results": [{"total": 100}],
            "row_count": 1
        },
        {
            "name": "Revenue total",
            "user_query": "Total revenue berapa?",
            "sql": "SELECT SUM(payment_value) as total_revenue FROM payments;",
            "results": [{"total_revenue": 1308666175.75}],
            "row_count": 1
        },
        {
            "name": "Top customers",
            "user_query": "Top 5 customer berdasarkan spending",
            "sql": "SELECT customer_name, total_spent FROM ...",
            "results": [
                {"customer_name": "Siti Mandasari", "total_spent": 39948489.02},
                {"customer_name": "Dr. Oskar Nasyiah", "total_spent": 32438503.75},
                {"customer_name": "Agus Wahyudin", "total_spent": 28957365.82},
                {"customer_name": "Rika Pratiwi", "total_spent": 25123456.50},
                {"customer_name": "Bambang Sutrisno", "total_spent": 22456789.20}
            ],
            "row_count": 5
        },
        {
            "name": "No results",
            "user_query": "Orders with amount over 10 billion",
            "sql": "SELECT * FROM orders WHERE total > 10000000000;",
            "results": [],
            "row_count": 0
        }
    ]
    
    for i, test in enumerate(test_cases, 1):
        print(f"Test {i}: {test['name']}")
        print("-" * 60)
        print(f"Query: {test['user_query']}")
        
        result = generator.generate(
            test['user_query'],
            test['sql'],
            test['results'],
            test['row_count']
        )
        
        print(f"\n✓ Insights ({result.insight_generation_time_ms:.0f}ms):")
        print(result.insights)
        print()
    
    print("="*60)
    print("TESTS COMPLETE")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_insight_generator()