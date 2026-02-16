"""Workspace root detection and path sandboxing for safe file operations."""

from __future__ import annotations

import logging
from pathlib import Path

from sca.config import get_config

logger = logging.getLogger(__name__)


def find_workspace_root(start: Path | None = None) -> Path:
    """
    Find workspace root from the current working directory.
    
    Uses the directory where the tool was invoked from as the workspace root.
    
    Args:
        start: Starting path (defaults to current working directory)
    
    Returns:
        Resolved path to workspace root (current working directory)
    """
    config = get_config()
    
    # Use config override if set (for testing)
    if config.workspace_root_override:
        logger.debug(f"Using workspace root override: {config.workspace_root_override}")
        return config.workspace_root_override
    
    root = (start or Path.cwd()).resolve()
    logger.debug(f"Using workspace root: {root}")
    
    return root


def validate_path(path: Path, workspace_root: Path) -> bool:
    """
    Check if a path is within workspace root boundaries.
    
    Args:
        path: Path to validate (will be resolved)
        workspace_root: Workspace root path
    
    Returns:
        True if path is within workspace_root, False otherwise
    """
    try:
        resolved = path.resolve()
        root_resolved = workspace_root.resolve()
        
        # Check if resolved path starts with workspace root
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
    workspace_root: Path,
    must_exist: bool = False
) -> Path | None:
    """
    Safely resolve a path within workspace boundaries.
    
    Args:
        path: Path to resolve (relative or absolute)
        workspace_root: Workspace root for boundary checking
        must_exist: If True, return None if path doesn't exist
    
    Returns:
        Resolved Path if valid and within boundaries, None otherwise
    """
    try:
        if isinstance(path, str):
            path = Path(path)
        
        # If relative, resolve against workspace root
        if not path.is_absolute():
            path = workspace_root / path
        
        resolved = path.resolve()
        
        # Validate boundaries
        if not validate_path(resolved, workspace_root):
            logger.error(f"Path outside workspace boundaries: {path}")
            return None
        
        # Check existence if required
        if must_exist and not resolved.exists():
            logger.warning(f"Path does not exist: {resolved}")
            return None
        
        return resolved
    
    except Exception as e:
        logger.error(f"Error resolving path {path}: {e}")
        return None
