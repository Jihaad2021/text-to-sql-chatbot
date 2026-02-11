"""
FastAPI Application - Text-to-SQL Chatbot

Main API server that orchestrates the SQL generation and execution pipeline.
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import time

# Import our components
from src.components.sql_generator import SQLGenerator, RetrievedTable
from src.components.query_executor import QueryExecutor

# Initialize FastAPI
app = FastAPI(
    title="Text-to-SQL Chatbot API",
    description="Convert natural language questions to SQL queries and execute them",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize components (on startup)
print("\n" + "="*60)
print("INITIALIZING TEXT-TO-SQL CHATBOT API")
print("="*60 + "\n")

sql_generator = SQLGenerator()
query_executor = QueryExecutor()

print("\n✅ API Ready!\n")

# Request/Response models
class QueryRequest(BaseModel):
    question: str
    database: Optional[str] = "sales_db"

class QueryResponse(BaseModel):
    question: str
    sql: str
    data: Optional[List[Dict[str, Any]]]
    row_count: int
    execution_time_ms: float
    metadata: Dict[str, Any]

class ErrorResponse(BaseModel):
    error: str
    details: Optional[str] = None

# Mock schema (for now - later we'll use Component 2)
MOCK_SCHEMAS = {
    'sales_db': [
        RetrievedTable(
            db_name='sales_db',
            table_name='customers',
            columns=['customer_id', 'customer_name', 'customer_email', 'customer_city', 'customer_state', 'customer_zip_code', 'customer_created_at'],
            description='Customer master data including buyer information, contact details, and location',
            relationships=['Referenced by orders.customer_id (1:N)']
        ),
        RetrievedTable(
            db_name='sales_db',
            table_name='orders',
            columns=['order_id', 'customer_id', 'order_status', 'order_purchase_timestamp', 'order_approved_at', 'order_delivered_timestamp', 'order_estimated_delivery_date'],
            description='Sales transactions, purchase records, order history with dates and status',
            relationships=['FK to customers.customer_id', 'Referenced by payments.order_id (1:1)']
        ),
        RetrievedTable(
            db_name='sales_db',
            table_name='payments',
            columns=['payment_id', 'order_id', 'payment_sequential', 'payment_type', 'payment_installments', 'payment_value'],
            description='Payment transactions and revenue data. Use payment_value for revenue calculations.',
            relationships=['FK to orders.order_id']
        )
    ],
    'products_db': [
        RetrievedTable(
            db_name='products_db',
            table_name='products',
            columns=['product_id', 'product_category_name', 'product_name_length', 'product_description_length', 'product_photos_qty', 'product_weight_g', 'product_length_cm', 'product_height_cm', 'product_width_cm'],
            description='Product catalog with item details and dimensions',
            relationships=['Referenced by order_items.product_id (1:N)']
        ),
        RetrievedTable(
            db_name='products_db',
            table_name='sellers',
            columns=['seller_id', 'seller_zip_code', 'seller_city', 'seller_state'],
            description='Seller/vendor information and location',
            relationships=['Referenced by order_items.seller_id (1:N)']
        ),
        RetrievedTable(
            db_name='products_db',
            table_name='order_items',
            columns=['order_id', 'order_item_id', 'product_id', 'seller_id', 'shipping_limit_date', 'price', 'freight_value'],
            description='Order line items linking orders to products and sellers',
            relationships=['FK to products.product_id', 'FK to sellers.seller_id', 'order_id references sales_db.orders (cross-DB)']
        )
    ],
    'analytics_db': [
        RetrievedTable(
            db_name='analytics_db',
            table_name='customer_segments',
            columns=['customer_id', 'rfm_score', 'segment', 'lifetime_value', 'total_orders', 'avg_order_value', 'last_purchase_date', 'updated_at'],
            description='Customer segmentation and RFM analysis (VIP, Regular, Occasional)',
            relationships=['customer_id references sales_db.customers (cross-DB)']
        ),
        RetrievedTable(
            db_name='analytics_db',
            table_name='daily_metrics',
            columns=['date', 'total_sales', 'total_orders', 'avg_order_value', 'new_customers', 'returning_customers'],
            description='Daily aggregated business metrics and KPIs',
            relationships=[]
        )
    ]
}

# Routes
@app.get("/")
def root():
    """Root endpoint"""
    return {
        "message": "Text-to-SQL Chatbot API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "query": "/query (POST)",
            "docs": "/docs"
        }
    }

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "components": {
            "sql_generator": "ready",
            "query_executor": "ready"
        }
    }

@app.post("/query", response_model=QueryResponse)
async def process_query(request: QueryRequest):
    """
    Main endpoint: Process natural language query.
    
    Args:
        request: QueryRequest with question and optional database
    
    Returns:
        QueryResponse with SQL, data, and metadata
    """
    start_time = time.time()
    
    try:
        user_question = request.question
        db_name = request.database
        
        # Validate database
        if db_name not in MOCK_SCHEMAS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid database. Available: {list(MOCK_SCHEMAS.keys())}"
            )
        
        # Get schemas for this database
        schemas = MOCK_SCHEMAS[db_name]
        
        # Step 1: Generate SQL
        gen_result = sql_generator.generate(user_question, schemas)
        
        if not gen_result.sql:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate SQL"
            )
        
        # Step 2: Execute SQL
        exec_result = query_executor.execute(gen_result.sql, db_name)
        
        if not exec_result.success:
            raise HTTPException(
                status_code=500,
                detail=f"Query execution failed: {exec_result.error}"
            )
        
        # Calculate total time
        total_time_ms = (time.time() - start_time) * 1000
        
        # Build response
        return QueryResponse(
            question=user_question,
            sql=gen_result.sql,
            data=exec_result.data,
            row_count=exec_result.row_count,
            execution_time_ms=total_time_ms,
            metadata={
                "database": db_name,
                "sql_generation_time_ms": gen_result.generation_time_ms,
                "query_execution_time_ms": exec_result.execution_time_ms,
                "total_time_ms": total_time_ms,
                "tables_used": [t.table_name for t in schemas]
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected error: {str(e)}"
        )

@app.get("/databases")
def list_databases():
    """List available databases"""
    return {
        "databases": list(MOCK_SCHEMAS.keys()),
        "default": "sales_db"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)