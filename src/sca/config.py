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

        # ── Tree-sitter grammar configuration ──────────────────────────
        # Path to the compiled grammar shared library (.so / .dll / .dylib)
        self.grammar_path: Path | None = None
        if grammar_env := os.getenv("SCA_GRAMMAR_PATH"):
            self.grammar_path = Path(grammar_env).resolve()

        # Language name — must match the exported C symbol tree_sitter_<name>()
        self.grammar_name: str | None = os.getenv("SCA_GRAMMAR_NAME")

        # File extensions this grammar applies to (comma-separated, e.g. ".xy,.xyz")
        self.grammar_extensions: list[str] = []
        if ext_env := os.getenv("SCA_GRAMMAR_EXTENSIONS"):
            self.grammar_extensions = [
                e.strip() if e.strip().startswith(".") else f".{e.strip()}"
                for e in ext_env.split(",")
                if e.strip()
            ]

        # Validate: all three must be set together or none
        grammar_fields = [self.grammar_path, self.grammar_name, self.grammar_extensions]
        grammar_set = [f for f in grammar_fields if f]
        if 0 < len(grammar_set) < 3:
            logging.getLogger(__name__).warning(
                "Partial tree-sitter config: SCA_GRAMMAR_PATH, SCA_GRAMMAR_NAME, "
                "and SCA_GRAMMAR_EXTENSIONS must all be set together. "
                f"Got: path={self.grammar_path}, name={self.grammar_name}, "
                f"extensions={self.grammar_extensions}"
            )

    @property
    def grammar_configured(self) -> bool:
        """True when all three grammar settings are present."""
        return bool(
            self.grammar_path and self.grammar_name and self.grammar_extensions
        )

    def __repr__(self) -> str:
        return (
            f"Config(base_url={self.openai_base_url!r}, "
            f"model={self.model_name!r}, "
            f"grammar={self.grammar_name!r})"
        )


# Global config instance
_config: Config | None = None


def get_config() -> Config:
    """Get or create the global config instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
