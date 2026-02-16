"""Tree-sitter code outline tool with 3-tier symbol resolution.

Loads a user-provided compiled Tree-sitter grammar at runtime and
extracts structural symbols (functions, classes, etc.) from source files.

Grammar resolution (fall-through):
    Level 1 — Query:    .agent/queries/{lang}/tags.scm  (standard tree-sitter)
    Level 2 — Registry: .agent/grammar.yaml  outline_node_types list
    Level 3 — Defaults: Universal common node types
"""

from __future__ import annotations

import ctypes
import logging
from pathlib import Path
from typing import Any

import yaml

from sca.runtime.sandbox import safe_resolve_path
from sca.tools import ToolResult

logger = logging.getLogger(__name__)


# ── Universal default node types (Level 3 fallback) ────────────────

DEFAULT_OUTLINE_NODE_TYPES: set[str] = {
    # Functions
    "function_definition",
    "function_declaration",
    "arrow_function",
    "lambda",
    # Classes / types
    "class_definition",
    "class_declaration",
    "struct_definition",
    "struct_declaration",
    "interface_declaration",
    "type_alias_declaration",
    "enum_definition",
    "enum_declaration",
    # Methods
    "method_definition",
    "method_declaration",
    # Modules / namespaces
    "module_definition",
    "module_declaration",
    "namespace_definition",
    # Imports
    "import_statement",
    "import_declaration",
    "include_statement",
}


# ── Grammar loading ────────────────────────────────────────────────

# Module-level cache for the loaded Language object
_cached_language: Any | None = None
_cached_grammar_key: tuple[str, str] | None = None


def load_grammar(grammar_path: Path, grammar_name: str) -> Any:
    """
    Load a Tree-sitter grammar from a compiled shared library.

    Uses ctypes to dlopen the library, call the tree_sitter_<name>()
    export, wrap the result in a PyCapsule, and return a Language.

    The result is cached at module level so the library is only
    loaded once per process.

    Args:
        grammar_path: Path to the .so / .dll / .dylib file
        grammar_name: Language name (must match the exported C symbol)

    Returns:
        tree_sitter.Language instance

    Raises:
        FileNotFoundError: If the grammar file doesn't exist
        OSError: If the shared library can't be loaded
        AttributeError: If the expected symbol isn't exported
        RuntimeError: If the language pointer is NULL
    """
    global _cached_language, _cached_grammar_key

    cache_key = (str(grammar_path), grammar_name)
    if _cached_language is not None and _cached_grammar_key == cache_key:
        return _cached_language

    # Import tree_sitter here to keep it an optional dependency at module level
    from tree_sitter import Language

    if not grammar_path.is_file():
        raise FileNotFoundError(f"Grammar file not found: {grammar_path}")

    logger.info(f"Loading tree-sitter grammar: {grammar_name} from {grammar_path}")

    # Load the shared library
    lib = ctypes.cdll.LoadLibrary(str(grammar_path))

    # Resolve the exported language function: tree_sitter_<name>()
    symbol_name = f"tree_sitter_{grammar_name}"
    try:
        lang_func = getattr(lib, symbol_name)
    except AttributeError:
        raise AttributeError(
            f"Grammar library does not export '{symbol_name}()'. "
            f"Check that SCA_GRAMMAR_NAME='{grammar_name}' matches "
            f"the grammar's language name."
        )

    lang_func.restype = ctypes.c_void_p
    lang_func.argtypes = []

    raw_ptr = lang_func()
    if not raw_ptr:
        raise RuntimeError(
            f"tree_sitter_{grammar_name}() returned NULL. "
            f"The grammar library may be corrupt."
        )

    # Wrap the raw pointer in a PyCapsule to avoid the deprecation warning
    # when passing an int directly to Language()
    ctypes.pythonapi.PyCapsule_New.restype = ctypes.py_object
    ctypes.pythonapi.PyCapsule_New.argtypes = [
        ctypes.c_void_p,  # pointer
        ctypes.c_char_p,  # name
        ctypes.c_void_p,  # destructor (NULL)
    ]
    capsule = ctypes.pythonapi.PyCapsule_New(
        raw_ptr, b"tree_sitter.Language", None
    )

    language = Language(capsule)
    logger.info(
        f"Grammar loaded: {grammar_name} "
        f"(ABI version {language.abi_version})"
    )

    _cached_language = language
    _cached_grammar_key = cache_key
    return language


# ── Level 1: Query-based outline (.scm) ───────────────────────────


def _resolve_query_path(
    grammar_name: str, workspace_root: Path
) -> Path | None:
    """Check for .agent/queries/{grammar_name}/tags.scm."""
    query_path = workspace_root / ".agent" / "queries" / grammar_name / "tags.scm"
    if query_path.is_file():
        logger.info(f"Found tags query: {query_path}")
        return query_path
    return None


def _outline_from_query(
    source: bytes,
    language: Any,
    query_path: Path,
    max_depth: int,
) -> list[dict]:
    """
    Extract outline symbols using a .scm query file.

    Follows tree-sitter tags.scm conventions:
        @name           — the symbol's identifier
        @definition.*   — the full definition node (kind derived from suffix)

    Args:
        source: Raw file bytes
        language: tree_sitter.Language instance
        query_path: Path to the .scm query file
        max_depth: Maximum nesting depth to include

    Returns:
        List of symbol dicts: {name, kind, start_line, end_line, depth}
    """
    from tree_sitter import Parser, Query, QueryCursor

    parser = Parser(language)
    tree = parser.parse(source)

    scm_text = query_path.read_text(encoding="utf-8")
    query = Query(language, scm_text)
    cursor = QueryCursor(query)

    symbols: list[dict] = []

    for _pattern_idx, capture_dict in cursor.matches(tree.root_node):
        # Find @name capture(s)
        name_nodes = capture_dict.get("name", [])

        # Find @definition.* captures and derive kind from the suffix
        def_captures = {
            k: v for k, v in capture_dict.items() if k.startswith("definition.")
        }

        if not name_nodes or not def_captures:
            continue

        for def_key, def_nodes in def_captures.items():
            # Kind is the part after "definition." (e.g. "definition.function" → "function")
            kind = def_key.split(".", 1)[1] if "." in def_key else def_key

            for def_node in def_nodes:
                # Compute depth by walking up the tree
                depth = _node_depth(def_node)
                if depth > max_depth:
                    continue

                # Match the first @name node that falls within this definition
                sym_name = None
                for name_node in name_nodes:
                    if (
                        name_node.start_byte >= def_node.start_byte
                        and name_node.end_byte <= def_node.end_byte
                    ):
                        sym_name = source[
                            name_node.start_byte : name_node.end_byte
                        ].decode("utf-8", errors="replace")
                        break

                if not sym_name:
                    continue

                symbols.append(
                    {
                        "name": sym_name,
                        "kind": kind,
                        "start_line": def_node.start_point[0] + 1,
                        "end_line": def_node.end_point[0] + 1,
                        "depth": depth,
                    }
                )

    # Deduplicate (a symbol may be captured by multiple patterns)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for s in symbols:
        key = (s["name"], s["kind"], s["start_line"])
        if key not in seen:
            seen.add(key)
            unique.append(s)

    unique.sort(key=lambda s: s["start_line"])
    return unique


# ── Level 2: Registry-based outline (grammar.yaml) ────────────────


def _load_registry_node_types(workspace_root: Path) -> set[str] | None:
    """Load outline_node_types from .agent/grammar.yaml if it exists."""
    yaml_path = workspace_root / ".agent" / "grammar.yaml"
    if not yaml_path.is_file():
        return None

    try:
        data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to parse {yaml_path}: {e}")
        return None

    if not isinstance(data, dict):
        logger.warning(f"grammar.yaml root is not a mapping: {yaml_path}")
        return None

    node_types = data.get("outline_node_types")
    if not isinstance(node_types, list) or not node_types:
        return None

    result = {str(t) for t in node_types}
    logger.info(f"Loaded {len(result)} node types from grammar.yaml")
    return result


# ── Level 2 & 3 shared: CST walk ──────────────────────────────────


def _outline_from_node_types(
    source: bytes,
    language: Any,
    node_types: set[str],
    max_depth: int,
) -> list[dict]:
    """
    Extract outline symbols by walking the CST and matching node types.

    For each matching node, the symbol name is taken from the first
    named child (typically the identifier).

    Args:
        source: Raw file bytes
        language: tree_sitter.Language instance
        node_types: Set of node type strings to match
        max_depth: Maximum nesting depth to include

    Returns:
        List of symbol dicts: {name, kind, start_line, end_line, depth}
    """
    from tree_sitter import Parser

    parser = Parser(language)
    tree = parser.parse(source)

    symbols: list[dict] = []
    _walk_node(tree.root_node, source, node_types, max_depth, 0, symbols)
    symbols.sort(key=lambda s: s["start_line"])
    return symbols


def _walk_node(
    node: Any,
    source: bytes,
    node_types: set[str],
    max_depth: int,
    current_depth: int,
    out: list[dict],
) -> None:
    """Recursively walk the CST, collecting outline-worthy nodes."""
    if current_depth > max_depth:
        return

    if node.type in node_types:
        # Extract name from the first named child (usually the identifier)
        name = _extract_symbol_name(node, source)

        out.append(
            {
                "name": name or "<anonymous>",
                "kind": node.type,
                "start_line": node.start_point[0] + 1,
                "end_line": node.end_point[0] + 1,
                "depth": current_depth,
            }
        )

        # Recurse into children at depth + 1
        for child in node.children:
            _walk_node(child, source, node_types, max_depth, current_depth + 1, out)
    else:
        # Not a match — pass through at same depth
        for child in node.children:
            _walk_node(child, source, node_types, max_depth, current_depth, out)


def _extract_symbol_name(node: Any, source: bytes) -> str | None:
    """
    Extract the symbol name from a definition node.

    Tries the 'name' field first, then falls back to the first
    named child node.
    """
    # Try the 'name' field (most grammars use this convention)
    name_node = node.child_by_field_name("name")
    if name_node:
        return source[name_node.start_byte : name_node.end_byte].decode(
            "utf-8", errors="replace"
        )

    # Fallback: first named child
    for child in node.children:
        if child.is_named:
            return source[child.start_byte : child.end_byte].decode(
                "utf-8", errors="replace"
            )

    return None


# ── Helpers ────────────────────────────────────────────────────────


def _node_depth(node: Any) -> int:
    """
    Compute the outline-relevant depth of a node.

    Depth 0 = direct child of the root (module/program) node.
    Depth 1 = one level nested (e.g. method inside a class body).

    Intermediate wrapper nodes (block, body, etc.) are not counted;
    only nodes whose type appears in DEFAULT_OUTLINE_NODE_TYPES or
    is the root node contribute to depth.
    """
    depth = 0
    current = node.parent
    while current is not None:
        if current.parent is None:
            # This is the root node — don't count it
            break
        # Count parent if it looks like a structural definition
        # (has a 'name' field, which most definition nodes do)
        if current.child_by_field_name("name") is not None:
            depth += 1
        current = current.parent
    return depth


# ── Public API ─────────────────────────────────────────────────────


def get_outline(
    path: str,
    workspace_root: Path,
    grammar_path: Path | None,
    grammar_name: str | None,
    grammar_extensions: list[str] | None,
    max_depth: int = 2,
) -> ToolResult:
    """
    Extract a structural outline of symbols from a source file.

    Uses a 3-tier fall-through strategy to decide how to extract symbols:
        Level 1: .agent/queries/{lang}/tags.scm   (tree-sitter standard)
        Level 2: .agent/grammar.yaml outline_node_types   (registry)
        Level 3: Universal default node types              (fallback)

    Args:
        path: File path (relative to workspace root or absolute)
        workspace_root: Workspace root for sandboxing
        grammar_path: Path to compiled grammar .so/.dll/.dylib
        grammar_name: Language name for the tree_sitter_<name>() symbol
        grammar_extensions: File extensions this grammar applies to
        max_depth: Maximum nesting depth (default 2: top-level + one nested)

    Returns:
        ToolResult with data containing path, grammar, level, and symbols list.
        Each symbol has: name, kind, start_line, end_line, depth.
    """
    # ── Validate grammar configuration ─────────────────────────────
    if not grammar_path or not grammar_name or not grammar_extensions:
        return {
            "ok": False,
            "data": None,
            "error": {
                "message": (
                    "Tree-sitter grammar not configured. Set all three env vars: "
                    "SCA_GRAMMAR_PATH, SCA_GRAMMAR_NAME, SCA_GRAMMAR_EXTENSIONS"
                ),
                "kind": "not_configured",
            },
        }

    # ── Resolve and sandbox-check the file path ───────────────────
    resolved = safe_resolve_path(path, workspace_root, must_exist=True)
    if not resolved:
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Invalid path: {path}", "kind": "path_error"},
        }

    if not resolved.is_file():
        return {
            "ok": False,
            "data": None,
            "error": {
                "message": f"Path is not a file: {path}",
                "kind": "path_error",
            },
        }

    # ── Validate file extension ────────────────────────────────────
    file_ext = resolved.suffix.lower()
    allowed_exts = [e.lower() for e in grammar_extensions]
    if file_ext not in allowed_exts:
        return {
            "ok": False,
            "data": None,
            "error": {
                "message": (
                    f"File extension '{file_ext}' not in configured grammar "
                    f"extensions: {allowed_exts}"
                ),
                "kind": "extension_mismatch",
            },
        }

    # ── Load grammar ──────────────────────────────────────────────
    try:
        language = load_grammar(grammar_path, grammar_name)
    except Exception as e:
        logger.error(f"Failed to load grammar: {e}")
        return {
            "ok": False,
            "data": None,
            "error": {
                "message": f"Failed to load grammar: {e}",
                "kind": "grammar_error",
            },
        }

    # ── Read file bytes ───────────────────────────────────────────
    try:
        source = resolved.read_bytes()
    except Exception as e:
        logger.error(f"Failed to read file: {e}")
        return {
            "ok": False,
            "data": None,
            "error": {"message": f"Failed to read file: {e}", "kind": "io_error"},
        }

    # ── 3-tier symbol resolution ──────────────────────────────────
    rel_path = str(resolved.relative_to(workspace_root))
    symbols: list[dict] = []
    level_used: str = ""

    # Level 1: Custom .scm query
    query_path = _resolve_query_path(grammar_name, workspace_root)
    if query_path is not None:
        level_used = "query"
        try:
            symbols = _outline_from_query(source, language, query_path, max_depth)
            logger.info(
                f"Outline via query ({query_path.name}): "
                f"{len(symbols)} symbols from {rel_path}"
            )
        except Exception as e:
            logger.warning(
                f"Query-based outline failed for {rel_path}, "
                f"falling back to registry/defaults: {e}"
            )
            query_path = None  # trigger fallback

    # Level 2: grammar.yaml registry
    if query_path is None:
        registry_types = _load_registry_node_types(workspace_root)
        if registry_types is not None:
            level_used = "registry"
            symbols = _outline_from_node_types(
                source, language, registry_types, max_depth
            )
            logger.info(
                f"Outline via registry (grammar.yaml): "
                f"{len(symbols)} symbols from {rel_path}"
            )
        else:
            # Level 3: Universal defaults
            level_used = "defaults"
            symbols = _outline_from_node_types(
                source, language, DEFAULT_OUTLINE_NODE_TYPES, max_depth
            )
            logger.info(
                f"Outline via defaults: "
                f"{len(symbols)} symbols from {rel_path}"
            )

    return {
        "ok": True,
        "data": {
            "path": rel_path,
            "grammar": grammar_name,
            "level": level_used,
            "max_depth": max_depth,
            "symbol_count": len(symbols),
            "symbols": symbols,
        },
        "error": None,
    }
