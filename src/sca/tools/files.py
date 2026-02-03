"""File reading and listing tools."""

from __future__ import annotations

import logging
from pathlib import Path

from sca.runtime.sandbox import safe_resolve_path

logger = logging.getLogger(__name__)


def open_snippet(
    path: str,
    repo_root: Path,
    start_line: int = 1,
    end_line: int | None = None,
) -> str:
    """
    Read a line-ranged snippet from a file.
    
    Evidence-first principle: All file references must cite line ranges.
    
    Args:
        path: File path (relative to repo root or absolute)
        repo_root: Repository root for sandboxing
        start_line: First line to read (1-indexed, inclusive)
        end_line: Last line to read (1-indexed, inclusive). If None, read to EOF
    
    Returns:
        File content for specified line range, or empty string on error
    """
    resolved = safe_resolve_path(path, repo_root, must_exist=True)
    
    if not resolved:
        logger.error(f"Cannot read snippet: invalid path {path}")
        return ""
    
    if not resolved.is_file():
        logger.error(f"Path is not a file: {resolved}")
        return ""
    
    try:
        lines = resolved.read_text(encoding="utf-8").splitlines(keepends=True)
        
        # Validate line range
        if start_line < 1:
            logger.warning(f"Invalid start_line {start_line}, using 1")
            start_line = 1
        
        if end_line is None:
            end_line = len(lines)
        
        if end_line < start_line:
            logger.error(f"Invalid range: {start_line}-{end_line}")
            return ""
        
        # Extract snippet (convert to 0-indexed)
        snippet_lines = lines[start_line - 1 : end_line]
        snippet = "".join(snippet_lines)
        
        logger.info(
            f"Read {resolved.relative_to(repo_root)} "
            f"[L{start_line}-L{end_line}] ({len(snippet)} chars)"
        )
        
        return snippet
    
    except UnicodeDecodeError:
        logger.error(f"Cannot decode file (binary?): {resolved}")
        return ""
    except Exception as e:
        logger.error(f"Error reading {resolved}: {e}")
        return ""


def file_stats(path: str, repo_root: Path) -> dict:
    """
    Get basic file statistics without reading content.
    
    Args:
        path: File path (relative to repo root or absolute)
        repo_root: Repository root for sandboxing
    
    Returns:
        Dictionary with size, line_count, exists, is_binary, error fields
    """
    resolved = safe_resolve_path(path, repo_root, must_exist=False)
    
    if not resolved or not resolved.exists():
        return {
            "exists": False,
            "path": path,
            "error": "Path not found or outside repo",
        }
    
    try:
        stat = resolved.stat()
        
        # Try to detect binary files (simple heuristic)
        is_binary = False
        line_count = 0
        
        if resolved.is_file():
            try:
                # Read first 8KB to check for null bytes
                sample = resolved.read_bytes()[:8192]
                is_binary = b"\x00" in sample
                
                if not is_binary:
                    # Count lines if text
                    content = resolved.read_text(encoding="utf-8")
                    line_count = content.count("\n") + 1
            except (UnicodeDecodeError, OSError):
                is_binary = True
        
        return {
            "exists": True,
            "path": str(resolved.relative_to(repo_root)),
            "size_bytes": stat.st_size,
            "line_count": line_count,
            "is_binary": is_binary,
            "is_file": resolved.is_file(),
            "is_dir": resolved.is_dir(),
        }
    
    except Exception as e:
        logger.error(f"Error getting stats for {path}: {e}")
        return {
            "exists": True,
            "path": path,
            "error": str(e),
        }
