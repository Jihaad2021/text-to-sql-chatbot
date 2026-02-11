"""
Logging Configuration

Sets up application logging.
"""

import logging

def setup_logger(name: str):
    """Setup logger with formatting"""
    logger = logging.getLogger(name)
    # TODO: Configure logging format
    return logger
