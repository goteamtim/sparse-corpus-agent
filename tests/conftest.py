"""Shared fixtures for sparse-corpus-agent tests."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """Return a temporary directory that acts as the workspace root."""
    return tmp_path


@pytest.fixture
def simple_text_file(workspace: Path) -> Path:
    """Create a plain text file with numbered lines inside the workspace."""
    f = workspace / "sample.txt"
    f.write_text("line1\nline2\nline3\nline4\nline5\n", encoding="utf-8")
    return f


@pytest.fixture
def binary_file(workspace: Path) -> Path:
    """Create a binary file with invalid UTF-8 bytes inside the workspace."""
    f = workspace / "binary.bin"
    # \xff is an invalid UTF-8 start byte, ensuring UnicodeDecodeError on read
    f.write_bytes(b"\xff\xfe" + b"binary content")
    return f
