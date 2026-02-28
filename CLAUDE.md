# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Suno Mastering Agent — a Python CLI tool that automates audio mastering on Suno AI (suno.com) via browser automation. It connects to a running Chrome instance over CDP (Chrome DevTools Protocol) using Playwright, navigates Suno's web UI, and applies mastering presets to tracks.

**Prerequisite:** Chrome must be running with `--remote-debugging-port=9222` and the user must be logged into suno.com before running any commands.

## Commands

```bash
# Full setup (venv, deps, playwright browsers) and run:
./suno_mastering_agent/run.sh [args]

# Run directly (after setup):
cd suno_mastering_agent
python main.py --port 9222 list
python main.py master --all --preset loud
python main.py explore
python main.py interactive
python main.py screenshot
```

No test suite or linter is configured.

## Architecture

All source lives under `suno_mastering_agent/`. Layered design, bottom-up:

1. **BrowserController** (`src/browser.py`) — Playwright async CDP connection, low-level page actions (click, type, wait, screenshot, JS eval).
2. **SunoInterface** (`src/suno_interface.py`) — Domain abstraction over Suno's web UI. Maintains CSS selectors (`SunoSelectors` class with fallback selectors), exposes track listing, mastering panel control, and download. Defines `Track` dataclass.
3. **MasteringWorkflow** (`src/mastering.py`) — Orchestrates mastering operations across multiple tracks. Defines `MasteringResult` dataclass. Uses Rich for terminal output.
4. **CLI** (`main.py`) — Click command group (`cli`) with subcommands: `list`, `master`, `explore`, `interactive`, `screenshot`.
5. **Config** (`config/settings.py`) — Pydantic models `SunoConfig` and `MasteringPreset`. Built-in presets: default, loud, warm, bright.

## Key Patterns

- **Fully async**: all browser/workflow code uses `async/await` with `asyncio.run()` at the CLI boundary.
- **CSS selector resilience**: `SunoSelectors` stores multiple fallback selectors per UI element since Suno's DOM can change.
- **Rich console**: all user-facing output uses Rich tables, spinners, and panels.
- **Pydantic config**: type-safe settings with defaults (chrome debug port 9222, timeout 30s).

## Dependencies

playwright, pydantic, rich, click, python-dotenv — pinned in `suno_mastering_agent/requirements.txt`. Requires Python >=3.9.
