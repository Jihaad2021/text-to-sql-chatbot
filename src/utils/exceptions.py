"""
Custom Exceptions

Centralized exception definitions for all agents and components.

Example:
    >>> from src.utils.exceptions import AgentExecutionError
    >>> raise AgentExecutionError(agent_name="intent_classifier", message="Failed")
"""

from typing import Optional, Dict, Any


class AgentExecutionError(Exception):
    """
    Raised when an agent fails during execution.

    Attributes:
        agent_name: Name of the agent that failed
        message: Error description
        details: Additional context about the failure

    Example:
        >>> raise AgentExecutionError(
        ...     agent_name="sql_generator",
        ...     message="Failed to generate SQL",
        ...     details={"query": "berapa total customer?"}
        ... )
    """

    def __init__(
        self,
        agent_name: str,
        message: str,
        details: Optional[Dict[str, Any]] = None
    ):
        self.agent_name = agent_name
        self.message = message
        self.details = details or {}
        super().__init__(f"[{agent_name}] {message}")


class LLMCallError(AgentExecutionError):
    """Raised when Claude API call fails."""
    pass


class IntentClassificationError(AgentExecutionError):
    """Raised when intent classification fails."""
    pass


class SchemaRetrievalError(AgentExecutionError):
    """Raised when schema retrieval from ChromaDB fails."""
    pass


class RetrievalEvaluationError(AgentExecutionError):
    """Raised when retrieval evaluation fails."""
    pass


class SQLGenerationError(AgentExecutionError):
    """Raised when SQL generation fails."""
    pass


class SQLValidationError(AgentExecutionError):
    """Raised when SQL validation fails."""
    pass


class QueryExecutionError(AgentExecutionError):
    """Raised when query execution fails."""
    pass


class InsightGenerationError(AgentExecutionError):
    """Raised when insight generation fails."""
    pass