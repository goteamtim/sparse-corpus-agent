# Sparse Corpus Agent Framework

A local-first, evidence-first CLI agent framework for working inside any folder or workspace. It is designed to be the starting point for building language-specific agents for programming languages that have sparse public corpora.

This repo is intentionally language-agnostic: it includes no language-specific rules, examples, or tooling. Downstream implementers add whatever is needed for their language in their own agent fork or package.

This repo provides a generic framework with a minimal toolset and a lightweight "skills" system for repeatable workflows.

---

### Environment + dependency management
- Recommended: `uv`
- Supported fallback: `python -m venv` + `pip`
---

## Core ideas

### Evidence-first answers
The agent should not "guess." If it claims something about the workspace, it should point to file paths + line ranges (snippets).

### Local-first runtime
Designed to run with a local LLM server (e.g. LM Studio) and a lightweight agent runtime (e.g. PydanticAI). The framework intentionally avoids requiring a hosted model however that is also supported.

### Human workspace context (AGENT.md)
A human-authored workspace guide provides the "meaning" that auto-discovery cannot:
- what the workspace/project is
- what folders matter
- conventions/glossary
- entrypoints
- what not to touch

The agent automatically loads this file (and optionally `.agent/*.md`) as the first context for every run.

---

## MVP scope: tools

### Workspace-scoped primitives
1. `read_workspace_prompt()`
   - Loads `AGENT.md` (and optional `.agent/*.md`) from workspace root.
2. `list_files(globs, ignore, max_files, include_hidden=False)`
   - Returns a structured list of paths and basic metadata.
3. `open_snippet(path, start_line, end_line)`
   - Returns a line-ranged snippet for citations.
4. `rg_search(query, globs, ignore, max_results, context_lines)`
   - Ripgrep-style search with structured match results.
5. `file_stats(path)`
   - Size, line count, binary detection, hash (for "don't open huge/minified/binary" decisions).
6. `get_outline(path, max_depth=2)`
   - Tree-sitter code outline extraction. Returns structural symbols (functions, classes, methods, etc.) with line ranges.
   - Requires a user-provided compiled grammar (`.so`/`.dll`/`.dylib`).
   - Uses a 3-tier fall-through resolution strategy:
     1. **Custom query:** `.agent/queries/{lang}/outline.scm` — full surgical control using tree-sitter query patterns (follows `tags.scm` conventions: `@name` + `@definition.*` captures).
     2. **Registry:** `.agent/grammar.yaml` with an `outline_node_types` list.
     3. **Universal defaults:** Hardcoded common node types (`function_definition`, `class_definition`, etc.).

> Note: all tools are workspace-scoped and sandboxed. No reading outside the workspace root. No arbitrary shell execution.

---

## Skills (lightweight, sharable workflow prompts)

Niche codebases often require "hand holding" to keep the model on the rails. This project supports skills: small, portable instruction packs that guide a workflow. The concept is inspired by other agent systems (e.g., Anthropic/Claude agent skills), but the implementation here stays minimal and language-agnostic.

- Agent skills overview: https://agentskills.io/specification

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
description: Perform a workspace-aware code review using citations
invoke: manual        # manual | auto
triggers:
  - "review"
  - "code review"
  - "PR review"
tools:
  - rg_search
  - open_snippet
---

# Review skill

## Goal
Perform a code review that cites files/lines and identifies risks.

## Steps
1) Find the touched files (use `rg_search` if needed).
2) Open relevant snippets with `open_snippet`.
3) Summarize issues by severity and suggest next steps.
```

Recommended frontmatter keys:
- `name` (string): skill id
- `description` (string): one-liner
- `invoke` (`manual|auto`): whether the agent may load it opportunistically
- `triggers` (list[string]): phrases that suggest relevance
- `tools` (list[string]): tools the skill expects to use
- `domain` (optional string): future use (language/library packs)

### How skills are used
- Manual: user runs `sca /review` or `sca skill run review`
- Auto: agent selects a skill when the user query matches a trigger and the skill is marked `invoke: auto`

To keep behavior predictable, auto-selection should be conservative:
- prefer manual unless users opt in
- only auto-load when trigger match is strong
- always show "using skill: <name>" in the trace/debug output


---

## How it works (high level)

1. Load workspace context (`AGENT.md`)
2. (Optional) Load a skill (manual or auto) to guide the workflow
3. Use tools to gather facts:
   - search candidates (`rg_search`, `list_files`)
   - retrieve proof (`open_snippet`)
4. Answer with citations (paths + line ranges)

---

## CLI (planned)

- `sca chat`
  Interactive session scoped to the workspace (tool-first).
- `sca explain <path>`
  Explain a file using snippets and citations.
- `sca find "<question or concept>"`
  Search + cite where it exists in the workspace.
- `sca skill list`
  List available skills in `.agent/skills`.
- `sca /<skill>`
  Shortcut to run a skill (e.g. `/review`).

*(MVP may start with just `chat`, `explain`, `skill list`, and `/skill` invocation.)*

---

## Quickstart (target workflow)

### 0) Prereqs
- Python 3.12+
- Ripgrep (`rg`) — install via `winget install BurntSushi.ripgrep.MSVC` (Windows), `brew install ripgrep` (macOS), or `apt install ripgrep` (Debian/Ubuntu)
- LM Studio running a local model server (OpenAI-compatible endpoint)

Optional:
- `uv`
- A compiled Tree-sitter grammar for your language (see "Tree-sitter grammar setup" below)

### 1) Start LM Studio server
Start the local server in LM Studio (OpenAI-compatible endpoint). Configure the base URL via env var below.

### 2) Install and run (recommended: `uv`)
```bash
# from this repo
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt

# run inside any target workspace or folder
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

### Repo resolution

You can run `sca` from anywhere — it doesn't need to be invoked from inside the target repo. The workspace root is resolved using the following precedence (first match wins):

| Priority | Source | Example |
|----------|--------|---------|
| 1 | `--repo` CLI flag | `sca chat --repo /path/to/repo` |
| 2 | `SCA_REPO` env var | `SCA_REPO=/path/to/repo sca chat` |
| 3 | `SCA_WORKSPACE_ROOT` env var (legacy) | `SCA_WORKSPACE_ROOT=/path/to/repo sca chat` |
| 4 | Auto-detect | Walk upward from cwd looking for `.git` or `AGENT.md` |

If none of these resolve to a valid directory, `sca` exits with an error.

```bash
# From anywhere on your system:
sca chat --repo ~/projects/my-lang-project

# Or set once for the shell session:
export SCA_REPO=~/projects/my-lang-project
sca chat
sca explain src/parser.py
```

### 4) Tree-sitter grammar setup (optional)

The framework ships with no bundled grammars — you provide your own. This is intentional: the framework targets niche languages that don't have pre-packaged tree-sitter bindings.

**Build a grammar:**
```bash
cd tree-sitter-mylang/
tree-sitter generate       # generates src/parser.c from grammar.js
tree-sitter build -o mylang.so   # compiles to shared library (.so / .dll / .dylib)
```

**Configure the three env vars:**
```bash
export SCA_GRAMMAR_PATH="/path/to/mylang.so"      # compiled shared library
export SCA_GRAMMAR_NAME="mylang"                   # language name (matches tree_sitter_<name>() export)
export SCA_GRAMMAR_EXTENSIONS=".ml,.mli"           # file extensions this grammar applies to
```

All three must be set together. When configured, the agent gains a `get_code_outline` tool.

**Customize symbol extraction (optional):**

The tool uses a 3-tier fall-through strategy:

1. **Custom query** — Create `.agent/queries/{grammar_name}/outline.scm` with tree-sitter query patterns following `tags.scm` conventions (`@name` + `@definition.*` captures). This gives you full control over what symbols are extracted.
2. **Registry** — Create `.agent/grammar.yaml` with an `outline_node_types` list:
   ```yaml
   outline_node_types:
     - function_definition
     - class_definition
     - method_definition
   ```
3. **Universal defaults** — If neither of the above exists, a built-in list of common node types is used.

---

## Safety / constraints

- Read-only by default
- Workspace-scoped sandboxing for all file operations
- Answers should be anchored to:
  - snippets (file + line range)

---

## Roadmap (later)
- Additional pluggable analyzers (AST, doc extraction)
- Multi-grammar support (multiple languages per workspace)

---

## Non-goals (for MVP)
- Language-specific rules, examples, or tooling
- Version-control integrations or history tools
- Editing files / applying diffs
- Running build/test commands automatically
- Multi-agent orchestration
- Executable skill scripts
