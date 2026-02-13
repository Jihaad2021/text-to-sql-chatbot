"""
FastAPI Application - Text-to-SQL Chatbot
Complete pipeline with all 7 components integrated.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import time

# Import ALL components
from src.components.intent_classifier import IntentClassifier
from src.components.schema_retriever import SchemaRetriever
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.components.query_executor import QueryExecutor
from src.components.insight_generator import InsightGenerator

# Initialize FastAPI
app = FastAPI(
    title="Text-to-SQL Chatbot API",
    description="AI-powered natural language to SQL with complete validation pipeline",
    version="2.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize ALL components
print("\n" + "="*60)
print("INITIALIZING TEXT-TO-SQL CHATBOT - FULL PIPELINE")
print("="*60 + "\n")

intent_classifier = IntentClassifier()
schema_retriever = SchemaRetriever()
sql_generator = SQLGenerator()
sql_validator = SQLValidator(enable_ai_validation=False)
query_executor = QueryExecutor()
insight_generator = InsightGenerator()
retrieval_evaluator = RetrievalEvaluator()

print("\n✅ ALL COMPONENTS READY!\n")
print("Pipeline: Intent → Retrieval → Evaluation → Generation → Validation → Execution → Insights")
print()

# Request/Response models
class QueryRequest(BaseModel):
    question: str
    database: Optional[str] = "sales_db"

class QueryResponse(BaseModel):
    question: str
    sql: Optional[str]
    data: Optional[List[Dict[str, Any]]]
    insights: Optional[str]
    row_count: int
    execution_time_ms: float
    metadata: Dict[str, Any]

# Helper function
def get_date_context(db_name: str, table_name: str, date_column: str):
    """Get available date range for context"""
    try:
        query = f"""
        SELECT 
            MIN({date_column}) as earliest_date,
            MAX({date_column}) as latest_date,
            COUNT(*) as total_records
        FROM {table_name}
        """
        
        result = query_executor.execute(query, db_name)
        
        if result.success and result.data:
            return result.data[0]
        return None
    except:
        return None

# Routes
@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Text-to-SQL Chatbot API - Full Pipeline v2.0",
        "components": [
            "Intent Classifier",
            "Schema Retriever",
            "Retrieval Evaluator",
            "SQL Generator",
            "SQL Validator",
            "Query Executor",
            "Insight Generator"
        ],
        "endpoints": {
            "health": "/health",
            "query": "/query (POST)",
            "databases": "/databases",
            "docs": "/docs"
        }
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "components": {
            "intent_classifier": "ready",
            "schema_retriever": "ready",
            "retrieval_evaluator": "ready",
            "sql_generator": "ready",
            "sql_validator": "ready",
            "query_executor": "ready",
            "insight_generator": "ready"
        }
    }

@app.get("/databases")
def list_databases():
    """List available databases based on indexed schemas"""
    try:
        all_tables = schema_retriever.get_all_tables()
        
        # Extract unique database names
        databases = list(set([
            table.split('.')[0] for table in all_tables if '.' in table
        ]))
        
        return {
            "databases": sorted(databases),
            "default": databases[0] if databases else "sales_db",
            "total_tables": len(all_tables)
        }
    except Exception as e:
        return {
            "databases": ["sales_db", "products_db", "analytics_db"],
            "default": "sales_db",
            "error": str(e)
        }

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Main endpoint: Complete 7-component pipeline.
    
    Pipeline:
    1. Intent Classification
    2. Schema Retrieval (ChromaDB)
    3. Retrieval Evaluation
    4. SQL Generation
    5. SQL Validation
    6. Query Execution
    7. Insight Generation
    """
    start_time = time.time()
    
    try:
        user_question = request.question
        db_name = request.database
        
        # ========================================
        # STEP 1: INTENT CLASSIFICATION
        # ========================================
        print(f"\n[1/7] Classifying intent for: {user_question[:50]}...")
        intent_result = intent_classifier.classify(user_question)
        
        # Check if needs clarification
        if intent_result.needs_clarification():
            return QueryResponse(
                question=user_question,
                sql=None,
                data=None,
                insights=None,
                row_count=0,
                execution_time_ms=(time.time() - start_time) * 1000,
                metadata={
                    "pipeline_stage": "intent_classification",
                    "database": db_name,
                    "intent": intent_result.intent.value,
                    "confidence": intent_result.confidence,
                    "needs_clarification": True,
                    "clarification_reason": intent_result.reason,
                    "suggestion": "Please provide more specific details about what data you want to query."
                }
            )
        
        print(f"  ✓ Intent: {intent_result.intent.value} (confidence: {intent_result.confidence:.2f})")
        
        # ========================================
        # STEP 2: SCHEMA RETRIEVAL (ChromaDB RAG)
        # ========================================
        print(f"[2/7] Retrieving schemas from ChromaDB...")
        retrieval_result = schema_retriever.retrieve(user_question, top_k=5)
        retrieved_schemas = retrieval_result.retrieved_tables

        if not retrieved_schemas:
            raise HTTPException(
                status_code=400,
                detail="No relevant schemas found. Please try a different question."
            )

        print(f"  ✓ Retrieved {len(retrieved_schemas)} tables ({retrieval_result.retrieval_time_ms:.0f}ms)")
        for table in retrieved_schemas:
            print(f"    - {table.db_name}.{table.table_name} (similarity: {table.similarity_score:.3f})")

        # ✨ AUTO-DETECT DATABASE from retrieved tables
        db_counts = {}
        for table in retrieved_schemas[:3]:  # Use top 3 tables
            db = table.db_name
            db_counts[db] = db_counts.get(db, 0) + 1

        # Get most common database
        if db_counts:
            detected_db = max(db_counts, key=db_counts.get)
            
            # Auto-switch if different from user's choice
            if detected_db != db_name:
                print(f"  ℹ️  Auto-detected database: {detected_db} (switching from {db_name})")
                db_name = detected_db
                
        # ========================================
        # STEP 3: RETRIEVAL EVALUATION
        # ========================================
        print(f"[3/7] Evaluating relevance...")
        eval_result = retrieval_evaluator.evaluate(user_question, retrieved_schemas)
        relevant_tables = eval_result.get_relevant_tables()
        print(f"  ✓ Filtered to {len(relevant_tables)} relevant tables")

        # ========================================
        # STEP 4: SQL GENERATION
        # ========================================
        print(f"[4/7] Generating SQL...")
        gen_result = sql_generator.generate(user_question, relevant_tables)
        
        if not gen_result.sql:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate SQL"
            )
        
        print(f"  ✓ SQL generated ({gen_result.generation_time_ms:.0f}ms)")
        print(f"  SQL: {gen_result.sql[:80]}...")
        
        # ========================================
        # STEP 5: SQL VALIDATION
        # ========================================
        print(f"[5/7] Validating SQL...")
        validation_result = sql_validator.validate_and_fix(gen_result.sql, user_question)
        
        if not validation_result.valid:
            return QueryResponse(
                question=user_question,
                sql=gen_result.sql,
                data=None,
                insights=None,
                row_count=0,
                execution_time_ms=(time.time() - start_time) * 1000,
                metadata={
                    "pipeline_stage": "sql_validation",
                    "database": db_name,
                    "validation_errors": validation_result.errors,
                    "validation_warnings": validation_result.warnings,
                    "error_message": "SQL validation failed"
                }
            )
        
        validated_sql = validation_result.sql
        print(f"  ✓ SQL validated ({validation_result.validation_time_ms:.0f}ms)")
        if validation_result.warnings:
            print(f"  ! {len(validation_result.warnings)} warnings")
        
        # ========================================
        # STEP 6: QUERY EXECUTION
        # ========================================
        print(f"[6/7] Executing query...")
        exec_result = query_executor.execute(validated_sql, db_name)

        if not exec_result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Query execution failed: {exec_result.error}"
            )

        print(f"  ✓ Query executed ({exec_result.execution_time_ms:.0f}ms)")
        print(f"  Rows: {exec_result.row_count}")

        # Get date context if no results and query involves dates
        date_context = None
        if exec_result.row_count == 0 and ('EXTRACT' in validated_sql.upper() or 'DATE' in validated_sql.upper()):
            if 'orders' in validated_sql.lower():
                date_context = get_date_context(db_name, 'orders', 'order_purchase_timestamp')
            elif 'payments' in validated_sql.lower():
                date_context = get_date_context(db_name, 'payments', 'payment_date') if 'payment_date' in validated_sql.lower() else None
            elif 'daily_metrics' in validated_sql.lower():
                date_context = get_date_context(db_name, 'daily_metrics', 'date')
            
            if date_context:
                print(f"  ! No data found, but available range: {date_context['earliest_date']} to {date_context['latest_date']}")

        # ========================================
        # STEP 7: INSIGHT GENERATION
        # ========================================
        print(f"[7/7] Generating insights...")

        # Add date context if available
        enhanced_query = user_question
        if date_context and exec_result.row_count == 0:
            context_info = f"\n\nAVAILABLE DATA PERIOD: {date_context['earliest_date']} to {date_context['latest_date']} ({date_context['total_records']} total records)"
            enhanced_query = f"{user_question}{context_info}"

        insight_result = insight_generator.generate(
            enhanced_query,
            validated_sql,
            exec_result.data,
            exec_result.row_count
        )
        
        print(f"  ✓ Insights generated ({insight_result.insight_generation_time_ms:.0f}ms)")
        
        # ========================================
        # FINAL RESPONSE
        # ========================================
        total_time_ms = (time.time() - start_time) * 1000
        print(f"\n✅ COMPLETE! Total: {total_time_ms:.0f}ms\n")
        
        return QueryResponse(
            question=user_question,
            sql=validated_sql,
            data=exec_result.data,
            insights=insight_result.insights,
            row_count=exec_result.row_count,
            execution_time_ms=total_time_ms,
            metadata={
                "pipeline_stage": "complete",
                "database": db_name,
                "intent": intent_result.intent.value,
                "intent_confidence": intent_result.confidence,
                "tables_retrieved": len(retrieved_schemas),
                "tables_used": len(relevant_tables),
                "validation_warnings": len(validation_result.warnings),
                "fixes_applied": len(validation_result.fixes_applied),
                "timing": {
                    "intent_classification_ms": intent_result.classification_time_ms,
                    "schema_retrieval_ms": retrieval_result.retrieval_time_ms,
                    "retrieval_evaluation_ms": eval_result.evaluation_time_ms,
                    "sql_generation_ms": gen_result.generation_time_ms,
                    "sql_validation_ms": validation_result.validation_time_ms,
                    "query_execution_ms": exec_result.execution_time_ms,
                    "insight_generation_ms": insight_result.insight_generation_time_ms,
                    "total_ms": total_time_ms
                }
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)