"""Tests for sca.tools.files: open_snippet, file_stats, list_files, rg_search."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from sca.tools.files import file_stats, list_files, open_snippet, rg_search


# ---------------------------------------------------------------------------
# open_snippet
# ---------------------------------------------------------------------------


class TestOpenSnippet:
    def test_reads_full_file(self, simple_text_file: Path, workspace: Path) -> None:
        result = open_snippet("sample.txt", workspace)
        assert result["ok"] is True
        assert result["data"]["text"] == "line1\nline2\nline3\nline4\nline5\n"
        assert result["data"]["start_line"] == 1
        assert result["data"]["end_line"] == 5

    def test_reads_partial_range(self, simple_text_file: Path, workspace: Path) -> None:
        result = open_snippet("sample.txt", workspace, start_line=2, end_line=4)
        assert result["ok"] is True
        assert result["data"]["text"] == "line2\nline3\nline4\n"
        assert result["data"]["start_line"] == 2
        assert result["data"]["end_line"] == 4

    def test_reads_single_line(self, simple_text_file: Path, workspace: Path) -> None:
        result = open_snippet("sample.txt", workspace, start_line=3, end_line=3)
        assert result["ok"] is True
        assert result["data"]["text"] == "line3\n"

    def test_start_line_beyond_eof(self, simple_text_file: Path, workspace: Path) -> None:
        result = open_snippet("sample.txt", workspace, start_line=100)
        assert result["ok"] is True
        assert result["data"]["text"] == ""

    def test_end_line_beyond_eof(self, simple_text_file: Path, workspace: Path) -> None:
        result = open_snippet("sample.txt", workspace, start_line=4, end_line=999)
        assert result["ok"] is True
        assert result["data"]["text"] == "line4\nline5\n"

    def test_clamps_invalid_start_line_to_one(
        self, simple_text_file: Path, workspace: Path
    ) -> None:
        result = open_snippet("sample.txt", workspace, start_line=0)
        assert result["ok"] is True
        assert result["data"]["start_line"] == 1

    def test_invalid_range_returns_error(
        self, simple_text_file: Path, workspace: Path
    ) -> None:
        result = open_snippet("sample.txt", workspace, start_line=4, end_line=2)
        assert result["ok"] is False
        assert result["error"]["kind"] == "invalid_range"

    def test_nonexistent_file_returns_error(self, workspace: Path) -> None:
        result = open_snippet("no_such_file.txt", workspace)
        assert result["ok"] is False
        assert result["error"]["kind"] == "path_error"

    def test_directory_path_returns_error(self, workspace: Path) -> None:
        sub = workspace / "subdir"
        sub.mkdir()
        result = open_snippet("subdir", workspace)
        assert result["ok"] is False
        assert result["error"]["kind"] == "path_error"

    def test_path_outside_workspace_returns_error(self, workspace: Path) -> None:
        result = open_snippet("/etc/passwd", workspace)
        assert result["ok"] is False
        assert result["error"]["kind"] == "path_error"

    def test_binary_file_returns_error(self, binary_file: Path, workspace: Path) -> None:
        result = open_snippet("binary.bin", workspace)
        assert result["ok"] is False
        assert result["error"]["kind"] == "binary_file"

    def test_relative_path_data_stripped(
        self, simple_text_file: Path, workspace: Path
    ) -> None:
        result = open_snippet("sample.txt", workspace)
        assert result["ok"] is True
        # Returned path should be relative, not absolute
        assert not Path(result["data"]["path"]).is_absolute()

    def test_absolute_path_within_workspace(
        self, simple_text_file: Path, workspace: Path
    ) -> None:
        result = open_snippet(str(simple_text_file), workspace)
        assert result["ok"] is True
        assert "line1" in result["data"]["text"]

    def test_nested_file(self, workspace: Path) -> None:
        sub = workspace / "sub"
        sub.mkdir()
        (sub / "nested.txt").write_text("a\nb\nc\n", encoding="utf-8")
        result = open_snippet("sub/nested.txt", workspace)
        assert result["ok"] is True
        assert result["data"]["text"] == "a\nb\nc\n"

    def test_empty_file(self, workspace: Path) -> None:
        (workspace / "empty.txt").write_text("", encoding="utf-8")
        result = open_snippet("empty.txt", workspace)
        assert result["ok"] is True
        assert result["data"]["text"] == ""
        assert result["data"]["end_line"] == 0


# ---------------------------------------------------------------------------
# file_stats
# ---------------------------------------------------------------------------


class TestFileStats:
    def test_text_file_stats(self, simple_text_file: Path, workspace: Path) -> None:
        result = file_stats("sample.txt", workspace)
        assert result["ok"] is True
        data = result["data"]
        assert data["exists"] is True
        assert data["is_file"] is True
        assert data["is_dir"] is False
        assert data["is_binary"] is False
        assert data["line_count"] == 6  # 5 newlines in content → count("\n") + 1 = 6
        assert data["size_bytes"] > 0

    def test_binary_file_stats(self, binary_file: Path, workspace: Path) -> None:
        result = file_stats("binary.bin", workspace)
        assert result["ok"] is True
        data = result["data"]
        assert data["is_binary"] is True
        assert data["is_file"] is True

    def test_directory_stats(self, workspace: Path) -> None:
        sub = workspace / "adir"
        sub.mkdir()
        result = file_stats("adir", workspace)
        assert result["ok"] is True
        data = result["data"]
        assert data["is_dir"] is True
        assert data["is_file"] is False

    def test_nonexistent_path_returns_error(self, workspace: Path) -> None:
        result = file_stats("ghost.txt", workspace)
        assert result["ok"] is False
        assert result["error"]["kind"] == "not_found"

    def test_path_outside_workspace_returns_error(self, workspace: Path) -> None:
        result = file_stats("/etc/passwd", workspace)
        assert result["ok"] is False
        assert result["error"]["kind"] == "not_found"

    def test_relative_path_in_result(self, simple_text_file: Path, workspace: Path) -> None:
        result = file_stats("sample.txt", workspace)
        assert result["ok"] is True
        assert not Path(result["data"]["path"]).is_absolute()

    def test_empty_file_stats(self, workspace: Path) -> None:
        (workspace / "empty.txt").write_text("", encoding="utf-8")
        result = file_stats("empty.txt", workspace)
        assert result["ok"] is True
        assert result["data"]["size_bytes"] == 0


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------


class TestListFiles:
    def _populate(self, workspace: Path) -> None:
        (workspace / "a.py").write_text("# a\n", encoding="utf-8")
        (workspace / "b.py").write_text("# b\n", encoding="utf-8")
        sub = workspace / "sub"
        sub.mkdir()
        (sub / "c.txt").write_text("c\n", encoding="utf-8")
        hidden = workspace / ".hidden"
        hidden.mkdir()
        (hidden / "secret.txt").write_text("secret\n", encoding="utf-8")

    def test_lists_all_files(self, workspace: Path) -> None:
        self._populate(workspace)
        result = list_files(workspace)
        assert result["ok"] is True
        paths = {f["path"] for f in result["data"]}
        assert "a.py" in paths
        assert "b.py" in paths
        assert "sub/c.txt" in paths

    def test_hidden_files_excluded_by_default(self, workspace: Path) -> None:
        self._populate(workspace)
        result = list_files(workspace)
        assert result["ok"] is True
        paths = {f["path"] for f in result["data"]}
        assert not any(".hidden" in p for p in paths)

    def test_hidden_files_included_when_requested(self, workspace: Path) -> None:
        self._populate(workspace)
        result = list_files(workspace, include_hidden=True)
        assert result["ok"] is True
        paths = {f["path"] for f in result["data"]}
        assert any(".hidden" in p for p in paths)

    def test_glob_filter(self, workspace: Path) -> None:
        self._populate(workspace)
        result = list_files(workspace, globs=["**/*.py"])
        assert result["ok"] is True
        paths = {f["path"] for f in result["data"]}
        assert all(p.endswith(".py") for p in paths)
        assert "sub/c.txt" not in paths

    def test_ignore_pattern(self, workspace: Path) -> None:
        self._populate(workspace)
        result = list_files(workspace, ignore=["sub/**"])
        assert result["ok"] is True
        paths = {f["path"] for f in result["data"]}
        assert "sub/c.txt" not in paths

    def test_max_files_respected(self, workspace: Path) -> None:
        for i in range(10):
            (workspace / f"file_{i}.txt").write_text(f"content {i}\n", encoding="utf-8")
        result = list_files(workspace, max_files=3)
        assert result["ok"] is True
        assert len(result["data"]) <= 3

    def test_empty_workspace(self, workspace: Path) -> None:
        result = list_files(workspace)
        assert result["ok"] is True
        assert result["data"] == []

    def test_result_contains_size_bytes(self, workspace: Path) -> None:
        (workspace / "file.txt").write_text("hello\n", encoding="utf-8")
        result = list_files(workspace)
        assert result["ok"] is True
        assert result["data"]
        assert "size_bytes" in result["data"][0]


# ---------------------------------------------------------------------------
# rg_search
# ---------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("rg") is None, reason="ripgrep not installed")
class TestRgSearch:
    def _create_files(self, workspace: Path) -> None:
        (workspace / "alpha.py").write_text(
            "def foo():\n    return 'hello'\n", encoding="utf-8"
        )
        (workspace / "beta.py").write_text(
            "def bar():\n    return 'world'\n", encoding="utf-8"
        )
        (workspace / "readme.md").write_text(
            "# Project\n\nThis uses foo and bar.\n", encoding="utf-8"
        )

    def test_finds_pattern(self, workspace: Path) -> None:
        self._create_files(workspace)
        result = rg_search("foo", workspace)
        assert result["ok"] is True
        paths = {m["path"] for m in result["data"]["matches"]}
        assert any("alpha.py" in p for p in paths)

    def test_no_matches_returns_empty_list(self, workspace: Path) -> None:
        self._create_files(workspace)
        result = rg_search("zzz_no_match_zzz", workspace)
        assert result["ok"] is True
        assert result["data"]["matches"] == []

    def test_glob_filter_limits_files(self, workspace: Path) -> None:
        self._create_files(workspace)
        result = rg_search("foo", workspace, globs=["*.py"])
        assert result["ok"] is True
        for m in result["data"]["matches"]:
            assert m["path"].endswith(".py")

    def test_ignore_pattern_excludes_files(self, workspace: Path) -> None:
        self._create_files(workspace)
        result = rg_search("foo", workspace, ignore=["*.py"])
        assert result["ok"] is True
        for m in result["data"]["matches"]:
            assert not m["path"].endswith(".py")

    def test_max_results_respected(self, workspace: Path) -> None:
        # Create a file with many occurrences
        content = "\n".join(f"hit {i}" for i in range(100))
        (workspace / "many.txt").write_text(content, encoding="utf-8")
        result = rg_search("hit", workspace, max_results=5)
        assert result["ok"] is True
        assert len(result["data"]["matches"]) <= 5

    def test_result_includes_metadata(self, workspace: Path) -> None:
        self._create_files(workspace)
        result = rg_search("foo", workspace)
        assert result["ok"] is True
        assert result["data"]["query"] == "foo"
        assert isinstance(result["data"]["matches"], list)

    def test_match_has_line_number(self, workspace: Path) -> None:
        self._create_files(workspace)
        result = rg_search("return", workspace, globs=["alpha.py"])
        assert result["ok"] is True
        assert result["data"]["matches"]
        assert "line_number" in result["data"]["matches"][0]

    def test_invalid_regex_returns_error(self, workspace: Path) -> None:
        result = rg_search("(unclosed", workspace)
        # rg exits with non-zero on regex error; we expect ok=False
        assert result["ok"] is False


@pytest.mark.skipif(shutil.which("rg") is not None, reason="ripgrep is installed")
class TestRgSearchMissingBinary:
    def test_missing_rg_returns_error(self, workspace: Path) -> None:
        result = rg_search("anything", workspace)
        assert result["ok"] is False
        assert result["error"]["kind"] == "missing_binary"
