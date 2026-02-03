"""Repo-root detection and path sandboxing for safe file operations."""

from __future__ import annotations

import logging
from pathlib import Path

from sca.config import get_config

logger = logging.getLogger(__name__)


def find_repo_root(start: Path | None = None) -> Path:
    """
    Find repository root by walking up from start path.
    
    Looks for:
    - .git directory (standard git repo)
    - AGENT.md file (repo context marker)
    
    Args:
        start: Starting path (defaults to current working directory)
    
    Returns:
        Resolved path to repo root, falls back to CWD if not found
    """
    config = get_config()
    
    # Use config override if set (for testing)
    if config.repo_root_override:
        logger.debug(f"Using repo root override: {config.repo_root_override}")
        return config.repo_root_override
    
    cur = (start or Path.cwd()).resolve()
    logger.debug(f"Searching for repo root from: {cur}")
    
    for p in [cur, *cur.parents]:
        if (p / ".git").exists():
            logger.debug(f"Found repo root via .git: {p}")
            return p
        if (p / "AGENT.md").exists():
            logger.debug(f"Found repo root via AGENT.md: {p}")
            return p
    
    logger.warning(f"No repo root markers found, using: {cur}")
    return cur


def validate_path(path: Path, repo_root: Path) -> bool:
    """
    Check if a path is within repo root boundaries.
    
    Args:
        path: Path to validate (will be resolved)
        repo_root: Repository root path
    
    Returns:
        True if path is within repo_root, False otherwise
    """
    try:
        resolved = path.resolve()
        root_resolved = repo_root.resolve()
        
        # Check if resolved path starts with repo root
        is_within = resolved.is_relative_to(root_resolved)
        
        if not is_within:
            logger.warning(
                f"Path escape attempt: {path} -> {resolved} "
                f"(root: {root_resolved})"
            )
        
        return is_within
    except (ValueError, OSError) as e:
        logger.error(f"Path validation error for {path}: {e}")
        return False


def safe_resolve_path(
    path: str | Path, 
    repo_root: Path,
    must_exist: bool = False
) -> Path | None:
    """
    Safely resolve a path within repo boundaries.
    
    Args:
        path: Path to resolve (relative or absolute)
        repo_root: Repository root for boundary checking
        must_exist: If True, return None if path doesn't exist
    
    Returns:
        Resolved Path if valid and within boundaries, None otherwise
    """
    try:
        if isinstance(path, str):
            path = Path(path)
        
        # If relative, resolve against repo root
        if not path.is_absolute():
            path = repo_root / path
        
        resolved = path.resolve()
        
        # Validate boundaries
        if not validate_path(resolved, repo_root):
            logger.error(f"Path outside repo boundaries: {path}")
            return None
        
        # Check existence if required
        if must_exist and not resolved.exists():
            logger.warning(f"Path does not exist: {resolved}")
            return None
        
        return resolved
    
    except Exception as e:
        logger.error(f"Error resolving path {path}: {e}")
        return None
