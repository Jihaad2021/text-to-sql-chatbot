"""
Logger Utility

Centralized logging setup for all agents and components.
Supports two output formats controlled by the LOG_FORMAT env var:
  - "text" (default): human-readable, good for development
  - "json": structured JSON, good for log aggregators (Datadog, CloudWatch, etc.)

Example:
    >>> from src.utils.logger import setup_logger
    >>> logger = setup_logger(name="agent.intent_classifier")
    >>> logger.info("Processing query...")
"""

import json
import logging
import os
from datetime import datetime, timezone


class _JsonFormatter(logging.Formatter):
    """Emit each log record as a single-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        log_obj: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_obj["exception"] = self.formatException(record.exc_info)
        # Include any extra fields attached via logger.info(..., extra={...})
        for key, value in record.__dict__.items():
            if key not in logging.LogRecord.__dict__ and not key.startswith("_"):
                log_obj[key] = value
        return json.dumps(log_obj, ensure_ascii=False, default=str)


class _TextFormatter(logging.Formatter):
    """Human-readable formatter for development."""

    _FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    _DATE_FMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self) -> None:
        super().__init__(fmt=self._FORMAT, datefmt=self._DATE_FMT)


def setup_logger(
    name: str,
    level: str = "INFO",
    log_to_file: bool = False,
    log_dir: str = "logs",
) -> logging.Logger:
    """
    Setup and return a configured logger.

    The output format is controlled by the LOG_FORMAT environment variable:
    - "json": structured JSON (recommended for production)
    - "text": human-readable (default, recommended for development)

    Args:
        name: Logger name (e.g., 'agent.intent_classifier')
        level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_to_file: Whether to also write logs to a dated file in log_dir
        log_dir: Directory for log files (default: 'logs/')

    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    log_format = os.getenv("LOG_FORMAT", "text").lower()
    formatter: logging.Formatter = (
        _JsonFormatter() if log_format == "json" else _TextFormatter()
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if log_to_file:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
