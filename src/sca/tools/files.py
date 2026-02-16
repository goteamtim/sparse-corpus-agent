"""File reading, listing, and search tools."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from sca.runtime.sandbox import safe_resolve_path, validate_path
from sca.tools import ToolResult

logger = logging.getLogger(__name__)


def open_snippet(
    path: str,
    workspace_root: Path,
    start_line: int = 1,
    end_line: int | None = None,
) -> ToolResult:
    """
    Read a line-ranged snippet from a file.
    
    Evidence-first principle: All file references must cite line ranges.
    
    Args:
        path: File path (relative to workspace root or absolute)
        workspace_root: Workspace root for sandboxing
        start_line: First line to read (1-indexed, inclusive)
        end_line: Last line to read (1-indexed, inclusive). If None, read to EOF
    
    Returns:
        ToolResult with data containing path, start_line, end_line, text
    """
    resolved = safe_resolve_path(path, workspace_root, must_exist=True)
    
    if not resolved:
        logger.error(f"Cannot read snippet: invalid path {path}")
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Invalid path: {path}", "kind": "path_error"},
        }
    
    if not resolved.is_file():
        logger.error(f"Path is not a file: {resolved}")
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Path is not a file: {path}", "kind": "path_error"},
        }
    
    try:
        # Validate line range
        if start_line < 1:
            logger.warning(f"Invalid start_line {start_line}, using 1")
            start_line = 1

        if end_line is not None and end_line < start_line:
            logger.error(f"Invalid range: {start_line}-{end_line}")
            return {
                "ok": False,
                "data": None,
                "error": {
                    "message": f"Invalid range: {start_line}-{end_line}",
                    "kind": "invalid_range",
                },
            }

        # Stream lines instead of reading the entire file into memory.
        # We skip lines before start_line and stop once we pass end_line,
        # so only the requested window is buffered.
        collected: list[str] = []
        last_line = 0

        with resolved.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh, start=1):
                last_line = i
                if i < start_line:
                    continue
                if end_line is not None and i > end_line:
                    break
                collected.append(line)

        # If end_line was not specified, it means "to EOF"
        if end_line is None:
            end_line = last_line

        snippet = "".join(collected)
        
        logger.info(
            f"Read {resolved.relative_to(workspace_root)} "
            f"[L{start_line}-L{end_line}] ({len(snippet)} chars)"
        )
        
        return {
            "ok": True,
            "data": {
                "path": str(resolved.relative_to(workspace_root)),
                "start_line": start_line,
                "end_line": end_line,
                "text": snippet,
            },
            "error": None,
        }
    
    except UnicodeDecodeError:
        logger.error(f"Cannot decode file (binary?): {resolved}")
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Cannot decode file (binary?): {path}", "kind": "binary_file"},
        }
    except Exception as e:
        logger.error(f"Error reading {resolved}: {e}")
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Error reading file: {e}", "kind": "io_error"},
        }


def file_stats(path: str, workspace_root: Path) -> ToolResult:
    """
    Get basic file statistics without reading content.
    
    Args:
        path: File path (relative to workspace root or absolute)
        workspace_root: Workspace root for sandboxing
    
    Returns:
        ToolResult with data containing size, line_count, exists, is_binary, etc.
    """
    resolved = safe_resolve_path(path, workspace_root, must_exist=False)
    
    if not resolved or not resolved.exists():
        return {
            "ok": False,
            "data": None,
            "error": {
                "message": "Path not found or outside workspace",
                "kind": "not_found",
            },
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
            "ok": True,
            "data": {
                "exists": True,
                "path": str(resolved.relative_to(workspace_root)),
                "name": resolved.name,
                "size_bytes": stat.st_size,
                "line_count": line_count,
                "is_binary": is_binary,
                "is_file": resolved.is_file(),
                "is_dir": resolved.is_dir(),
            },
            "error": None,
        }
    
    except Exception as e:
        logger.error(f"Error getting stats for {path}: {e}")
        return {
            "ok": False,
            "data": None,
            "error": {"message": str(e), "kind": "io_error"},
        }


def list_files(
    workspace_root: Path,
    globs: list[str] | None = None,
    ignore: list[str] | None = None,
    max_files: int = 500,
    include_hidden: bool = False,
) -> ToolResult:
    """
    List files in the workspace matching glob patterns.

    Args:
        workspace_root: Workspace root for sandboxing
        globs: Glob patterns to include (e.g. ["**/*.py"]). Defaults to ["**/*"]
        ignore: Glob patterns to exclude (e.g. ["**/node_modules/**"])
        max_files: Maximum number of files to return
        include_hidden: Whether to include hidden files/directories

    Returns:
        ToolResult with data containing list of file dicts with path, size_bytes
    """
    if globs is None:
        globs = ["**/*"]
    if ignore is None:
        ignore = []

    results: list[dict] = []
    seen: set[Path] = set()

    for pattern in globs:
        for match in sorted(workspace_root.glob(pattern)):
            if len(results) >= max_files:
                logger.warning(f"list_files hit max_files limit ({max_files})")
                break

            if match in seen:
                continue
            seen.add(match)

            # Skip hidden files/dirs unless requested
            if not include_hidden:
                parts = match.relative_to(workspace_root).parts
                if any(p.startswith(".") for p in parts):
                    continue

            # Apply ignore patterns
            rel = match.relative_to(workspace_root)
            if any(rel.match(ig) for ig in ignore):
                continue

            # Only list files, not directories
            if not match.is_file():
                continue

            try:
                stat = match.stat()
                results.append({
                    "path": str(rel),
                    "size_bytes": stat.st_size,
                })
            except OSError as e:
                logger.warning(f"Cannot stat {match}: {e}")

        if len(results) >= max_files:
            break

    logger.info(f"list_files matched {len(results)} files")
    return {
        "ok": True,
        "data": results,
        "error": None,
    }


def rg_search(
    query: str,
    workspace_root: Path,
    globs: list[str] | None = None,
    ignore: list[str] | None = None,
    max_results: int = 50,
    context_lines: int = 2,
) -> ToolResult:
    """
    Search workspace using ripgrep with structured match results.

    Uses PATH resolution to find the rg binary.

    Args:
        query: Search pattern (regex by default)
        workspace_root: Workspace root for sandboxing
        globs: File glob filters (e.g. ["*.py", "*.md"])
        ignore: Glob patterns to exclude
        max_results: Maximum number of matches to return
        context_lines: Number of context lines before/after each match

    Returns:
        ToolResult with data containing query, globs, ignore, and matches list
    """
    rg_bin = shutil.which("rg")
    if not rg_bin:
        logger.error("ripgrep (rg) not found on PATH")
        return {
            "ok": False,
            "data": None,
            "error": {
                "message": "ripgrep (rg) not found. Install and retry.",
                "kind": "missing_binary",
            },
        }

    cmd: list[str] = [
        rg_bin,
        "--json",
        "--max-count", str(max_results),
        "--context", str(context_lines),
    ]

    # Add glob filters
    if globs:
        for g in globs:
            cmd.extend(["--glob", g])

    # Add ignore patterns
    if ignore:
        for ig in ignore:
            cmd.extend(["--glob", f"!{ig}"])

    cmd.append(query)
    cmd.append(str(workspace_root))

    logger.debug(f"rg command: {cmd}")

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(workspace_root),
        )
    except subprocess.TimeoutExpired:
        logger.error("rg_search timed out after 30s")
        return {
            "ok": False,
            "data": None,
            "error": {"message": "Search timed out after 30 seconds", "kind": "timeout"},
        }
    except Exception as e:
        logger.error(f"rg_search failed: {e}")
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Search failed: {e}", "kind": "subprocess_error"},
        }

    # Exit code 1 = no matches (not an error)
    if proc.returncode not in (0, 1):
        logger.error(f"rg exited with code {proc.returncode}: {proc.stderr}")
        return {
            "ok": False,
            "data": None,
            "error": {
                "message": f"ripgrep error: {proc.stderr.strip()}",
                "kind": "subprocess_error",
            },
        }

    if proc.returncode == 1:
        # No matches - still a success
        return {
            "ok": True,
            "data": {
                "query": query,
                "globs": globs or [],
                "ignore": ignore or [],
                "matches": [],
            },
            "error": None,
        }

    # Parse JSON lines output
    matches: list[dict] = []
    context_buffer: list[str] = []

    for raw_line in proc.stdout.splitlines():
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue

        msg_type = obj.get("type")

        if msg_type == "context":
            data = obj["data"]
            context_buffer.append(data["lines"]["text"].rstrip("\n"))

        elif msg_type == "match":
            data = obj["data"]
            path_text = data["path"]["text"]

            # Sandbox check: ensure match path is inside workspace
            match_path = Path(path_text)
            if match_path.is_absolute() and not validate_path(match_path, workspace_root):
                continue

            # Relative path for output
            try:
                rel_path = str(Path(path_text).relative_to(workspace_root))
            except ValueError:
                rel_path = path_text

            line_text = data["lines"]["text"].rstrip("\n")
            line_number = data["line_number"]

            match_entry = {
                "path": rel_path,
                "line_number": line_number,
                "line_text": line_text,
            }

            if context_buffer:
                match_entry["context_before"] = list(context_buffer)
                context_buffer.clear()

            matches.append(match_entry)

            if len(matches) >= max_results:
                break

        elif msg_type == "end":
            # Attach trailing context to last match
            pass

    logger.info(f"rg_search found {len(matches)} matches for {query!r}")
    return {
        "ok": True,
        "data": {
            "query": query,
            "globs": globs or [],
            "ignore": ignore or [],
            "matches": matches,
        },
        "error": None,
    }
