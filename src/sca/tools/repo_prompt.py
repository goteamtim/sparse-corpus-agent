"""Load repository context from AGENT.md."""

from __future__ import annotations

import logging
from pathlib import Path

from sca.runtime.sandbox import safe_resolve_path

logger = logging.getLogger(__name__)


def read_repo_prompt(repo_root: Path) -> str:
    """
    Load AGENT.md from repository root.
    
    This file contains human-authored context about the repository:
    - Conventions and coding patterns
    - Folder structure explanations
    - Domain glossary
    - Common pitfalls and gotchas
    
    Args:
        repo_root: Repository root path
    
    Returns:
        Contents of AGENT.md, or empty string if not found
    """
    agent_md = safe_resolve_path("AGENT.md", repo_root, must_exist=True)
    
    if not agent_md:
        logger.warning(f"AGENT.md not found in {repo_root}")
        return ""
    
    try:
        content = agent_md.read_text(encoding="utf-8")
        logger.info(f"Loaded AGENT.md ({len(content)} chars)")
        return content
    except Exception as e:
        logger.error(f"Error reading AGENT.md: {e}")
        return ""
