"""
FastAPI Application - Text-to-SQL Chatbot
Complete 7-agent pipeline using AgentState.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from src.models.agent_state import AgentState
from src.components.intent_classifier import IntentClassifier
from src.components.schema_retriever import SchemaRetriever
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.components.query_executor import QueryExecutor
from src.components.insight_generator import InsightGenerator
from src.utils.logger import setup_logger
from src.utils.exceptions import AgentExecutionError

logger = setup_logger(name="main")

# Initialize FastAPI
app = FastAPI(
    title="Text-to-SQL Chatbot API",
    description="AI-powered natural language to SQL with 7-agent pipeline",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize all agents
logger.info("Initializing agents...")

intent_classifier = IntentClassifier()
schema_retriever = SchemaRetriever()
retrieval_evaluator = RetrievalEvaluator()
sql_generator = SQLGenerator()
sql_validator = SQLValidator(enable_ai_validation=False)
query_executor = QueryExecutor()
insight_generator = InsightGenerator()

logger.info("All agents ready.")
logger.info("Pipeline: Intent → Retrieval → Evaluation → Generation → Validation → Execution → Insights")


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


# Routes
@app.get("/")
def root():
    return {
        "message": "Text-to-SQL Chatbot API v3.0",
        "pipeline": [
            "1. IntentClassifier",
            "2. SchemaRetriever",
            "3. RetrievalEvaluator",
            "4. SQLGenerator",
            "5. SQLValidator",
            "6. QueryExecutor",
            "7. InsightGenerator"
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
    agents = [
        intent_classifier,
        schema_retriever,
        retrieval_evaluator,
        sql_generator,
        sql_validator,
        query_executor,
        insight_generator
    ]
    return {
        "status": "healthy",
        "version": "3.0.0",
        "agents": {
            agent.name: {
                "status": "ready",
                "metrics": agent.get_metrics()
            }
            for agent in agents
        }
    }


@app.get("/databases")
def list_databases():
    try:
        all_tables = schema_retriever.get_all_tables()
        databases = list(set([
            t.split('.')[0] for t in all_tables if '.' in t
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
    Main endpoint: Run complete 7-agent pipeline.

    Each agent reads from and writes to AgentState.
    Pipeline stops early if query is ambiguous or an error occurs.
    """

    # Initialize state
    state = AgentState(
        query=request.question,
        database=request.database
    )

    try:
        # Step 1: Intent Classification
        state = intent_classifier.run(state)

        if state.needs_clarification:
            return QueryResponse(
                question=state.query,
                sql=None,
                data=None,
                insights=None,
                row_count=0,
                execution_time_ms=sum(state.timing.values()),
                metadata={
                    "pipeline_stage": "intent_classification",
                    "needs_clarification": True,
                    "clarification_reason": state.clarification_reason,
                    "intent": state.intent,
                    "suggestion": "Please provide more specific details."
                }
            )

        # Step 2: Schema Retrieval
        state = schema_retriever.run(state)

        # Step 3: Retrieval Evaluation
        state = retrieval_evaluator.run(state)

        # Step 4: SQL Generation
        state = sql_generator.run(state)

        # Step 5: SQL Validation
        state = sql_validator.run(state)

        # Step 6: Query Execution
        state = query_executor.run(state)

        # Step 7: Insight Generation
        state = insight_generator.run(state)

        # Return final response
        total_ms = sum(state.timing.values())

        return QueryResponse(
            question=state.query,
            sql=state.validated_sql,
            data=state.query_result,
            insights=state.insights,
            row_count=state.row_count,
            execution_time_ms=total_ms,
            metadata={
                "pipeline_stage": "complete",
                "database": state.database,
                "intent": state.intent,
                "tables_retrieved": len(state.retrieved_tables),
                "tables_used": len(state.evaluated_tables),
                "timing": state.timing,
                "errors": state.errors
            }
        )

    except AgentExecutionError as e:
        logger.error(f"Agent error at {e.agent_name}: {e.message}")
        raise HTTPException(
            status_code=500,
            detail={
                "agent": e.agent_name,
                "error": e.message,
                "details": e.details
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)