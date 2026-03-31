"""
LLMBaseAgent - Base class for all LLM-based agents.

Extends BaseAgent with Anthropic Claude client and _call_llm() method.
Only agents that use LLM should inherit this class.

Example:
    >>> class IntentClassifier(LLMBaseAgent):
    ...     def __init__(self):
    ...         super().__init__(name="intent_classifier", version="1.0")
    ...
    ...     def execute(self, state: AgentState) -> AgentState:
    ...         response = self._call_llm(prompt="classify: " + state.query)
    ...         state.intent = self._parse(response)
    ...         return state
"""

import os
from anthropic import Anthropic
from dotenv import load_dotenv

from src.core.base_agent import BaseAgent
from src.models.agent_state import AgentState
from src.utils.exceptions import LLMCallError

load_dotenv()


class LLMBaseAgent(BaseAgent):
    """
    Base class for agents that use Claude LLM.

    Extends BaseAgent with:
    - Anthropic client initialization
    - _call_llm() method for Claude API calls

    Attributes:
        client: Anthropic API client
        model: Claude model name

    Example:
        >>> class SQLGenerator(LLMBaseAgent):
        ...     def execute(self, state: AgentState) -> AgentState:
        ...         sql = self._call_llm(prompt=self._build_prompt(state))
        ...         state.sql = sql
        ...         return state
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        model: str = None,
        log_level: str = "INFO"
    ):
        """
        Initialize LLM base agent.

        Args:
            name: Agent name
            version: Agent version
            model: Claude model name (default from env or claude-sonnet-4-20250514)
            log_level: Logging level

        Raises:
            ValueError: If ANTHROPIC_API_KEY not found
        """
        super().__init__(name=name, version=version, log_level=log_level)

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY not found in .env file")

        self.client = Anthropic(api_key=api_key)
        self.model = model or os.getenv("LLM_MODEL", "claude-sonnet-4-20250514")

        self.log(f"LLM client initialized with model: {self.model}")

    def _call_llm(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0
    ) -> str:
        """
        Call Claude API and return response text.

        Args:
            prompt: Prompt string to send to Claude
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0 = deterministic)

        Returns:
            Response text from Claude

        Raises:
            LLMCallError: If API call fails

        Example:
            >>> response = self._call_llm(
            ...     prompt="Classify this query: berapa total customer?",
            ...     max_tokens=500,
            ...     temperature=0
            ... )
        """
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text.strip()

        except Exception as e:
            self.log(f"LLM call failed: {str(e)}", level="error")
            raise LLMCallError(
                agent_name=self.name,
                message=f"LLM call failed: {str(e)}"
            ) from e