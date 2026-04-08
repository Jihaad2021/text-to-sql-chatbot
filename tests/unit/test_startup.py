"""
Unit tests for startup.validate_environment().

Tests cover:
- Passes with all required vars set
- Fails if no LLM API key at all
- Fails if no database URL at all
- Fails if DEFAULT_LLM missing
- Fails if DEFAULT_MODEL missing
- Warns (does not fail) when OPENAI_API_KEY absent but other LLM key present
- Warns (does not fail) when some DB URLs missing but at least one present
"""

import logging
import os

import pytest

from src.core.startup import validate_environment

# Minimal env that satisfies all requirements
_FULL_ENV = {
    "ANTHROPIC_API_KEY": "sk-ant-test",
    "OPENAI_API_KEY": "sk-test",
    "SALES_DB_URL": "postgresql://user:pass@localhost/sales",
    "PRODUCTS_DB_URL": "postgresql://user:pass@localhost/products",
    "ANALYTICS_DB_URL": "postgresql://user:pass@localhost/analytics",
    "DEFAULT_LLM": "openai",
    "DEFAULT_MODEL": "gpt-4o",
}

# Keys that must not appear in the env for specific failure tests
_ALL_LLM_KEYS = ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"]
_ALL_DB_KEYS = ["SALES_DB_URL", "PRODUCTS_DB_URL", "ANALYTICS_DB_URL"]


def _env_without(*keys: str) -> dict:
    """Return _FULL_ENV with specific keys removed."""
    return {k: v for k, v in _FULL_ENV.items() if k not in keys}


# ========================================
# Test: Happy path
# ========================================

class TestPassesWhenValid:

    def test_all_vars_set(self, monkeypatch):
        """Should not raise when all required env vars are present."""
        for k, v in _FULL_ENV.items():
            monkeypatch.setenv(k, v)
        validate_environment()  # must not raise

    def test_single_llm_key_sufficient(self, monkeypatch):
        """Only one LLM key is needed."""
        env = _env_without("OPENAI_API_KEY")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        validate_environment()  # must not raise

    def test_single_db_url_sufficient(self, monkeypatch):
        """Only one DB URL is needed."""
        env = _env_without("PRODUCTS_DB_URL", "ANALYTICS_DB_URL")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("PRODUCTS_DB_URL", raising=False)
        monkeypatch.delenv("ANALYTICS_DB_URL", raising=False)
        validate_environment()  # must not raise


# ========================================
# Test: Failures
# ========================================

class TestFailsOnMissingCritical:

    def test_fails_if_no_llm_key(self, monkeypatch):
        """Should raise EnvironmentError if no LLM key is set."""
        env = _env_without(*_ALL_LLM_KEYS)
        for k in _ALL_LLM_KEYS:
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)

        with pytest.raises(EnvironmentError, match="Missing required"):
            validate_environment()

    def test_fails_if_no_db_url(self, monkeypatch):
        """Should raise EnvironmentError if no DB URL is set."""
        env = _env_without(*_ALL_DB_KEYS)
        for k in _ALL_DB_KEYS:
            monkeypatch.delenv(k, raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, v)

        with pytest.raises(EnvironmentError, match="Missing required"):
            validate_environment()

    def test_fails_if_default_llm_missing(self, monkeypatch):
        """Should raise EnvironmentError if DEFAULT_LLM is not set."""
        env = _env_without("DEFAULT_LLM")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("DEFAULT_LLM", raising=False)

        with pytest.raises(EnvironmentError, match="Missing required"):
            validate_environment()

    def test_fails_if_default_model_missing(self, monkeypatch):
        """Should raise EnvironmentError if DEFAULT_MODEL is not set."""
        env = _env_without("DEFAULT_MODEL")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("DEFAULT_MODEL", raising=False)

        with pytest.raises(EnvironmentError, match="Missing required"):
            validate_environment()


# ========================================
# Test: Warnings (not failures)
# ========================================

class TestWarnsOnDegradedMode:

    def test_warns_when_openai_key_absent(self, monkeypatch, caplog):
        """Missing OPENAI_API_KEY should warn (ChromaDB degraded) but not fail."""
        env = _env_without("OPENAI_API_KEY")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)

        with caplog.at_level(logging.WARNING, logger="startup"):
            validate_environment()

        assert any("ChromaDB" in r.message for r in caplog.records)

    def test_warns_when_partial_db_urls(self, monkeypatch, caplog):
        """Missing some (but not all) DB URLs should warn but not fail."""
        env = _env_without("PRODUCTS_DB_URL")
        for k, v in env.items():
            monkeypatch.setenv(k, v)
        monkeypatch.delenv("PRODUCTS_DB_URL", raising=False)

        with caplog.at_level(logging.WARNING, logger="startup"):
            validate_environment()

        assert any("PRODUCTS_DB_URL" in r.message for r in caplog.records)
