"""
LLMBaseAgent - Base class for all LLM-based agents.

Auto-detects LLM provider from environment variables:
- If ANTHROPIC_API_KEY is set → use Anthropic Claude
- If OPENAI_API_KEY is set → use OpenAI GPT
- If both are set → Anthropic takes priority

Set LLM_MODEL in .env to override default model.

Example .env:
    # Use Anthropic
    ANTHROPIC_API_KEY=sk-ant-...
    LLM_MODEL=claude-sonnet-4-20250514  # optional

    # Use OpenAI
    OPENAI_API_KEY=sk-...
    LLM_MODEL=gpt-4o-mini  # optional

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
from dotenv import load_dotenv

from src.core.base_agent import BaseAgent
from src.models.agent_state import AgentState
from src.utils.exceptions import LLMCallError

load_dotenv()

# Default models per provider
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o-mini"
}


class LLMBaseAgent(BaseAgent):
    """
    Base class for agents that use LLM.

    Auto-detects provider from .env:
    - ANTHROPIC_API_KEY → Anthropic Claude
    - OPENAI_API_KEY    → OpenAI GPT

    Attributes:
        client: LLM API client (Anthropic or OpenAI)
        model: Model name
        provider: 'anthropic' or 'openai'
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        model: str = None,
        log_level: str = "INFO"
    ):
        """
        Initialize LLM base agent with auto-detected provider.

        Args:
            name: Agent name
            version: Agent version
            model: Override model name (default from env or provider default)
            log_level: Logging level

        Raises:
            ValueError: If no LLM API key found in .env
        """
        super().__init__(name=name, version=version, log_level=log_level)

        self.provider, self.client = self._init_client()
        self.model = model or os.getenv("LLM_MODEL", DEFAULT_MODELS[self.provider])

        self.log(f"LLM provider: {self.provider}, model: {self.model}")

    def _init_client(self) -> tuple:
        """
        Auto-detect and initialize LLM client from environment variables.

        Priority: Anthropic > OpenAI

        Returns:
            Tuple of (provider_name, client_instance)

        Raises:
            ValueError: If no API key found
        """
        anthropic_key = os.getenv("ANTHROPIC_API_KEY")
        openai_key = os.getenv("OPENAI_API_KEY")

        if anthropic_key:
            from anthropic import Anthropic
            return "anthropic", Anthropic(api_key=anthropic_key)

        elif openai_key:
            from openai import OpenAI
            return "openai", OpenAI(api_key=openai_key)

        else:
            raise ValueError(
                "No LLM API key found. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY in .env file."
            )

    def _call_llm(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0
    ) -> str:
        """
        Call LLM API and return response text.

        Automatically uses the detected provider (Anthropic or OpenAI).

        Args:
            prompt: Prompt string to send to LLM
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0 = deterministic)

        Returns:
            Response text from LLM

        Raises:
            LLMCallError: If API call fails
        """
        try:
            if self.provider == "anthropic":
                return self._call_anthropic(prompt, max_tokens, temperature)
            elif self.provider == "openai":
                return self._call_openai(prompt, max_tokens, temperature)
            else:
                raise LLMCallError(
                    agent_name=self.name,
                    message=f"Unknown provider: {self.provider}"
                )

        except LLMCallError:
            raise
        except Exception as e:
            self.log(f"LLM call failed: {str(e)}", level="error")
            raise LLMCallError(
                agent_name=self.name,
                message=f"LLM call failed: {str(e)}"
            ) from e

    def _call_anthropic(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Call Anthropic Claude API."""
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()

    def _call_openai(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Call OpenAI GPT API."""
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()