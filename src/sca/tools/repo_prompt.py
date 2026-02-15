"""Load workspace context from AGENT.md and .agent/*.md files."""

from __future__ import annotations

import logging
from pathlib import Path

from sca.runtime.sandbox import safe_resolve_path

logger = logging.getLogger(__name__)


def read_repo_prompt(workspace_root: Path) -> str:
    """
    Load AGENT.md and supplementary .agent/*.md files from workspace root.

    This provides human-authored context about the workspace:
    - Conventions and coding patterns
    - Folder structure explanations
    - Domain glossary
    - Common pitfalls and gotchas

    Files are loaded in this order:
    1. AGENT.md (primary workspace context)
    2. .agent/*.md (supplementary context, sorted alphabetically)

    Note: .agent/skills/ subdirectories are NOT loaded here; skills
    are loaded separately via the skills system.

    Args:
        workspace_root: Workspace root path

    Returns:
        Combined contents separated by document delimiters, or empty string
    """
    content_parts: list[str] = []

    # 1. Load AGENT.md (primary)
    agent_md = safe_resolve_path("AGENT.md", workspace_root, must_exist=True)
    if agent_md:
        try:
            text = agent_md.read_text(encoding="utf-8")
            content_parts.append(text)
            logger.info(f"Loaded AGENT.md ({len(text)} chars)")
        except Exception as e:
            logger.error(f"Error reading AGENT.md: {e}")
    else:
        logger.warning(f"AGENT.md not found in {workspace_root}")

    # 2. Load .agent/*.md (supplementary, non-recursive)
    agent_dir = workspace_root / ".agent"
    if agent_dir.is_dir():
        md_files = sorted(agent_dir.glob("*.md"))
        for md_file in md_files:
            try:
                text = md_file.read_text(encoding="utf-8")
                content_parts.append(text)
                logger.info(
                    f"Loaded .agent/{md_file.name} ({len(text)} chars)"
                )
            except Exception as e:
                logger.error(f"Error reading .agent/{md_file.name}: {e}")
        if md_files:
            logger.info(f"Loaded {len(md_files)} supplementary .agent/*.md files")
    else:
        logger.debug("No .agent/ directory found")

    if not content_parts:
        return ""

    return "\n\n---\n\n".join(content_parts)
