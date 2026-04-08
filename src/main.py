"""
FastAPI Application - Text-to-SQL Chatbot
Complete 7-agent pipeline using AgentState.
"""

import os
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

load_dotenv()

from src.components.insight_generator import InsightGenerator
from src.components.intent_classifier import IntentClassifier
from src.components.query_executor import QueryExecutor
from src.components.retrieval_evaluator import RetrievalEvaluator
from src.components.schema_retriever import SchemaRetriever
from src.components.sql_generator import SQLGenerator
from src.components.sql_validator import SQLValidator
from src.core.config import Config
from src.core.pipeline import TextToSQLPipeline
from src.core.startup import validate_environment
from src.models.agent_state import AgentState
from src.utils.exceptions import AgentExecutionError
from src.utils.logger import setup_logger

logger = setup_logger(name="main")

limiter = Limiter(key_func=get_remote_address)

pipeline: TextToSQLPipeline


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown lifecycle."""
    global pipeline

    validate_environment()

    logger.info("Initializing pipeline...")
    pipeline = TextToSQLPipeline(
        intent_classifier=IntentClassifier(),
        schema_retriever=SchemaRetriever(),
        retrieval_evaluator=RetrievalEvaluator(),
        sql_generator=SQLGenerator(),
        sql_validator=SQLValidator(enable_ai_validation=Config.ENABLE_AI_VALIDATION),
        query_executor=QueryExecutor(),
        insight_generator=InsightGenerator(),
    )
    logger.info(
        "Pipeline ready — "
        "Intent → Retrieval → Evaluation → Generation → Validation → Execution → Insights"
    )

    yield

    logger.info("Shutting down — closing database connections...")
    pipeline.close()


# ─────────────────────────────────────────────
# APP
# ─────────────────────────────────────────────

app = FastAPI(
    title="Text-to-SQL Chatbot API",
    description="AI-powered natural language to SQL with 7-agent pipeline",
    version="3.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8501").split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Authorization"],
)


# ─────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────

_ALLOWED_DATABASES = set(Config.DB_URLS.keys())


class QueryRequest(BaseModel):
    question: str
    database: str = "sales_db"

    @field_validator("question")
    @classmethod
    def question_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 3:
            raise ValueError("question must be at least 3 characters")
        return v

    @field_validator("database")
    @classmethod
    def database_must_be_known(cls, v: str) -> str:
        if v not in _ALLOWED_DATABASES:
            raise ValueError(
                f"Unknown database '{v}'. Allowed values: {sorted(_ALLOWED_DATABASES)}"
            )
        return v


class QueryResponse(BaseModel):
    question: str
    sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    insights: Optional[str] = None
    row_count: int
    execution_time_ms: float
    metadata: Dict[str, Any]


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.get("/")
def root() -> dict:
    return {
        "message": "Text-to-SQL Chatbot API v3.0",
        "pipeline": [
            "1. IntentClassifier",
            "2. SchemaRetriever",
            "3. RetrievalEvaluator",
            "4. SQLGenerator",
            "5. SQLValidator",
            "6. QueryExecutor",
            "7. InsightGenerator",
        ],
        "endpoints": {
            "health": "/health",
            "query": "/query (POST)",
            "databases": "/databases",
            "docs": "/docs",
        },
    }


@app.get("/health")
def health_check() -> JSONResponse:
    """
    Deep health check — verifies actual connectivity to databases and ChromaDB.
    Returns HTTP 200 if all critical components are healthy, 503 if degraded.
    """
    health = pipeline.check_health()
    status = "healthy" if health["overall_healthy"] else "degraded"

    return JSONResponse(
        status_code=200 if health["overall_healthy"] else 503,
        content={
            "status": status,
            "version": "3.0.0",
            "databases": health["databases"],
            "retrieval": health["retrieval"],
            "agents": health["agents"],
        },
    )


@app.get("/databases")
def list_databases() -> dict:
    try:
        all_tables = pipeline.get_all_tables()
        databases = sorted({t.split(".")[0] for t in all_tables if "." in t})
        return {
            "databases": databases,
            "default": databases[0] if databases else "sales_db",
            "total_tables": len(all_tables),
        }
    except Exception as e:
        return {
            "databases": sorted(_ALLOWED_DATABASES),
            "default": "sales_db",
            "error": str(e),
        }


@app.post("/query", response_model=QueryResponse)
@limiter.limit(f"{Config.RATE_LIMIT_PER_MINUTE}/minute")
async def process_query(request: Request, body: QueryRequest) -> QueryResponse:
    """
    Main endpoint: Run the complete 7-agent pipeline.

    Rate limited to RATE_LIMIT_PER_MINUTE requests per IP per minute.
    """
    request_id = str(uuid.uuid4())
    state = AgentState(query=body.question, database=body.database)

    try:
        state = pipeline.run(state)

        total_ms = sum(state.timing.values()) * 1000

        if state.needs_clarification:
            logger.info(
                "query needs clarification",
                extra={"request_id": request_id, "database": body.database, "success": False},
            )
            return QueryResponse(
                question=state.query,
                row_count=0,
                execution_time_ms=total_ms,
                metadata={
                    "request_id": request_id,
                    "pipeline_stage": "intent_classification",
                    "needs_clarification": True,
                    "clarification_reason": state.clarification_reason,
                    "intent": state.intent,
                    "suggestion": "Please provide more specific details.",
                },
            )

        logger.info(
            "query completed",
            extra={
                "request_id": request_id,
                "database": state.database,
                "intent": state.intent,
                "row_count": state.row_count,
                "execution_time_ms": round(total_ms, 1),
                "success": True,
            },
        )

        return QueryResponse(
            question=state.query,
            sql=state.validated_sql,
            data=state.query_result,
            insights=state.insights,
            row_count=state.row_count,
            execution_time_ms=total_ms,
            metadata={
                "request_id": request_id,
                "pipeline_stage": "complete",
                "database": state.database,
                "intent": state.intent,
                "tables_retrieved": len(state.retrieved_tables),
                "tables_used": len(state.evaluated_tables),
                "timing": state.timing,
                "errors": state.errors,
            },
        )

    except AgentExecutionError as e:
        logger.error(
            "agent error",
            extra={"request_id": request_id, "agent": e.agent_name, "error": e.message},
        )
        raise HTTPException(
            status_code=500,
            detail={"request_id": request_id, "agent": e.agent_name, "error": e.message},
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error("unexpected error", extra={"request_id": request_id, "error": str(e)})
        raise HTTPException(
            status_code=500,
            detail={"request_id": request_id, "error": "Internal server error"},
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
