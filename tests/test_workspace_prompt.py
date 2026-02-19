"""Tests for sca.tools.workspace_prompt: read_workspace_prompt."""

from __future__ import annotations

from pathlib import Path

from sca.tools.workspace_prompt import read_workspace_prompt


class TestReadWorkspacePrompt:
    def test_returns_empty_string_when_no_files(self, workspace: Path) -> None:
        result = read_workspace_prompt(workspace)
        assert result == ""

    def test_loads_agent_md(self, workspace: Path) -> None:
        (workspace / "AGENT.md").write_text("# context\n", encoding="utf-8")
        result = read_workspace_prompt(workspace)
        assert "# context" in result

    def test_loads_supplementary_agent_dir(self, workspace: Path) -> None:
        (workspace / "AGENT.md").write_text("primary\n", encoding="utf-8")
        agent_dir = workspace / ".agent"
        agent_dir.mkdir()
        (agent_dir / "extra.md").write_text("supplementary\n", encoding="utf-8")
        result = read_workspace_prompt(workspace)
        assert "primary" in result
        assert "supplementary" in result

    def test_supplementary_files_sorted_alphabetically(self, workspace: Path) -> None:
        (workspace / "AGENT.md").write_text("primary\n", encoding="utf-8")
        agent_dir = workspace / ".agent"
        agent_dir.mkdir()
        (agent_dir / "b_second.md").write_text("B\n", encoding="utf-8")
        (agent_dir / "a_first.md").write_text("A\n", encoding="utf-8")
        result = read_workspace_prompt(workspace)
        idx_a = result.index("A")
        idx_b = result.index("B")
        assert idx_a < idx_b

    def test_parts_joined_with_delimiter(self, workspace: Path) -> None:
        (workspace / "AGENT.md").write_text("primary\n", encoding="utf-8")
        agent_dir = workspace / ".agent"
        agent_dir.mkdir()
        (agent_dir / "extra.md").write_text("extra\n", encoding="utf-8")
        result = read_workspace_prompt(workspace)
        assert "---" in result

    def test_only_supplementary_without_agent_md(self, workspace: Path) -> None:
        agent_dir = workspace / ".agent"
        agent_dir.mkdir()
        (agent_dir / "info.md").write_text("only supplementary\n", encoding="utf-8")
        result = read_workspace_prompt(workspace)
        assert "only supplementary" in result

    def test_non_md_files_in_agent_dir_ignored(self, workspace: Path) -> None:
        (workspace / "AGENT.md").write_text("primary\n", encoding="utf-8")
        agent_dir = workspace / ".agent"
        agent_dir.mkdir()
        (agent_dir / "notes.txt").write_text("should be ignored\n", encoding="utf-8")
        result = read_workspace_prompt(workspace)
        assert "should be ignored" not in result

    def test_skills_subdir_not_loaded(self, workspace: Path) -> None:
        (workspace / "AGENT.md").write_text("primary\n", encoding="utf-8")
        skills_dir = workspace / ".agent" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "skill.md").write_text("skill content\n", encoding="utf-8")
        result = read_workspace_prompt(workspace)
        assert "skill content" not in result
