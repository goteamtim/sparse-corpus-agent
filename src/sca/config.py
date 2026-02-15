"""Configuration and logging setup for sca."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path


def setup_logging(level: str | None = None) -> None:
    """
    Configure console logging for sca.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR). 
               Falls back to SCA_LOG_LEVEL env var, defaults to INFO.
    """
    log_level = level or os.getenv("SCA_LOG_LEVEL", "INFO").upper()
    
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
    )


class Config:
    """Runtime configuration loaded from environment variables."""
    
    def __init__(self) -> None:
        # OpenAI-compatible endpoint (LM Studio, Ollama, etc.)
        self.openai_base_url = os.getenv(
            "OPENAI_BASE_URL", 
            "http://localhost:11434/v1"
        )

        # Ollama default url: http://localhost:11434/v1
        # LM Studio default url: http://localhost:1234/v1
        
        # API key (not needed for local models, but required by client)
        self.openai_api_key = os.getenv("OPENAI_API_KEY", "not-needed")
        
        # Model identifier (must match LM Studio/Ollama model name)
        self.model_name = os.getenv("MODEL_NAME", "local-model")
        
        # Workspace root override (for testing; normally auto-detected)
        self.workspace_root_override: Path | None = None
        if workspace_env := os.getenv("SCA_WORKSPACE_ROOT"):
            self.workspace_root_override = Path(workspace_env).resolve()
    
    def __repr__(self) -> str:
        return (
            f"Config(base_url={self.openai_base_url!r}, "
            f"model={self.model_name!r}, "
            f"workspace_override={self.workspace_root_override})"
        )


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
