"""
Configuration Loader

Loads configuration from YAML files and environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Application configuration"""
    
    def __init__(self):
        # TODO: Load YAML configs
        pass
    
    @property
    def anthropic_key(self) -> str:
        return os.getenv('ANTHROPIC_API_KEY')
    
    @property
    def openai_key(self) -> str:
        return os.getenv('OPENAI_API_KEY')

# Global config instance
config = Config()
