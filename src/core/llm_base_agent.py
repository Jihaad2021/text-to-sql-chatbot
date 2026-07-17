"""
LLMBaseAgent - Base class for all LLM-based agents.

Supports multiple LLM providers:
- Anthropic Claude
- OpenAI GPT
- Groq (Llama, Mixtral)
- Google Gemini

Provider selection priority:
1. Per-agent config from .env (e.g. INTENT_CLASSIFIER_LLM)
2. DEFAULT_LLM from .env
3. Auto-detect from available API keys

Example .env configuration:
    # API Keys
    ANTHROPIC_API_KEY=sk-ant-...
    OPENAI_API_KEY=sk-...
    GROQ_API_KEY=gsk_...
    GEMINI_API_KEY=AIza...

    # Default for all agents
    DEFAULT_LLM=openai
    DEFAULT_MODEL=gpt-4o

    # Per-agent override (optional)
    INTENT_CLASSIFIER_LLM=groq
    INTENT_CLASSIFIER_MODEL=llama3-8b-8192
    SQL_GENERATOR_LLM=openai
    SQL_GENERATOR_MODEL=gpt-4o
"""

import os
from typing import TYPE_CHECKING, Any

from dotenv import load_dotenv

if TYPE_CHECKING:
    from src.models.agent_state import AgentState

from src.core.base_agent import BaseAgent
from src.core.config import Config
from src.utils.exceptions import LLMCallError

load_dotenv()

# Default models per provider
DEFAULT_MODELS = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "groq": "llama3-8b-8192",
    "gemini": "gemini-1.5-flash",
    "openrouter": "google/gemini-2.5-flash",
}

# Env key mapping per agent name
AGENT_ENV_KEYS = {
    "query_rewriter":         ("QUERY_REWRITER_LLM",         "QUERY_REWRITER_MODEL"),
    "intent_classifier":      ("INTENT_CLASSIFIER_LLM",      "INTENT_CLASSIFIER_MODEL"),
    "query_planner":          ("QUERY_PLANNER_LLM",          "QUERY_PLANNER_MODEL"),
    "retrieval_evaluator":    ("RETRIEVAL_EVALUATOR_LLM",    "RETRIEVAL_EVALUATOR_MODEL"),
    "sql_generator":          ("SQL_GENERATOR_LLM",          "SQL_GENERATOR_MODEL"),
    "sql_validator":          ("SQL_VALIDATOR_LLM",          "SQL_VALIDATOR_MODEL"),
    "analytical_investigator":("ANALYTICAL_INVESTIGATOR_LLM","ANALYTICAL_INVESTIGATOR_MODEL"),
    "insight_generator":      ("INSIGHT_GENERATOR_LLM",      "INSIGHT_GENERATOR_MODEL"),
    "response_planner":       ("RESPONSE_PLANNER_LLM",       "RESPONSE_PLANNER_MODEL"),
}

# API key env names per provider
API_KEY_ENV = {
    "anthropic":  "ANTHROPIC_API_KEY",
    "openai":     "OPENAI_API_KEY",
    "groq":       "GROQ_API_KEY",
    "gemini":     "GEMINI_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}


class LLMBaseAgent(BaseAgent):
    """
    Base class for agents that use LLM.

    Supports Anthropic, OpenAI, Groq, and Gemini.
    Provider and model can be configured per-agent via .env.

    Attributes:
        client: LLM API client
        model: Model name
        provider: Provider name ('anthropic', 'openai', 'groq', 'gemini')
    """

    def __init__(
        self,
        name: str,
        version: str = "1.0.0",
        model: str | None = None,
        log_level: str = "INFO",
    ) -> None:
        super().__init__(name=name, version=version, log_level=log_level)

        self.provider, self.client, self.model = self._init_client(
            agent_name=name,
            model_override=model,
        )

        # Token usage from the most recent provider call — set by each _call_* method.
        # Read immediately after _call_llm() returns; never rely on it after another call.
        self._last_usage: dict | None = None

        self.log(f"LLM provider: {self.provider}, model: {self.model}")

    def _init_client(self, agent_name: str, model_override: str | None = None) -> tuple[str, Any, str]:
        """
        Initialize LLM client based on .env configuration.

        Priority:
        1. Per-agent config (e.g. INTENT_CLASSIFIER_LLM)
        2. DEFAULT_LLM
        3. Auto-detect from available API keys

        Returns:
            Tuple of (provider, client, model)
        """
        # Step 1: Get provider from per-agent config or default
        provider = self._resolve_provider(agent_name)

        # Step 2: Get model
        model = model_override or self._resolve_model(agent_name, provider)

        # Step 3: Initialize client
        client = self._create_client(provider)

        return provider, client, model

    def _resolve_provider(self, agent_name: str) -> str:
        """Resolve provider for this agent."""
        # Check per-agent config
        if agent_name in AGENT_ENV_KEYS:
            llm_key, _ = AGENT_ENV_KEYS[agent_name]
            agent_provider = os.getenv(llm_key, "").lower()
            if agent_provider and agent_provider in DEFAULT_MODELS:
                return agent_provider

        # Check DEFAULT_LLM
        default_provider = Config.DEFAULT_LLM.lower()
        if default_provider and default_provider in DEFAULT_MODELS:
            return default_provider

        # Auto-detect from available API keys
        for provider, env_key in API_KEY_ENV.items():
            if os.getenv(env_key):
                return provider

        raise ValueError(
            "No LLM provider configured. "
            "Set DEFAULT_LLM or at least one API key "
            "(ANTHROPIC_API_KEY, OPENAI_API_KEY, GROQ_API_KEY, GEMINI_API_KEY) in .env"
        )

    def _resolve_model(self, agent_name: str, provider: str) -> str:
        """Resolve model for this agent."""
        # Check per-agent model config
        if agent_name in AGENT_ENV_KEYS:
            _, model_key = AGENT_ENV_KEYS[agent_name]
            agent_model = os.getenv(model_key, "")
            if agent_model:
                return agent_model

        # Check DEFAULT_MODEL
        if Config.DEFAULT_MODEL:
            return Config.DEFAULT_MODEL

        # Use provider default
        return DEFAULT_MODELS[provider]

    def _create_client(self, provider: str) -> Any:
        """Create LLM client for the given provider."""
        api_key = os.getenv(API_KEY_ENV[provider])

        if not api_key:
            raise ValueError(
                f"API key for provider '{provider}' not found. "
                f"Set {API_KEY_ENV[provider]} in .env"
            )

        if provider == "anthropic":
            from anthropic import Anthropic
            return Anthropic(api_key=api_key)

        elif provider == "openai":
            from openai import OpenAI
            return OpenAI(api_key=api_key)

        elif provider == "groq":
            from groq import Groq
            return Groq(api_key=api_key)

        elif provider == "gemini":
            from openai import OpenAI
            return OpenAI(
                api_key=api_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
            )

        elif provider == "openrouter":
            from openai import OpenAI
            return OpenAI(
                api_key=api_key,
                base_url="https://openrouter.ai/api/v1",
            )

        else:
            raise ValueError(f"Unsupported provider: {provider}")

    def _call_llm(
        self,
        prompt: str,
        max_tokens: int = 1000,
        temperature: float = 0,
        use_thinking: bool = False,
        model: str | None = None,
    ) -> str:
        """
        Call LLM API and return response text.

        Automatically routes to correct provider.

        Args:
            prompt: Prompt string
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature (0 = deterministic)
            use_thinking: Enable extended thinking (Anthropic only)

        Returns:
            Response text

        Raises:
            LLMCallError: If API call fails
        """
        try:
            if self.provider == "anthropic":
                return self._call_anthropic(prompt, max_tokens, temperature, use_thinking, model=model)
            elif self.provider in ("openai", "openrouter"):
                return self._call_openai(prompt, max_tokens, temperature, use_thinking, model=model)
            elif self.provider in ("gemini",):
                return self._call_openai(prompt, max_tokens, temperature, model=model)
            elif self.provider == "groq":
                return self._call_groq(prompt, max_tokens, temperature, model=model)
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

    def _call_anthropic(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        use_thinking: bool = False,
        model: str | None = None,
    ) -> str:
        """Call Anthropic Claude API, optionally with extended thinking."""
        # Thinking requires budget_tokens < max_tokens; no temperature allowed
        _THINKING_BUDGET = 8000
        kwargs: dict = {
            "model":    model or self.model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if use_thinking:
            kwargs["max_tokens"] = max(max_tokens, _THINKING_BUDGET + 4000)
            kwargs["thinking"]   = {"type": "enabled", "budget_tokens": _THINKING_BUDGET}
        else:
            kwargs["max_tokens"]  = max_tokens
            kwargs["temperature"] = temperature

        response = self.client.messages.create(**kwargs)
        if response.usage:
            self._last_usage = {
                "prompt_tokens":     response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens":      response.usage.input_tokens + response.usage.output_tokens,
            }
        # Response may contain thinking blocks + text blocks — return text only
        return next(
            (b.text.strip() for b in response.content if b.type == "text"), ""
        )

    # OpenAI reasoning model prefixes — these require different API params
    _OPENAI_REASONING_PREFIXES = ("o1", "o3", "o4")

    def _is_openai_reasoning_model(self, model: str) -> bool:
        return any(model.startswith(p) for p in self._OPENAI_REASONING_PREFIXES)

    def _call_openai(
        self,
        prompt: str,
        max_tokens: int,
        temperature: float,
        use_thinking: bool = False,
        model: str | None = None,
    ) -> str:
        """Call OpenAI GPT API, optionally routing to a reasoning model."""
        effective_model = model or self.model
        if use_thinking:
            # Switch to reasoning model for complex intents
            reasoning_model = "o4-mini"
            response = self.client.chat.completions.create(
                model=reasoning_model,
                max_completion_tokens=max(max_tokens, 8000),
                reasoning_effort="high",
                messages=[{"role": "user", "content": prompt}],
            )
            self.log(f"OpenAI reasoning model used: {reasoning_model}")
        elif self._is_openai_reasoning_model(effective_model):
            # Configured model is already a reasoning model — use its native params
            response = self.client.chat.completions.create(
                model=effective_model,
                max_completion_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        else:
            response = self.client.chat.completions.create(
                model=effective_model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[{"role": "user", "content": prompt}],
            )
        if response.usage:
            self._last_usage = {
                "prompt_tokens":     response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens":      response.usage.total_tokens,
            }
        return response.choices[0].message.content.strip()

    def _call_groq(self, prompt: str, max_tokens: int, temperature: float, model: str | None = None) -> str:
        """Call Groq API (same interface as OpenAI)."""
        response = self.client.chat.completions.create(
            model=model or self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        if response.usage:
            self._last_usage = {
                "prompt_tokens":     response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens":      response.usage.total_tokens,
            }
        return response.choices[0].message.content.strip()

    def _record_token_usage(
        self,
        state: "AgentState",
        *,
        model: str,
        iteration: int | None = None,
    ) -> None:
        """Read self._last_usage and INSERT one row into token_usage_log. Never raises."""
        if not self._last_usage:
            return
        from src.core.token_logger import log_token_usage
        log_token_usage(
            request_id=getattr(state, "request_id", None) or "unknown",
            session_id=getattr(state, "session_id", None),
            agent_name=self.name,
            model=model,
            quality_tier=getattr(state, "quality_tier", "standard"),
            prompt_tokens=self._last_usage.get("prompt_tokens", 0),
            completion_tokens=self._last_usage.get("completion_tokens", 0),
            total_tokens=self._last_usage.get("total_tokens", 0),
            iteration=iteration,
        )

    def _call_gemini(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """Call Google Gemini via OpenAI-compatible API."""
        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content.strip()
