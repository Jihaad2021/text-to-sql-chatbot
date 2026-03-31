"""
Logger Utility

Centralized logging setup for all agents and components.

Example:
    >>> from src.utils.logger import setup_logger
    >>> logger = setup_logger(name="agent.intent_classifier")
    >>> logger.info("Processing query...")
"""

import logging
import os
from datetime import datetime


def setup_logger(
    name: str,
    level: str = "INFO",
    log_to_file: bool = False,
    log_dir: str = "logs"
) -> logging.Logger:
    """
    Setup and return a configured logger.

    Args:
        name: Logger name (e.g., 'agent.intent_classifier')
        level: Log level ('DEBUG', 'INFO', 'WARNING', 'ERROR')
        log_to_file: Whether to also write logs to file
        log_dir: Directory for log files (default: 'logs/')

    Returns:
        Configured logger instance

    Example:
        >>> logger = setup_logger(name="agent.sql_generator", level="DEBUG")
        >>> logger.info("SQL generated successfully")
    """
    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Format
    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler (optional)
    if log_to_file:
        os.makedirs(log_dir, exist_ok=True)
        log_file = os.path.join(log_dir, f"{datetime.now().strftime('%Y-%m-%d')}.log")
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger