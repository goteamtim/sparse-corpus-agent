"""Skills system: discover, parse, and load SKILL.md workflow prompts."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)

SKILLS_DIR = ".agent/skills"


@dataclass
class Skill:
    """Parsed skill from a SKILL.md file."""

    name: str
    description: str
    invoke: str = "manual"  # "manual" | "auto"
    triggers: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    domain: str | None = None
    body: str = ""  # Markdown instructions below frontmatter
    path: Path = field(default_factory=lambda: Path("."))

    @property
    def summary(self) -> str:
        """One-line summary for listing."""
        mode = "auto" if self.invoke == "auto" else "manual"
        return f"{self.name} ({mode}) — {self.description}"


def parse_skill_md(content: str, file_path: Path) -> Skill | None:
    """
    Parse a SKILL.md file with YAML frontmatter and markdown body.

    Expected format:
        ---
        name: review
        description: Perform a repo-aware code review
        invoke: manual
        triggers: [...]
        tools: [...]
        ---

        # Review skill
        ...markdown instructions...

    Args:
        content: Raw text of the SKILL.md file
        file_path: Path to the SKILL.md file (for error reporting)

    Returns:
        Parsed Skill, or None if parsing fails
    """
    content = content.strip()

    if not content.startswith("---"):
        logger.error(f"SKILL.md missing YAML frontmatter: {file_path}")
        return None

    # Split frontmatter from body
    parts = content.split("---", 2)
    if len(parts) < 3:
        logger.error(f"SKILL.md malformed frontmatter: {file_path}")
        return None

    frontmatter_raw = parts[1].strip()
    body = parts[2].strip()

    try:
        meta = yaml.safe_load(frontmatter_raw)
    except yaml.YAMLError as e:
        logger.error(f"SKILL.md YAML parse error in {file_path}: {e}")
        return None

    if not isinstance(meta, dict):
        logger.error(f"SKILL.md frontmatter is not a mapping: {file_path}")
        return None

    # Validate required fields
    name = meta.get("name")
    description = meta.get("description")
    if not name or not description:
        logger.error(
            f"SKILL.md missing required 'name' or 'description': {file_path}"
        )
        return None

    return Skill(
        name=str(name),
        description=str(description),
        invoke=str(meta.get("invoke", "manual")),
        triggers=[str(t) for t in meta.get("triggers", [])],
        tools=[str(t) for t in meta.get("tools", [])],
        domain=str(meta["domain"]) if meta.get("domain") else None,
        body=body,
        path=file_path,
    )


def discover_skills(workspace_root: Path) -> list[Skill]:
    """
    Scan .agent/skills/ for all valid SKILL.md files.

    Args:
        workspace_root: Workspace root path

    Returns:
        List of parsed Skill objects, sorted by name
    """
    skills_dir = workspace_root / SKILLS_DIR

    if not skills_dir.is_dir():
        logger.debug(f"No skills directory found at {skills_dir}")
        return []

    skills: list[Skill] = []

    for skill_dir in sorted(skills_dir.iterdir()):
        if not skill_dir.is_dir():
            continue

        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            logger.debug(f"Skipping {skill_dir.name}: no SKILL.md")
            continue

        try:
            content = skill_md.read_text(encoding="utf-8")
            skill = parse_skill_md(content, skill_md)
            if skill:
                skills.append(skill)
                logger.info(f"Loaded skill: {skill.name} from {skill_dir.name}/")
        except Exception as e:
            logger.error(f"Error reading {skill_md}: {e}")

    logger.info(f"Discovered {len(skills)} skill(s)")
    return skills


def load_skill(name: str, workspace_root: Path) -> Skill | None:
    """
    Load a single skill by name.

    Args:
        name: Skill name (directory name under .agent/skills/)
        workspace_root: Workspace root path

    Returns:
        Parsed Skill, or None if not found/invalid
    """
    skill_md = workspace_root / SKILLS_DIR / name / "SKILL.md"

    if not skill_md.is_file():
        logger.warning(f"Skill not found: {name}")
        return None

    try:
        content = skill_md.read_text(encoding="utf-8")
        skill = parse_skill_md(content, skill_md)
        if skill:
            logger.info(f"Loaded skill: {skill.name}")
        return skill
    except Exception as e:
        logger.error(f"Error loading skill {name}: {e}")
        return None


def load_skill_supporting_files(skill: Skill, workspace_root: Path) -> dict[str, str]:
    """
    Load supporting reference files for a skill (checklists, templates, etc.).

    Reads all non-SKILL.md files in the skill directory.

    Args:
        skill: The skill whose supporting files to load
        workspace_root: Workspace root path

    Returns:
        Dictionary mapping filename to content
    """
    skill_dir = skill.path.parent
    supporting: dict[str, str] = {}

    if not skill_dir.is_dir():
        return supporting

    for f in sorted(skill_dir.iterdir()):
        if f.is_file() and f.name != "SKILL.md":
            try:
                supporting[f.name] = f.read_text(encoding="utf-8")
                logger.debug(f"Loaded supporting file: {f.name}")
            except Exception as e:
                logger.warning(f"Cannot read supporting file {f.name}: {e}")

    return supporting


def build_skill_prompt(skill: Skill, workspace_root: Path) -> str:
    """
    Build a prompt section from a skill's instructions and supporting files.

    Args:
        skill: Parsed skill to build prompt for
        workspace_root: Workspace root path

    Returns:
        Formatted skill prompt string for injection into system instructions
    """
    parts: list[str] = []

    parts.append(f"## Active Skill: {skill.name}")
    parts.append(f"*{skill.description}*\n")

    if skill.body:
        parts.append(skill.body)

    # Load and append supporting files
    supporting = load_skill_supporting_files(skill, workspace_root)
    for filename, content in supporting.items():
        parts.append(f"\n### Reference: {filename}\n")
        parts.append(content)

    return "\n\n".join(parts)
