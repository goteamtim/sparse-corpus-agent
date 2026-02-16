# Sparse Corpus Agent Repository

This is a Python 3.12+ CLI agent framework for evidence-first code exploration.

## Project Structure

- `src/sca/` - Main package
  - `cli.py` - CLI commands (chat, explain, find, history)
  - `config.py` - Environment configuration and logging
  - `runtime/` - Agent runtime and sandboxing
  - `tools/` - File reading and repo context tools

## Conventions

- All file operations are sandboxed to repo root
- Evidence-first: cite file paths and line ranges
- Read-only operations only (no file editing in MVP)
- Local-first: designed for LM Studio/Ollama

## Key Files

- `README.md` - High-level specification
- `pyproject.toml` - Package configuration and dependencies
- `requirements.txt` - Pip-installable dependencies

## Getting Started

1. Install dependencies: `pip install -r requirements.txt`
2. Set environment variables:
   ```bash
   export OPENAI_BASE_URL="http://localhost:1234/v1"
   export MODEL_NAME="your-model-name"
   ```
3. Run chat: `python -m sca chat`
