# Sparse Corpus Agent Framework

A **local-first, evidence-first CLI agent** for working inside a code repository—especially useful when a repo has domain-specific conventions that general coding agents don’t reliably pick up.

This repo provides a **generic framework** with a minimal toolset and a lightweight “skills” system for hand-holding the model on repeatable workflows.

---

## Opinions (locked in)

### Python version
- **Python 3.12.x** (recommended: latest patch release of 3.12)

Why 3.12:
- Modern stdlib + performance improvements, widely supported by the ecosystem.
- Meets **PydanticAI’s** baseline requirement (Python **3.10+**).

> We intentionally avoid “latest alpha/beta” Python versions for MVP stability.

### Environment + dependency management
- **Recommended:** `uv` (fast, single-tool workflow: create venv + install deps + global cache)
- **Supported fallback:** `python -m venv` + `pip`

Why `uv`:
- One command surface for most things (`uv venv`, `uv pip …`, later `uv lock/sync`).
- Plays nicely with existing workflows (you can still use `requirements.txt` initially).

---

## Core ideas

### Evidence-first answers
The agent should not “guess.” If it claims something about the repo, it should point to **file paths + line ranges** (snippets) or **git evidence** (commits/blame).

### Local-first runtime
Designed to run with a local LLM server (e.g. **LM Studio**) and a lightweight agent runtime (e.g. **PydanticAI**). The framework intentionally avoids requiring a hosted model.

### Human repo context (`AGENT.md`)
A human-authored repo guide provides the “meaning” that auto-discovery can’t:
- what the repo is
- what folders matter
- conventions/glossary
- entrypoints
- what not to touch

The agent automatically loads this file (and optionally `.agent/*.md`) as the first context for every run.

---

## MVP scope: tools

### repo-safe primitives
1. **`read_repo_prompt()`**
   - Loads `AGENT.md` (and optional `.agent/*.md`) from repo root.
2. **`list_files(globs, ignore, max_files, include_hidden=False)`**
   - Returns a structured list of paths and basic metadata.
3. **`open_snippet(path, start_line, end_line)`**
   - Returns a line-ranged snippet for citations.
4. **`rg_search(query, globs, ignore, max_results, context_lines)`**
   - Ripgrep-style search with structured match results.
5. **`file_stats(path)`**
   - Size, line count, binary detection, hash (for “don’t open huge/minified/binary” decisions).

### git evidence tools
1. **`git_status()`**
   - Basic working tree status.
2. **`git_log(path=None, grep=None, max_commits=20)`**
   - “When did X change?” / “what commits mention Y?”
3. **`git_show(ref, path=None)`**
   - Show a file at a ref, or show commit content summary.
4. **`git_blame(path, line)`**
   - “Who changed this line and when?”

> Note: all tools are **repo-root sandboxed**. No reading outside repo root. No arbitrary shell execution.

---

## Skills (lightweight, sharable workflow prompts)

Niche codebases often require “hand holding” to keep the model on the rails. This project supports **skills**, inspired by the general idea of packaging repeatable instructions as small folders. In Claude Code, skills are described as a `SKILL.md` file plus optional supporting files, invoked automatically when relevant or manually via a slash command. (See Anthropic’s docs and examples.)  
- Claude Code skills overview: https://code.claude.com/docs/en/skills  
- Anthropic skills repo/examples: https://github.com/anthropics/skills  

### What a skill is (in this framework)
A **skill** is:
- a small folder under `.agent/skills/<skill-name>/`
- a `SKILL.md` with YAML frontmatter + markdown instructions
- optional supporting reference files (checklists, templates, examples)

**Important MVP rule:** skills are **instruction/resource-only** (no executable scripts). This keeps the surface area safer and easier to trust.

### Directory layout (example)
```
.agent/
  skills/
    review/
      SKILL.md
      checklist.md
    triage/
      SKILL.md
      rubric.md
```

### `SKILL.md` format
We use a simple convention:

```md
---
name: review
description: Perform a repo-aware code review using citations
invoke: manual        # manual | auto
triggers:
  - "review"
  - "code review"
  - "PR review"
tools:
  - rg_search
  - open_snippet
  - git_blame
---

# Review skill

## Goal
Perform a code review that cites files/lines and identifies risks.

## Steps
1) Find the touched files (use `rg_search` if needed).
2) Open relevant snippets with `open_snippet`.
3) Use `git_blame` on suspicious lines to understand intent.
4) Summarize issues by severity and suggest next steps.
```

Recommended frontmatter keys:
- `name` (string): skill id
- `description` (string): one-liner
- `invoke` (`manual|auto`): whether the agent may load it opportunistically
- `triggers` (list[string]): phrases that suggest relevance
- `tools` (list[string]): tools the skill expects to use
- `domain` (optional string): future use (language/library packs)

### How skills are used
- **Manual:** user runs `sca /review` or `sca skill run review`
- **Auto:** agent selects a skill when the user query matches a trigger and the skill is marked `invoke: auto`

To keep behavior predictable, auto-selection should be conservative:
- prefer manual unless users opt in
- only auto-load when trigger match is strong
- always show “using skill: <name>” in the trace/debug output

### Security note
Skills can steer behavior significantly; treat third-party skills as untrusted. Anthropic notes that skills can introduce security risks if they include code or malicious instructions
- https://www.anthropic.com/engineering/equipping-agents-for-the-real-world-with-agent-skills  

---

## How it works (high level)

1. Load repo context (`AGENT.md`)
2. (Optional) Load a skill (manual or auto) to guide the workflow
3. Use tools to gather facts:
   - search candidates (`rg_search`, `list_files`)
   - retrieve proof (`open_snippet`)
   - validate with history (`git_log`, `git_blame`, `git_show`)
4. Answer with citations (paths + line ranges; commit IDs when relevant)

---

## CLI (planned)

- `sca chat`  
  Interactive session scoped to the repo (tool-first).
- `sca explain <path>`  
  Explain a file using snippets and citations.
- `sca find "<question or concept>"`  
  Search + cite where it exists in the repo.
- `sca history <path> [--grep "..."]`  
  Summarize relevant commits, show blame highlights.
- `sca skill list`  
  List available skills in `.agent/skills`.
- `sca /<skill>`  
  Shortcut to run a skill (e.g. `/review`).

*(MVP may start with just `chat`, `explain`, `skill list`, and `/skill` invocation.)*

---

## Quickstart (target workflow)

### 0) Prereqs
- Python **3.12.x**
- Git
- Ripgrep (`rg`)
- LM Studio running a local model server (OpenAI-compatible endpoint)

Optional:
- `uv`

### 1) Start LM Studio server
Start the local server in LM Studio (OpenAI-compatible endpoint). Configure the base URL via env var below.

### 2) Install and run (recommended: `uv`)
```bash
# from this repo
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# run inside a target repo
sca chat
```

### 2b) Install and run (fallback: `venv` + `pip`)
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

sca chat
```

### 3) Configure environment
```bash
export OPENAI_BASE_URL="http://localhost:1234/v1"
export OPENAI_API_KEY="not-needed"   # placeholder for OpenAI-compatible clients
export MODEL_NAME="your-lm-studio-model-id"
```

---

## Safety / constraints

- **Read-only by default**
- **Repo-root sandboxing** for all file operations
- **Allowlisted git operations** only
- Answers should be anchored to:
  - snippets (file + line range)
  - git evidence (commit/blame/log)

---

## Roadmap (later)
- Pluggable analyzers (tree-sitter, AST, doc extraction)

---

## Non-goals (for MVP)
- Editing files / applying diffs
- Running build/test commands automatically
- Multi-agent orchestration
- Executable skill scripts
