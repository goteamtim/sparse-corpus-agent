"""Tests for sca.runtime.sandbox: validate_path, safe_resolve_path, find_workspace_root."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from sca.runtime.sandbox import find_workspace_root, safe_resolve_path, validate_path


# ---------------------------------------------------------------------------
# validate_path
# ---------------------------------------------------------------------------


class TestValidatePath:
    def test_path_inside_workspace_is_valid(self, workspace: Path) -> None:
        child = workspace / "file.txt"
        assert validate_path(child, workspace) is True

    def test_path_equal_to_workspace_is_valid(self, workspace: Path) -> None:
        assert validate_path(workspace, workspace) is True

    def test_nested_path_is_valid(self, workspace: Path) -> None:
        nested = workspace / "a" / "b" / "c.txt"
        assert validate_path(nested, workspace) is True

    def test_path_outside_workspace_is_invalid(self, workspace: Path) -> None:
        outside = workspace.parent / "other_dir" / "file.txt"
        assert validate_path(outside, workspace) is False

    def test_path_traversal_attempt_is_invalid(self, workspace: Path) -> None:
        traversal = workspace / ".." / "escape.txt"
        assert validate_path(traversal, workspace) is False

    def test_absolute_path_outside_is_invalid(self, workspace: Path) -> None:
        assert validate_path(Path("/etc/passwd"), workspace) is False


# ---------------------------------------------------------------------------
# safe_resolve_path
# ---------------------------------------------------------------------------


class TestSafeResolvePath:
    def test_relative_path_resolves_inside_workspace(self, workspace: Path) -> None:
        (workspace / "hello.txt").write_text("hi\n", encoding="utf-8")
        result = safe_resolve_path("hello.txt", workspace)
        assert result is not None
        assert result == workspace.resolve() / "hello.txt"

    def test_absolute_path_inside_workspace(self, workspace: Path) -> None:
        f = workspace / "hi.txt"
        f.write_text("hi\n", encoding="utf-8")
        result = safe_resolve_path(str(f), workspace)
        assert result is not None
        assert result == f.resolve()

    def test_path_outside_workspace_returns_none(self, workspace: Path) -> None:
        result = safe_resolve_path("/etc/passwd", workspace)
        assert result is None

    def test_must_exist_true_missing_file_returns_none(self, workspace: Path) -> None:
        result = safe_resolve_path("nonexistent.txt", workspace, must_exist=True)
        assert result is None

    def test_must_exist_false_missing_file_returns_path(self, workspace: Path) -> None:
        result = safe_resolve_path("nonexistent.txt", workspace, must_exist=False)
        assert result is not None
        assert result == workspace.resolve() / "nonexistent.txt"

    def test_must_exist_true_existing_file_returns_path(self, workspace: Path) -> None:
        (workspace / "exists.txt").write_text("data\n", encoding="utf-8")
        result = safe_resolve_path("exists.txt", workspace, must_exist=True)
        assert result is not None

    def test_path_traversal_returns_none(self, workspace: Path) -> None:
        result = safe_resolve_path("../../etc/passwd", workspace, must_exist=False)
        assert result is None

    def test_accepts_path_object(self, workspace: Path) -> None:
        (workspace / "pathobj.txt").write_text("ok\n", encoding="utf-8")
        result = safe_resolve_path(Path("pathobj.txt"), workspace, must_exist=True)
        assert result is not None

    def test_nested_relative_path(self, workspace: Path) -> None:
        sub = workspace / "sub"
        sub.mkdir()
        (sub / "deep.txt").write_text("deep\n", encoding="utf-8")
        result = safe_resolve_path("sub/deep.txt", workspace, must_exist=True)
        assert result is not None
        assert result.name == "deep.txt"


# ---------------------------------------------------------------------------
# find_workspace_root
# ---------------------------------------------------------------------------


class TestFindWorkspaceRoot:
    def test_explicit_repo_path(self, workspace: Path) -> None:
        root = find_workspace_root(repo_path=workspace)
        assert root == workspace.resolve()

    def test_explicit_repo_path_not_exist_raises(self, tmp_path: Path) -> None:
        ghost = tmp_path / "does_not_exist"
        with pytest.raises(ValueError):
            find_workspace_root(repo_path=ghost)

    def test_explicit_repo_path_file_raises(self, workspace: Path) -> None:
        f = workspace / "file.txt"
        f.write_text("x\n", encoding="utf-8")
        with pytest.raises(ValueError):
            find_workspace_root(repo_path=f)

    def test_sca_repo_env_var(self, workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SCA_REPO", str(workspace))
        root = find_workspace_root()
        assert root == workspace.resolve()

    def test_sca_workspace_root_legacy_env_var(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCA_REPO", raising=False)
        monkeypatch.setenv("SCA_WORKSPACE_ROOT", str(workspace))
        root = find_workspace_root()
        assert root == workspace.resolve()

    def test_sca_repo_nonexistent_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("SCA_REPO", "/does/not/exist/ever")
        with pytest.raises(ValueError):
            find_workspace_root()

    def test_auto_detect_via_git_marker(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCA_REPO", raising=False)
        monkeypatch.delenv("SCA_WORKSPACE_ROOT", raising=False)
        git_dir = workspace / ".git"
        git_dir.mkdir()
        root = find_workspace_root(start=workspace)
        assert root == workspace.resolve()

    def test_auto_detect_via_agent_md_marker(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCA_REPO", raising=False)
        monkeypatch.delenv("SCA_WORKSPACE_ROOT", raising=False)
        (workspace / "AGENT.md").write_text("# agent\n", encoding="utf-8")
        root = find_workspace_root(start=workspace)
        assert root == workspace.resolve()

    def test_auto_detect_from_subdirectory(
        self, workspace: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCA_REPO", raising=False)
        monkeypatch.delenv("SCA_WORKSPACE_ROOT", raising=False)
        (workspace / ".git").mkdir()
        sub = workspace / "deep" / "sub"
        sub.mkdir(parents=True)
        root = find_workspace_root(start=sub)
        assert root == workspace.resolve()

    def test_no_marker_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("SCA_REPO", raising=False)
        monkeypatch.delenv("SCA_WORKSPACE_ROOT", raising=False)
        # Use a directory that has no .git or AGENT.md anywhere in its tree
        isolated = tmp_path / "isolated"
        isolated.mkdir()
        with pytest.raises(ValueError):
            find_workspace_root(start=isolated)
