"""PydanticAI agent initialization and tool registration."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel

from sca.config import get_config
from sca.runtime.sandbox import find_workspace_root
from sca.tools.files import file_stats, list_files, open_snippet, rg_search
from sca.tools.repo_prompt import read_repo_prompt

logger = logging.getLogger(__name__)


def create_agent(workspace_root: Path, skill_prompt: str | None = None) -> Agent:
    """
    Create a PydanticAI agent with workspace-aware tools.
    
    The agent is initialized with:
    - OpenAI-compatible model (LM Studio, Ollama, etc.)
    - System prompt from AGENT.md + .agent/*.md (if exists)
    - Optionally, a skill prompt for workflow-specific instructions
    - File reading/search tools
    
    Conversation history management:
    - Pass result.all_messages() to message_history param in subsequent runs
    - PydanticAI handles context window automatically
    - History processors can be added later for token management
    
    Args:
        workspace_root: Workspace root path for tool context
        skill_prompt: Optional skill instructions to append to system prompt
    
    Returns:
        Configured Agent instance
    """
    config = get_config()
    
    # Initialize OpenAI-compatible model (works with LM Studio, Ollama)
    # Set environment variables for OpenAI client configuration
    os.environ['OPENAI_BASE_URL'] = config.openai_base_url
    os.environ['OPENAI_API_KEY'] = config.openai_api_key
    
    model = OpenAIChatModel(config.model_name)
    
    # Load workspace context from AGENT.md
    workspace_context = read_repo_prompt(workspace_root)
    
    # Build system instructions
    system_instructions = build_system_prompt(workspace_context, workspace_root, skill_prompt)
    
    logger.info(f"Creating agent with model: {config.model_name}")
    logger.debug(f"Base URL: {config.openai_base_url}")
    logger.debug(f"Workspace root: {workspace_root}")
    
    # Create agent with tools
    agent = Agent(
        model,
        instructions=system_instructions,
        retries=2,  # Retry on transient failures
    )
    
    # Register file tools with repo context
    @agent.tool
    def read_file_snippet(
        ctx: RunContext,
        path: str,
        start_line: int = 1,
        end_line: int | None = None,
    ) -> str:
        """
        Read a line-ranged snippet from a file in the workspace.
        
        Evidence-first: All file references must cite line ranges.
        
        Args:
            path: File path relative to workspace root
            start_line: First line to read (1-indexed, inclusive)
            end_line: Last line to read (1-indexed, inclusive). If None, reads to end of file
        
        Returns:
            File content for specified line range
        """
        return open_snippet(path, workspace_root, start_line, end_line)
    
    @agent.tool
    def get_file_info(ctx: RunContext, path: str) -> dict:
        """
        Get file metadata without reading content.
        
        Useful for checking if a file exists, determining size, or detecting binary files.
        
        Args:
            path: File path relative to workspace root
        
        Returns:
            Dictionary with exists, size_bytes, line_count, is_binary fields
        """
        return file_stats(path, workspace_root)

    @agent.tool
    def search_files(
        ctx: RunContext,
        query: str,
        globs: list[str] | None = None,
        ignore: list[str] | None = None,
        max_results: int = 50,
        context_lines: int = 2,
    ) -> list[dict]:
        """
        Search the workspace using ripgrep.

        Returns structured matches with file paths, line numbers, and context.

        Args:
            query: Search pattern (regex)
            globs: File glob filters (e.g. ["*.py", "*.md"])
            ignore: Glob patterns to exclude
            max_results: Maximum matches to return
            context_lines: Lines of context around each match

        Returns:
            List of match dicts with path, line_number, line_text fields
        """
        return rg_search(query, workspace_root, globs, ignore, max_results, context_lines)

    @agent.tool
    def find_files(
        ctx: RunContext,
        globs: list[str] | None = None,
        ignore: list[str] | None = None,
        max_files: int = 500,
        include_hidden: bool = False,
    ) -> list[dict]:
        """
        List files in the workspace matching glob patterns.

        Args:
            globs: Glob patterns to match (e.g. ["**/*.py"]). Defaults to all files
            ignore: Glob patterns to exclude
            max_files: Maximum number of files to return
            include_hidden: Whether to include hidden files/directories

        Returns:
            List of dicts with path and size_bytes fields
        """
        return list_files(workspace_root, globs, ignore, max_files, include_hidden)

    logger.info(
        "Agent created with 4 tools: "
        "read_file_snippet, get_file_info, search_files, find_files"
    )
    
    return agent


def build_system_prompt(
    workspace_context: str,
    workspace_root: Path,
    skill_prompt: str | None = None,
) -> str:
    """
    Build system prompt combining framework instructions, workspace context, and skill.
    
    Args:
        workspace_context: Content from AGENT.md and .agent/*.md
        workspace_root: Workspace root path
        skill_prompt: Optional skill instructions to append
    
    Returns:
        Complete system prompt string
    """
    base_prompt = f"""You are a code exploration assistant for a workspace.

Workspace root: {workspace_root}

Core principles:
- Evidence-first: All claims must cite file paths and line ranges
- Never guess: Use tools to retrieve actual code before answering
- Be concise but thorough: Provide relevant context without unnecessary detail

Available tools:
- read_file_snippet: Read specific line ranges from files
- get_file_info: Check file metadata (size, existence, type)
- search_files: Search workspace content with ripgrep (regex patterns)
- find_files: List files matching glob patterns

When answering questions:
1. Use tools to gather evidence from the workspace
2. Cite specific file paths and line numbers in your responses
3. If uncertain, state what information is missing and what tools could help
"""
    
    if workspace_context:
        base_prompt += f"\n\n## Workspace Context\n\n{workspace_context}"
        logger.debug(f"Added {len(workspace_context)} chars of workspace context from AGENT.md")
    else:
        logger.debug("No AGENT.md found, using base prompt only")

    if skill_prompt:
        base_prompt += f"\n\n{skill_prompt}"
        logger.debug(f"Added {len(skill_prompt)} chars of skill prompt")

    return base_prompt
