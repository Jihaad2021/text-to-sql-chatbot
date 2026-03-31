"""
BaseAgent - Abstract base class for all agents.

All agents in the pipeline must inherit from this class.
Provides: logging, metrics tracking, error handling.

Non-LLM agents (SchemaRetriever, QueryExecutor) inherit this directly.
LLM agents inherit LLMBaseAgent which extends this class.

Example:
    >>> class SchemaRetriever(BaseAgent):
    ...     def __init__(self):
    ...         super().__init__(name="schema_retriever", version="1.0")
    ...
    ...     def execute(self, state: AgentState) -> AgentState:
    ...         state.retrieved_tables = self._retrieve(state.query)
    ...         return state
"""

import time
from abc import ABC, abstractmethod
from typing import Dict, Any
from datetime import datetime

from src.models.agent_state import AgentState
from src.utils.logger import setup_logger
from src.utils.exceptions import AgentExecutionError


class BaseAgent(ABC):
    """
    Abstract base class for all agents.

    Provides:
    - Standardized execute() interface
    - run() wrapper with metrics & error handling
    - Integrated logging
    - Performance metrics

    Attributes:
        name: Agent identifier
        version: Agent version
        logger: Logger instance
        metrics: Performance tracking dictionary
    """

    def __init__(self, name: str, version: str = "1.0.0", log_level: str = "INFO"):
        """
        Initialize base agent.

        Args:
            name: Agent name (e.g., 'intent_classifier')
            version: Agent version string
            log_level: Logging level
        """
        self.name = name
        self.version = version
        self.logger = setup_logger(name=f"agent.{name}", level=log_level)

        self.metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time_seconds": 0.0,
            "average_time_seconds": 0.0,
            "last_execution_time": None,
            "created_at": datetime.now().isoformat()
        }

        self.log(f"Agent '{name}' (v{version}) initialized", level="debug")

    @abstractmethod
    def execute(self, state: AgentState) -> AgentState:
        """
        Execute agent logic and return updated state.

        Must be implemented by all subclasses.
        Read inputs from state, write outputs to state, return state.

        Args:
            state: Current pipeline state

        Returns:
            Updated pipeline state

        Example:
            >>> def execute(self, state: AgentState) -> AgentState:
            ...     state.intent = self._classify(state.query)
            ...     return state
        """
        pass

    def run(self, state: AgentState) -> AgentState:
        """
        Run agent with automatic metrics tracking and error handling.

        Call this instead of execute() directly.

        Args:
            state: Current pipeline state

        Returns:
            Updated pipeline state

        Raises:
            AgentExecutionError: If execution fails
        """
        start_time = time.time()
        state.current_stage = self.name

        try:
            self.log(f"Executing with query: {state.query[:50]}...")

            updated_state = self.execute(state)

            execution_time = time.time() - start_time
            updated_state.add_timing(self.name, execution_time * 1000)
            self._update_metrics(success=True, execution_time=execution_time)

            self.log(f"Completed in {execution_time:.2f}s")

            return updated_state

        except Exception as e:
            execution_time = time.time() - start_time
            self._update_metrics(success=False, execution_time=execution_time)

            self.log(f"Failed after {execution_time:.2f}s: {str(e)}", level="error")

            state.add_error(f"[{self.name}] {str(e)}")

            if isinstance(e, AgentExecutionError):
                raise
            raise AgentExecutionError(
                agent_name=self.name,
                message=str(e),
                details={
                    "execution_time": execution_time,
                    "query": state.query,
                    "original_error": type(e).__name__
                }
            ) from e

    def log(self, message: str, level: str = "info") -> None:
        """
        Log message with agent context.

        Args:
            message: Log message
            level: Log level ('debug', 'info', 'warning', 'error')
        """
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(f"[{self.name}] {message}")

    def _update_metrics(self, success: bool, execution_time: float) -> None:
        """Update agent performance metrics."""
        self.metrics["total_calls"] += 1

        if success:
            self.metrics["successful_calls"] += 1
        else:
            self.metrics["failed_calls"] += 1

        self.metrics["total_time_seconds"] += execution_time
        self.metrics["average_time_seconds"] = (
            self.metrics["total_time_seconds"] / self.metrics["total_calls"]
        )
        self.metrics["last_execution_time"] = execution_time

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get current agent performance metrics.

        Returns:
            Dictionary with metrics including success rate and timing.
        """
        success_rate = 0.0
        if self.metrics["total_calls"] > 0:
            success_rate = (
                self.metrics["successful_calls"] / self.metrics["total_calls"]
            ) * 100

        return {
            "agent_name": self.name,
            "agent_version": self.version,
            "total_calls": self.metrics["total_calls"],
            "successful_calls": self.metrics["successful_calls"],
            "failed_calls": self.metrics["failed_calls"],
            "success_rate": round(success_rate, 2),
            "total_time_seconds": round(self.metrics["total_time_seconds"], 2),
            "average_time_seconds": round(self.metrics["average_time_seconds"], 3),
            "last_execution_time": self.metrics["last_execution_time"],
            "created_at": self.metrics["created_at"]
        }

    def reset_metrics(self) -> None:
        """Reset all metrics to initial state."""
        created_at = self.metrics["created_at"]
        self.metrics = {
            "total_calls": 0,
            "successful_calls": 0,
            "failed_calls": 0,
            "total_time_seconds": 0.0,
            "average_time_seconds": 0.0,
            "last_execution_time": None,
            "created_at": created_at
        }
        self.log("Metrics reset", level="debug")

    def get_info(self) -> Dict[str, str]:
        """Get agent metadata."""
        return {
            "name": self.name,
            "version": self.version,
            "class": self.__class__.__name__
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"name='{self.name}', "
            f"version='{self.version}', "
            f"calls={self.metrics['total_calls']})"
        )

    def __str__(self) -> str:
        return f"{self.name} (v{self.version})"