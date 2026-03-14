# MAGI

MAGI is a lightweight advisory orchestrator for local CLI subscriptions such as Codex, Claude Code, and Gemini CLI.

Instead of pushing multiple models into a free-form conversation, MAGI asks them the same question independently, stores their responses, and produces a synthesis report that highlights:

- agreement
- differences
- open questions
- recommended next steps

The current version is a local CLI-first MVP with a built-in `mock` mode for immediate testing.

## Why MAGI

Many multi-agent tools focus on autonomous execution. MAGI is designed for structured comparison and decision support.

This makes it useful for:

- software design reviews
- implementation planning
- debugging strategy
- research or writing workflows
- comparing alternative approaches before committing to execution

## Features

- interactive shell with persistent modes
- arrow-key command history via `prompt_toolkit`
- one-shot CLI execution
- provider abstraction for external CLIs
- file-based run history
- saved advisor outputs and synthesis reports
- mode switching with slash commands
- provider, model, and effort switching from `/model`
- model catalog refresh via `magi models` or `/models`
- run cleanup with `/clean` or `magi clean`
- quota/status placeholders for each provider

## Quick Start

Run directly from this folder:

```powershell
python -m magi "Compare three implementation approaches for a small internal tool."
```

Or install the command locally:

```powershell
python -m pip install -e .
magi "Review the initial architecture for this project."
```

By default, MAGI uses mock providers named `codex`, `claude`, and `gemini`, and writes artifacts to `runs/`.

## Interactive Mode

Start the shell:

```powershell
python -m magi
```

If `prompt_toolkit` is available and you are in a real terminal, MAGI uses command history and line editing similar to other modern CLIs.

MAGI keeps the current mode until you switch it.

```text
MAGI [ask]> /plan
mode: plan
MAGI [plan]> Break this project into an MVP and a second phase.
MAGI [plan]> /model
MAGI model menu
Enter: descend/select | Esc: back/exit | Space: toggle provider on/off
MAGI [plan]> /clean 20
MAGI [plan]> /debug
MAGI [debug]> Investigate why provider output is failing to parse.
MAGI [debug]> /exit
```

Available slash commands:

- `/ask`
- `/plan`
- `/debug`
- `/agent`
- `/model`
- `/models`
- `/clean`
- `/mode`
- `/status`
- `/runs`
- `/last`
- `/help`
- `/exit`

The shell currently shows quota placeholders such as `codex: --%` until provider-specific usage parsing is implemented.

## `/model` Menu

Run `/model` with no arguments to open the keyboard-driven selector.

The first `/model` in an interactive MAGI session also forces a model catalog refresh before opening the menu, so recently added subscription models can show up without a manual `magi models refresh`.

Controls:

- `Enter`: go down one level or confirm the current selection
- `Esc`: go up one level or leave the menu
- `Space`: on the provider list, cycle provider role: `[×] off` -> `[•] advisor` -> `[○] synthesizer`
- Arrow keys: move the cursor

Provider roles:

- `[×]`: disabled
- `[•]`: active advisor
- `[○]`: active advisor and final synthesizer

Only one provider can be `[○]` at a time.
If `[○]` is already assigned, other providers cycle between `[×]` and `[•]` until the synthesizer slot is freed.

Hierarchy:

1. provider selection
2. model selection for the focused provider
3. effort selection for the focused provider

You can also use text commands when that is faster:

```text
MAGI [ask]> /model codex gpt-5.4 high
MAGI [ask]> /model gemini gemini-3.1-pro-preview medium
MAGI [ask]> /model all
MAGI [ask]> /model show
```

## Cleaning Runs

Runs accumulate under `runs/`. Use `clean` to remove older history.

```powershell
magi clean 20
magi clean all
```

Inside the shell:

```text
/clean 20
/clean all
```

## Model Catalog Refresh

Static model lists go stale. MAGI can refresh provider model catalogs from a local discovery command and cache the results under `.magi-cache/model_catalogs.json`.

Requirements:

- `model_discovery_command` must print one model ID per line
- `model_discovery_regex` is optional and can extract model IDs from noisy output
- `model_discovery_ttl_hours` controls when startup auto-refresh should run again

Example:

```toml
[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec", "--model", "{model}", "{prompt}"]
model_discovery_command = ["python", "scripts/list_codex_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
default_model = "gpt-5.4"
default_effort = "high"
```

Bundled discovery helpers:

- `scripts/list_codex_models.py`
- `scripts/list_claude_models.py`
- `scripts/list_gemini_models.py`

`claude` discovery inspects the installed official Claude Code bundle. `gemini` discovery reads the installed Gemini CLI core model constants. `codex` currently uses a curated fallback because Codex CLI does not expose a public model-list command.

Useful commands:

```powershell
magi models
magi models refresh
magi models refresh codex
```

Inside the shell:

```text
/models
/models refresh
/models refresh claude
```

## One-shot Mode

You can still run a single request without opening the shell:

```powershell
python -m magi --mode plan --providers codex --models codex=gpt-5.4 --efforts codex=high "Outline the delivery phases for this CLI tool."
python -m magi --synth-provider gemini "Compare three implementation approaches for a small internal tool."
```

## Project Structure

```text
magi/
  cli.py
  config.py
  io.py
  model_catalog.py
  model_menu.py
  models.py
  pipeline.py
  prompts.py
  runs.py
  synthesis.py
  prompts/
    advisor.md
    plan.md
    debug.md
    agent.md
  providers/
    base.py
    external_cli.py
    mock.py
runs/
.magi-cache/
```

## Local Config

Create `.magi.toml` in any project directory to override the defaults for that project.

```toml
project_name = "my-project"
runs_dir = "runs"

[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec", "{prompt}"]
model_discovery_command = ["python", "scripts/list_codex_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
# model_discovery_regex = "(gpt-[A-Za-z0-9.-]+)"
default_model = "gpt-5.4"
model_options = ["gpt-5.4", "gpt-5.3-codex", "gpt-5.2-codex", "gpt-5.2", "gpt-5.1-codex-max", "gpt-5.1-codex-mini"]
default_effort = "high"
effort_options = ["default", "low", "medium", "high", "xhigh"]

[providers.claude]
type = "cli"
enabled = true
command = ["claude", "-p", "--model", "{model}", "--effort", "{effort}", "{prompt}"]
model_discovery_command = ["python", "scripts/list_claude_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
default_model = "claude-sonnet-4-6"
model_options = ["claude-sonnet-4-6", "claude-opus-4-6", "claude-haiku-4-5", "claude-sonnet-4-5", "claude-opus-4-1"]
default_effort = "default"
effort_options = ["default", "low", "medium", "high"]

[providers.gemini]
type = "cli"
enabled = true
command = ["gemini", "-m", "{model}", "-p", "{prompt}"]
model_discovery_command = ["python", "scripts/list_gemini_models.py"]
model_discovery_ttl_hours = 24
model_discovery_timeout_seconds = 15
default_model = "gemini-3.1-pro-preview"
model_options = ["gemini-3.1-pro-preview", "gemini-3-flash-preview", "gemini-3-pro-preview", "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite"]
default_effort = "default"
effort_options = ["default", "low", "medium", "high"]
```

Adjust each command to match the CLI syntax installed on your machine. MAGI only assumes that a provider can accept a prompt and return a response on stdout.

`default_model`, `model_options`, `default_effort`, and `effort_options` are only UI/config values until the command template actually uses `{model}` and `{effort}`. If the command omits those placeholders, `/model` changes will not be passed through to the external CLI.

If your CLI reads from standard input, use:

```toml
[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec"]
stdin_prompt = true
default_model = "gpt-5.4"
default_effort = "high"
```

If your CLI supports model and effort flags, include `{model}` and `{effort}` in the command template:

```toml
[providers.codex]
type = "cli"
enabled = true
command = ["codex", "exec", "--model", "{model}", "--reasoning-effort", "{effort}", "{prompt}"]
default_model = "gpt-5.4"
default_effort = "high"
```

## Commands

Ask for advice:

```powershell
magi "Compare design options for this workflow."
```

List saved runs:

```powershell
magi runs
```

Show the latest report path:

```powershell
magi last
```

Clean old runs:

```powershell
magi clean 20
```

## Current Scope

Implemented in this MVP:

- CLI entrypoint
- interactive shell with persistent modes
- prompt_toolkit-backed history when a real console is available
- provider abstraction
- mock provider mode
- external CLI provider adapter
- file-based run persistence
- basic agreement/difference synthesis
- runtime provider, model, and effort selection
- run cleanup commands

Not yet implemented:

- iterative follow-up or re-ask loop
- worker orchestration
- real provider quota parsing
- local LLM or SLM providers
- GUI

## Japanese README

For a Japanese overview, see [README.ja.md](README.ja.md).

## License

MIT. See [LICENSE](LICENSE).
