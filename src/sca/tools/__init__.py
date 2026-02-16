"""Tools package initialization."""

from __future__ import annotations

from typing import Any, TypedDict


class ErrorDetail(TypedDict):
    """Error detail structure for tool results."""
    message: str
    kind: str


class ToolResult(TypedDict):
    """Standard envelope for all tool return values."""
    ok: bool
    data: Any
    error: ErrorDetail | None
