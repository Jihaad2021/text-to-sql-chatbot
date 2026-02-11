"""
Response Models

Defines API response structures.
"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class QueryResponse(BaseModel):
    """Final response to user"""
    insights: str
    sql: Optional[str] = None
    data: Optional[List[Dict[str, Any]]] = None
    metadata: Dict[str, Any]

# TODO: Add ErrorResponse model
