"""PydanticAI agent initialization and tool registration."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIModel

from sca.config import get_config
from sca.runtime.sandbox import find_repo_root
from sca.tools.files import file_stats, open_snippet
from sca.tools.repo_prompt import read_repo_prompt

logger = logging.getLogger(__name__)


def create_agent(repo_root: Path) -> Agent:
    """
    Create a PydanticAI agent with repo-aware tools.
    
    The agent is initialized with:
    - OpenAI-compatible model (LM Studio, Ollama, etc.)
    - System prompt from AGENT.md (if exists)
    - File reading tools (open_snippet, file_stats)
    
    Conversation history management:
    - Pass result.all_messages() to message_history param in subsequent runs
    - PydanticAI handles context window automatically
    - History processors can be added later for token management
    
    Args:
        repo_root: Repository root path for tool context
    
    Returns:
        Configured Agent instance
    """
    config = get_config()
    
    # Initialize OpenAI-compatible model (works with LM Studio, Ollama)
    model = OpenAIModel(
        config.model_name,
        base_url=config.openai_base_url,
        api_key=config.openai_api_key,
    )
    
    # Load repo context from AGENT.md
    repo_context = read_repo_prompt(repo_root)
    
    # Build system instructions
    system_instructions = build_system_prompt(repo_context, repo_root)
    
    logger.info(f"Creating agent with model: {config.model_name}")
    logger.debug(f"Base URL: {config.openai_base_url}")
    logger.debug(f"Repo root: {repo_root}")
    
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
        Read a line-ranged snippet from a file in the repository.
        
        Evidence-first: All file references must cite line ranges.
        
        Args:
            path: File path relative to repo root
            start_line: First line to read (1-indexed, inclusive)
            end_line: Last line to read (1-indexed, inclusive). If None, reads to end of file
        
        Returns:
            File content for specified line range
        """
        return open_snippet(path, repo_root, start_line, end_line)
    
    @agent.tool
    def get_file_info(ctx: RunContext, path: str) -> dict:
        """
        Get file metadata without reading content.
        
        Useful for checking if a file exists, determining size, or detecting binary files.
        
        Args:
            path: File path relative to repo root
        
        Returns:
            Dictionary with exists, size_bytes, line_count, is_binary fields
        """
        return file_stats(path, repo_root)
    
    logger.info("Agent created with 2 tools: read_file_snippet, get_file_info")
    
    return agent


def build_system_prompt(repo_context: str, repo_root: Path) -> str:
    """
    Build system prompt combining framework instructions and repo context.
    
    Args:
        repo_context: Content from AGENT.md
        repo_root: Repository root path
    
    Returns:
        Complete system prompt string
    """
    base_prompt = f"""You are a code exploration assistant for a repository.

Repository root: {repo_root}

Core principles:
- Evidence-first: All claims must cite file paths and line ranges
- Never guess: Use tools to retrieve actual code before answering
- Be concise but thorough: Provide relevant context without unnecessary detail

Available tools:
- read_file_snippet: Read specific line ranges from files
- get_file_info: Check file metadata (size, existence, type)

When answering questions:
1. Use tools to gather evidence from the repository
2. Cite specific file paths and line numbers in your responses
3. If uncertain, state what information is missing and what tools could help
"""
    
    if repo_context:
        base_prompt += f"\n\n## Repository Context\n\n{repo_context}"
        logger.debug(f"Added {len(repo_context)} chars of repo context from AGENT.md")
    else:
        logger.debug("No AGENT.md found, using base prompt only")
    
    return base_prompt
