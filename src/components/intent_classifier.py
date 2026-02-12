"""
Component 1: Intent Classifier

Classifies user queries into intent categories and detects ambiguous queries.
Uses Claude Sonnet 4 for intelligent classification.

Type: Agentic
"""

from anthropic import Anthropic
import os
from dotenv import load_dotenv
import time
from enum import Enum

load_dotenv()

class QueryIntent(str, Enum):
    """Query intent categories"""
    SIMPLE_SELECT = "simple_select"           # Basic SELECT queries
    FILTERED_QUERY = "filtered_query"         # SELECT with WHERE
    AGGREGATION = "aggregation"               # COUNT, SUM, AVG, etc.
    MULTI_TABLE_JOIN = "multi_table_join"     # JOIN queries
    COMPLEX_ANALYTICS = "complex_analytics"   # Complex queries with subqueries
    AMBIGUOUS = "ambiguous"                   # Unclear, needs clarification

class IntentResult:
    """Result of intent classification"""
    def __init__(
        self,
        intent: QueryIntent,
        confidence: float,
        reason: str = "",
        classification_time_ms: float = 0
    ):
        self.intent = intent
        self.confidence = confidence
        self.reason = reason
        self.classification_time_ms = classification_time_ms
    
    def needs_clarification(self) -> bool:
        """Check if query needs clarification"""
        return self.intent == QueryIntent.AMBIGUOUS or self.confidence < 0.7

class IntentClassifier:
    """
    Classify user query intent using Claude Sonnet 4.
    
    Helps detect:
    - Ambiguous queries that need clarification
    - Query complexity level
    - Expected operation type
    """
    
    def __init__(self):
        """Initialize Intent Classifier with Claude client"""
        
        # Get API key
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env file")
        
        # Initialize Claude client
        self.client = Anthropic(api_key=api_key)
        self.model = "claude-sonnet-4-20250514"
        
        print(f"✓ IntentClassifier initialized")
        print(f"  - Model: {self.model}")
    
    def classify(self, user_query: str) -> IntentResult:
        """
        Classify user query intent.
        
        Args:
            user_query: User's natural language question
        
        Returns:
            IntentResult with intent, confidence, and reason
        """
        start_time = time.time()
        
        # Build prompt
        prompt = self._build_prompt(user_query)
        
        try:
            # Call Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                temperature=0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Parse response
            result_text = response.content[0].text.strip()
            intent_result = self._parse_response(result_text)
            
            elapsed_ms = (time.time() - start_time) * 1000
            intent_result.classification_time_ms = elapsed_ms
            
            return intent_result
        
        except Exception as e:
            print(f"✗ Intent classification failed: {str(e)}")
            elapsed_ms = (time.time() - start_time) * 1000
            
            # Default to ambiguous on error
            return IntentResult(
                intent=QueryIntent.AMBIGUOUS,
                confidence=0.0,
                reason=f"Classification error: {str(e)}",
                classification_time_ms=elapsed_ms
            )
    
    def _build_prompt(self, user_query: str) -> str:
        """Build classification prompt"""
        
        prompt = f"""You are a SQL query intent classifier for an e-commerce database analytics system.

Classify the following user query into ONE of these categories:

1. simple_select - Basic data retrieval (e.g., "show all customers", "list products")
   Examples: "Show customers", "List orders", "Display products"

2. filtered_query - Queries with specific filters (e.g., "customers from Jakarta", "orders above 1000")
   Examples: "Customers in Jakarta", "Orders over Rp 1 million", "Products in Electronics category"

3. aggregation - Queries needing COUNT, SUM, AVG, MIN, MAX (e.g., "how many customers?", "total revenue")
   Examples: "How many customers?", "Total sales", "Average order value", "Count orders"

4. multi_table_join - Queries requiring data from multiple tables (e.g., "top customers by spending")
   Examples: "Top customers by revenue", "Products sold by each seller", "Customer order history"

5. complex_analytics - Advanced analytics with grouping, trends, comparisons
   Examples: "Monthly revenue trend", "Customer segmentation", "Year-over-year growth"

6. ambiguous - Unclear or incomplete queries that need clarification
   Examples: "Show me the data", "What about sales?", "Give me info", "Tell me more"

USER QUERY: "{user_query}"

Respond in this EXACT format:
INTENT: [intent_category]
CONFIDENCE: [0.0 to 1.0]
REASON: [brief explanation]

Rules:
- If query is vague, unclear, or lacks specificity → classify as "ambiguous"
- If confidence is below 0.7 → classify as "ambiguous"
- Be strict: when in doubt, mark as ambiguous
- Consider Indonesian and English queries
- Focus on what SQL operation would be needed

Your response:"""
        
        return prompt
    
    def _parse_response(self, response_text: str) -> IntentResult:
        """Parse Claude's classification response"""
        
        lines = response_text.strip().split('\n')
        
        intent_str = ""
        confidence = 0.0
        reason = ""
        
        for line in lines:
            line = line.strip()
            
            if line.startswith("INTENT:"):
                intent_str = line.replace("INTENT:", "").strip().lower()
            elif line.startswith("CONFIDENCE:"):
                conf_str = line.replace("CONFIDENCE:", "").strip()
                try:
                    confidence = float(conf_str)
                except:
                    confidence = 0.5
            elif line.startswith("REASON:"):
                reason = line.replace("REASON:", "").strip()
        
        # Map string to enum
        intent_mapping = {
            "simple_select": QueryIntent.SIMPLE_SELECT,
            "filtered_query": QueryIntent.FILTERED_QUERY,
            "aggregation": QueryIntent.AGGREGATION,
            "multi_table_join": QueryIntent.MULTI_TABLE_JOIN,
            "complex_analytics": QueryIntent.COMPLEX_ANALYTICS,
            "ambiguous": QueryIntent.AMBIGUOUS
        }
        
        intent = intent_mapping.get(intent_str, QueryIntent.AMBIGUOUS)
        
        # Force ambiguous if confidence too low
        if confidence < 0.7:
            intent = QueryIntent.AMBIGUOUS
            if not reason:
                reason = f"Low confidence ({confidence:.2f}) - needs clarification"
        
        return IntentResult(
            intent=intent,
            confidence=confidence,
            reason=reason
        )


# Test function
def test_intent_classifier():
    """Test Intent Classifier with various queries"""
    print("\n" + "="*60)
    print("TESTING INTENT CLASSIFIER")
    print("="*60 + "\n")
    
    # Initialize
    classifier = IntentClassifier()
    
    # Test queries
    test_queries = [
        # Clear queries
        ("How many customers are there?", QueryIntent.AGGREGATION),
        ("Show all customers", QueryIntent.SIMPLE_SELECT),
        ("Customers from Jakarta", QueryIntent.FILTERED_QUERY),
        ("Top 5 customers by spending", QueryIntent.MULTI_TABLE_JOIN),
        ("Monthly revenue trend", QueryIntent.COMPLEX_ANALYTICS),
        
        # Ambiguous queries
        ("Show me the data", QueryIntent.AMBIGUOUS),
        ("Tell me about sales", QueryIntent.AMBIGUOUS),
        ("What?", QueryIntent.AMBIGUOUS),
    ]
    
    print("Testing various query types:\n")
    
    success_count = 0
    
    for i, (query, expected_intent) in enumerate(test_queries, 1):
        print(f"Test {i}: {query}")
        print("-" * 60)
        
        result = classifier.classify(query)
        
        match = "✓" if result.intent == expected_intent else "✗"
        
        print(f"{match} Intent: {result.intent.value}")
        print(f"  Confidence: {result.confidence:.2f}")
        print(f"  Expected: {expected_intent.value}")
        print(f"  Reason: {result.reason}")
        print(f"  Time: {result.classification_time_ms:.0f}ms")
        
        if result.needs_clarification():
            print(f"  ⚠️  Needs clarification!")
        
        if result.intent == expected_intent:
            success_count += 1
        
        print()
    
    print("="*60)
    accuracy = (success_count / len(test_queries)) * 100
    print(f"ACCURACY: {success_count}/{len(test_queries)} ({accuracy:.0f}%)")
    print("="*60 + "\n")


if __name__ == "__main__":
    # Run tests
    test_intent_classifier()