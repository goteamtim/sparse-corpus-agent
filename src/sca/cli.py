from __future__ import annotations

import logging
import os
import shutil
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console

from sca.config import get_config, setup_logging
from sca.runtime.agent import create_agent
from sca.runtime.sandbox import find_workspace_root
from sca.skills import Skill, build_skill_prompt, discover_skills, load_skill
from sca.tools.files import open_snippet, file_stats, rg_search

app = typer.Typer(add_completion=False, help="Sparse Corpus Agent (sca)")
skill_app = typer.Typer(help="Manage and run skills")
app.add_typer(skill_app, name="skill")

console = Console()
logger = logging.getLogger(__name__)


def resolve_repo_arg(repo: Optional[str]) -> Optional[Path]:
    """Resolve an explicit --repo value or SCA_REPO env var to a Path."""
    if repo:
        return Path(repo).expanduser().resolve()
    env = os.getenv("SCA_REPO")
    if env:
        return Path(env).expanduser().resolve()
    return None


def _check_ripgrep() -> None:
    """Check that ripgrep is available on PATH, exit with guidance if not."""
    if shutil.which("rg") is None:
        print("[red]Missing required tool: ripgrep (rg)[/red]\n")
        print("Install ripgrep:")
        print("  • [bold]Windows:[/bold]  winget install BurntSushi.ripgrep.MSVC")
        print("  • [bold]macOS:[/bold]    brew install ripgrep")
        print("  • [bold]Linux:[/bold]    apt install ripgrep")
        print(f"\n[dim]https://github.com/BurntSushi/ripgrep[/dim]")
        raise typer.Exit(code=1)


@app.command()
def chat(
    skill_name: str = typer.Option(None, "--skill", "-s", help="Load a skill by name"),
    repo: Optional[str] = typer.Option(None, "--repo", help="Path to target repo"),
) -> None:
    """
    Start an interactive chat session with the agent.
    
    The agent has access to workspace files and can answer questions
    about the codebase. Type 'quit' or 'exit' to end the session.

    Use --skill to start with a skill loaded, or type /skillname
    during the session to load one on the fly.
    """
    # Setup logging
    setup_logging()
    _check_ripgrep()
    
    # Find workspace root and create agent
    workspace_root = find_workspace_root(repo_path=resolve_repo_arg(repo))
    logger.info(f"Starting chat session for workspace: {workspace_root}")

    # Load skill if specified
    active_skill: Skill | None = None
    active_skill_prompt: str | None = None
    if skill_name:
        active_skill = load_skill(skill_name, workspace_root)
        if active_skill:
            active_skill_prompt = build_skill_prompt(active_skill, workspace_root)
            print(f"[bold magenta]Using skill:[/bold magenta] {active_skill.name} — {active_skill.description}")
        else:
            print(f"[red]Error:[/red] Skill '{skill_name}' not found")
            raise typer.Exit(code=1)
    
    print(f"[bold cyan]sca chat[/bold cyan]")
    print(f"[dim]Workspace root:[/dim] {workspace_root}")
    print(f"[dim]Type 'quit' or 'exit' to end session[/dim]")
    print(f"[dim]Type '/skillname' to load a skill[/dim]\n")
    
    try:
        agent = create_agent(workspace_root, skill_prompt=active_skill_prompt, active_skill=active_skill)
    except Exception as e:
        logger.error(f"Failed to create agent: {e}")
        print(f"[red]Error:[/red] Could not initialize agent: {e}")
        print("[yellow]Check your OPENAI_BASE_URL and MODEL_NAME environment variables[/yellow]")
        raise typer.Exit(code=1)
    
    # Conversation state
    message_history = []
    
    # Main chat loop
    while True:
        try:
            # Get user input
            user_input = typer.prompt("\n[You]", prompt_suffix=" ")
            
            # Check for exit commands
            if user_input.lower() in ["quit", "exit", "q"]:
                print("[dim]Goodbye![/dim]")
                break
            
            if not user_input.strip():
                continue

            # Check for /skill invocation
            if user_input.startswith("/"):
                new_skill_name = user_input[1:].strip()
                if not new_skill_name:
                    continue
                new_skill = load_skill(new_skill_name, workspace_root)
                if new_skill:
                    active_skill = new_skill
                    active_skill_prompt = build_skill_prompt(active_skill, workspace_root)
                    # Recreate agent with new skill, preserving nothing
                    # (skill changes are a fresh context)
                    try:
                        agent = create_agent(workspace_root, skill_prompt=active_skill_prompt, active_skill=active_skill)
                    except ValueError as e:
                        print(f"[red]Error loading skill:[/red] {e}")
                        continue
                    message_history = []
                    print(f"[bold magenta]Loaded skill:[/bold magenta] {active_skill.name} — {active_skill.description}")
                    print("[dim]Conversation reset for new skill context.[/dim]")
                else:
                    print(f"[yellow]Skill '{new_skill_name}' not found.[/yellow] Use 'sca skill list' to see available skills.")
                continue
            
            # Run agent with conversation history
            print("[dim]Agent is thinking...[/dim]")
            
            try:
                result = agent.run_sync(
                    user_input,
                    message_history=message_history if message_history else None
                )
                
                # Update conversation history with new messages
                message_history = result.all_messages()
                
                # Display response
                print(f"\n[bold green][Agent][/bold green] {result.output}\n")
                
            except Exception as e:
                logger.error(f"Agent run failed: {e}", exc_info=True)
                print(f"[red]Error:[/red] Agent failed to respond: {e}")
                print("[yellow]The conversation history has been preserved. Try again.[/yellow]")
        
        except KeyboardInterrupt:
            print("\n[dim]Goodbye![/dim]")
            break
        except EOFError:
            print("\n[dim]Goodbye![/dim]")
            break


@app.command()
def explain(
    path: str,
    repo: Optional[str] = typer.Option(None, "--repo", help="Path to target repo"),
) -> None:
    """
    Explain a file using snippets and citations.

    Reads the file, gathers basic stats, and uses the agent to produce
    an evidence-based explanation.
    """
    setup_logging()
    workspace_root = find_workspace_root(repo_path=resolve_repo_arg(repo))

    print(f"[bold cyan]sca explain[/bold cyan] {path}")
    print(f"[dim]Workspace root:[/dim] {workspace_root}\n")

    # Get file stats first
    stats_result = file_stats(path, workspace_root)
    if not stats_result["ok"]:
        error_msg = stats_result["error"]["message"] if stats_result["error"] else "Unknown error"
        print(f"[red]Error:[/red] {error_msg}")
        raise typer.Exit(code=1)
    
    stats = stats_result["data"]
    if stats.get("is_binary"):
        print(f"[red]Error:[/red] Cannot explain binary file: {path}")
        raise typer.Exit(code=1)

    print(f"[dim]File:[/dim] {stats.get('path')} ({stats.get('line_count', '?')} lines, {stats.get('size_bytes', '?')} bytes)\n")

    # Read the full file content for the agent
    content_result = open_snippet(path, workspace_root)
    if not content_result["ok"]:
        error_msg = content_result["error"]["message"] if content_result["error"] else "Unknown error"
        print(f"[red]Error:[/red] {error_msg}")
        raise typer.Exit(code=1)
    
    content = content_result["data"]["text"]

    try:
        agent = create_agent(workspace_root)
    except Exception as e:
        print(f"[red]Error:[/red] Could not initialize agent: {e}")
        raise typer.Exit(code=1)

    prompt = (
        f"Explain the file `{path}` in detail. Here is the full content:\n\n"
        f"```\n{content}\n```\n\n"
        "Provide:\n"
        "1. Purpose and responsibility of this file\n"
        "2. Key functions/classes and what they do\n"
        "3. Dependencies and how it fits into the larger project\n"
        "4. Cite specific line numbers for important sections"
    )

    print("[dim]Agent is thinking...[/dim]")
    try:
        result = agent.run_sync(prompt)
        print(f"\n{result.output}\n")
    except Exception as e:
        logger.error(f"Agent run failed: {e}", exc_info=True)
        print(f"[red]Error:[/red] Agent failed: {e}")
        raise typer.Exit(code=1)


@app.command()
def find(
    query: str,
    repo: Optional[str] = typer.Option(None, "--repo", help="Path to target repo"),
) -> None:
    """
    Search the workspace and show matches with citations.

    Uses ripgrep to search for the query and displays results
    with file paths, line numbers, and context.
    """
    setup_logging()
    _check_ripgrep()
    workspace_root = find_workspace_root(repo_path=resolve_repo_arg(repo))

    print(f"[bold cyan]sca find[/bold cyan] {query!r}")
    print(f"[dim]Workspace root:[/dim] {workspace_root}\n")

    search_result = rg_search(query, workspace_root)
    
    if not search_result["ok"]:
        error_msg = search_result["error"]["message"] if search_result["error"] else "Unknown error"
        print(f"[red]Error:[/red] {error_msg}")
        raise typer.Exit(code=1)
    
    matches = search_result["data"]["matches"]

    if not matches:
        print("[yellow]No matches found.[/yellow]")
        return

    print(f"[bold]{len(matches)} match(es):[/bold]\n")

    for m in matches:
        path = m.get("path", "?")
        line_num = m.get("line_number", "?")
        line_text = m.get("line_text", "").strip()
        print(f"  [cyan]{path}[/cyan]:[yellow]{line_num}[/yellow]  {line_text}")

        # Show context if available
        ctx_before = m.get("context_before", [])
        for ctx_line in ctx_before:
            print(f"    [dim]{ctx_line}[/dim]")

    print()


# ── Skill subcommands ──────────────────────────────────────────────


@skill_app.command("list")
def skill_list(
    repo: Optional[str] = typer.Option(None, "--repo", help="Path to target repo"),
) -> None:
    """List available skills in .agent/skills/."""
    setup_logging()
    workspace_root = find_workspace_root(repo_path=resolve_repo_arg(repo))
    skills = discover_skills(workspace_root)

    if not skills:
        print("[yellow]No skills found.[/yellow]")
        print(f"[dim]Looked in: {workspace_root / '.agent' / 'skills'}[/dim]")
        print("[dim]Create a skill by adding .agent/skills/<name>/SKILL.md[/dim]")
        return

    print(f"[bold cyan]Available skills ({len(skills)}):[/bold cyan]\n")
    for s in skills:
        mode_tag = "[green]auto[/green]" if s.invoke == "auto" else "[dim]manual[/dim]"
        print(f"  [bold]{s.name}[/bold]  {mode_tag}")
        print(f"    {s.description}")
        if s.triggers:
            print(f"    [dim]triggers:[/dim] {', '.join(s.triggers)}")
        if s.tools:
            print(f"    [dim]tools:[/dim] {', '.join(s.tools)}")
        print()


@skill_app.command("run")
def skill_run(
    name: str,
    repo: Optional[str] = typer.Option(None, "--repo", help="Path to target repo"),
) -> None:
    """
    Run a skill by name (starts a chat session with the skill loaded).

    Equivalent to: sca chat --skill <name>
    """
    setup_logging()
    workspace_root = find_workspace_root(repo_path=resolve_repo_arg(repo))

    skill = load_skill(name, workspace_root)
    if not skill:
        print(f"[red]Error:[/red] Skill '{name}' not found")
        print("[dim]Use 'sca skill list' to see available skills[/dim]")
        raise typer.Exit(code=1)

    # Delegate to chat with skill loaded
    chat(skill_name=name, repo=repo)
