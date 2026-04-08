"""
Unit tests for setup_logger and log formatters.

Tests cover:
- Text format produces human-readable output
- JSON format produces valid JSON with required keys
- JSON format includes extra fields from logger.info(..., extra={})
- Same logger name returns same instance (no duplicate handlers)
"""

import json
import logging

import pytest

from src.utils.logger import setup_logger


def _capture_log(logger: logging.Logger, message: str, **extra) -> str:
    """Emit one log record and capture it via a StringIO stream handler."""
    import io
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logger.handlers[0].formatter)
    logger.addHandler(handler)
    try:
        if extra:
            logger.info(message, extra=extra)
        else:
            logger.info(message)
        return stream.getvalue().strip()
    finally:
        logger.removeHandler(handler)


# ========================================
# Test: Text format
# ========================================

class TestTextFormat:

    def test_produces_human_readable_output(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "text")
        logger = setup_logger(name="test.text.readable")
        output = _capture_log(logger, "hello world")

        assert "hello world" in output
        assert "[INFO]" in output or "INFO" in output

    def test_is_not_json(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "text")
        logger = setup_logger(name="test.text.notjson")
        output = _capture_log(logger, "not json")

        with pytest.raises((json.JSONDecodeError, ValueError)):
            json.loads(output)


# ========================================
# Test: JSON format
# ========================================

class TestJsonFormat:

    def test_produces_valid_json(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        logger = setup_logger(name="test.json.valid")
        output = _capture_log(logger, "structured log")

        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_json_has_required_keys(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        logger = setup_logger(name="test.json.keys")
        output = _capture_log(logger, "check keys")

        parsed = json.loads(output)
        assert "timestamp" in parsed
        assert "level" in parsed
        assert "logger" in parsed
        assert "message" in parsed

    def test_json_message_matches(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        logger = setup_logger(name="test.json.message")
        output = _capture_log(logger, "my test message")

        parsed = json.loads(output)
        assert parsed["message"] == "my test message"

    def test_json_includes_extra_fields(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        logger = setup_logger(name="test.json.extra")
        output = _capture_log(
            logger,
            "request completed",
            request_id="abc-123",
            row_count=42,
        )

        parsed = json.loads(output)
        assert parsed.get("request_id") == "abc-123"
        assert parsed.get("row_count") == 42

    def test_json_level_is_uppercase(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "json")
        logger = setup_logger(name="test.json.level")
        output = _capture_log(logger, "level check")

        parsed = json.loads(output)
        assert parsed["level"] == "INFO"


# ========================================
# Test: Logger identity (no duplicate handlers)
# ========================================

class TestLoggerIdentity:

    def test_same_name_returns_same_logger(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "text")
        logger_a = setup_logger(name="test.identity.same")
        logger_b = setup_logger(name="test.identity.same")
        assert logger_a is logger_b

    def test_no_duplicate_handlers_on_repeated_calls(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMAT", "text")
        logger = setup_logger(name="test.identity.handlers")
        initial_count = len(logger.handlers)
        setup_logger(name="test.identity.handlers")  # second call
        assert len(logger.handlers) == initial_count
