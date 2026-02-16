"""Workspace root detection and path sandboxing for safe file operations."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Marker files/dirs that indicate a repository root
_ROOT_MARKERS = (".git", "AGENT.md")


def find_workspace_root(
    repo_path: Path | None = None,
    start: Path | None = None,
) -> Path:
    """
    Resolve the workspace/repo root directory.

    Resolution order (first match wins):
      1. Explicit *repo_path* argument (from ``--repo`` CLI flag)
      2. ``SCA_REPO`` environment variable
      3. ``SCA_WORKSPACE_ROOT`` environment variable (legacy)
      4. Walk upward from *start* (default: cwd) looking for ``.git`` or ``AGENT.md``

    Args:
        repo_path: Explicit repo root (already resolved by caller).
        start: Starting directory for upward search (defaults to cwd).

    Returns:
        Resolved path to the workspace root.

    Raises:
        ValueError: If no root can be determined.
    """
    # 1. Explicit argument
    if repo_path is not None:
        root = repo_path.resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"Repo path does not exist or is not a directory: {root}")
        logger.debug(f"Using explicit repo path: {root}")
        return root

    # 2. SCA_REPO env var
    if env_repo := os.getenv("SCA_REPO"):
        root = Path(env_repo).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(f"SCA_REPO path does not exist or is not a directory: {root}")
        logger.debug(f"Using SCA_REPO: {root}")
        return root

    # 3. SCA_WORKSPACE_ROOT env var (legacy, superseded by SCA_REPO)
    if env_ws := os.getenv("SCA_WORKSPACE_ROOT"):
        root = Path(env_ws).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise ValueError(
                f"SCA_WORKSPACE_ROOT path does not exist or is not a directory: {root}"
            )
        logger.debug(f"Using SCA_WORKSPACE_ROOT (legacy): {root}")
        return root

    # 4. Walk upward from start/cwd looking for marker files
    cur = (start or Path.cwd()).resolve()
    for p in [cur, *cur.parents]:
        if any((p / marker).exists() for marker in _ROOT_MARKERS):
            logger.debug(f"Auto-detected workspace root: {p}")
            return p

    raise ValueError(
        "No repo found. Run inside a repo, pass --repo, or set SCA_REPO."
    )


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
