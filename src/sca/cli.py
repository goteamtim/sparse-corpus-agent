from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import typer
from rich import print
from rich.console import Console

from sca.config import get_config, setup_logging
from sca.runtime.agent import create_agent
from sca.runtime.sandbox import find_repo_root

app = typer.Typer(add_completion=False, help="Sparse Corpus Agent (sca)")

console = Console()
logger = logging.getLogger(__name__)


@app.command()
def chat() -> None:
    """
    Start an interactive chat session with the agent.
    
    The agent has access to repository files and can answer questions
    about the codebase. Type 'quit' or 'exit' to end the session.
    """
    # Setup logging
    setup_logging()
    
    # Find repo root and create agent
    repo_root = find_repo_root()
    logger.info(f"Starting chat session for repo: {repo_root}")
    
    print(f"[bold cyan]sca chat[/bold cyan]")
    print(f"[dim]Repo root:[/dim] {repo_root}")
    print(f"[dim]Type 'quit' or 'exit' to end session[/dim]\n")
    
    try:
        agent = create_agent(repo_root)
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
def explain(path: str) -> None:
    """Explain a file (placeholder - to be implemented)."""
    repo_root = find_repo_root()
    file_path = (repo_root / path).resolve()
    print(f"[bold]sca explain[/bold] {path}")
    print(f"[dim]Resolved:[/dim] {file_path}")
    print("[yellow]TODO:[/yellow] open_snippet + evidence-based explanation")


@app.command()
def find(query: str) -> None:
    """Search the repo (placeholder - to be implemented)."""
    repo_root = find_repo_root()
    print(f"[bold]sca find[/bold] {query!r}")
    print(f"[dim]Repo root:[/dim] {repo_root}")
    print("[yellow]TODO:[/yellow] rg_search + show matches with citations")


@app.command()
def history(path: str, grep: Optional[str] = typer.Option(None, "--grep")) -> None:
    """Show git history (placeholder - to be implemented)."""
    repo_root = find_repo_root()
    print(f"[bold]sca history[/bold] {path}")
    if grep:
        print(f"[dim]grep:[/dim] {grep}")
    print(f"[dim]Repo root:[/dim] {repo_root}")
    print("[yellow]TODO:[/yellow] git_log + git_blame summaries")
