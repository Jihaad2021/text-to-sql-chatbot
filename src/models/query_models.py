"""
Pydantic Models for Query Pipeline

Defines data structures used throughout the pipeline.
"""

from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from enum import Enum

class QueryIntent(str, Enum):
    SIMPLE_SELECT = "simple_select"
    FILTERED_QUERY = "filtered_query"
    AGGREGATION = "aggregation"
    MULTI_TABLE_JOIN = "multi_table_join"
    COMPLEX_ANALYTICS = "complex_analytics"
    AMBIGUOUS = "ambiguous"

# TODO: Add more models (IntentResult, RetrievedTable, etc.)
