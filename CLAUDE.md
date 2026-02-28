# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Suno AI Studio Automation Agent — a Python tool that automates music creation, EQ mastering, mixing, and export on Suno AI (suno.com) via browser automation. It has two modes:

1. **Skills-based CLI** (`main.py`) — Deterministic Playwright skills for precise pixel-coordinate automation
2. **AI Agent** (`agent.py`) — LLM-driven agent using Browser Use + LangGraph for intelligent, autonomous control

**Prerequisite:** The tool launches its own Chromium with `--remote-debugging-port=9222`. User must be logged into suno.com (run `python main.py login` first).

## Commands

```bash
# Setup
cd suno_mastering_agent
pip install -r requirements.txt
playwright install chromium

# Skills-based CLI (deterministic)
python main.py login                                    # One-time login
python main.py master --all --profile radio_ready       # Master all tracks
python main.py create -l "lyrics" -s "indie pop"        # Create song
python main.py batch songs.json                         # Batch create
python main.py export --type full                       # Export project
python main.py profiles                                 # List profiles
python main.py interactive                              # Interactive REPL

# AI Agent (LLM-driven)
python agent.py                                         # Interactive CLI REPL
python agent.py --provider ollama --model llama3.3      # Use local Ollama
python agent.py --provider deepseek                     # Use DeepSeek (default)
python agent.py --ui gradio                             # Web UI at localhost:7860
python agent.py --task "Master all tracks and export"   # One-shot task
python main.py agent                                    # Via main.py wrapper
```

No test suite or linter is configured.

## Architecture

All source lives under `suno_mastering_agent/`. Three-layer design:

### Layer 1: Skills (deterministic browser actions)
- **BrowserController** (`src/browser.py`) — Playwright CDP connection, page actions, CDP port support
- **Skills** (`src/skills/`) — Atomic actions: NavigateSkill, ModalSkill, StudioSkill, EQSkill, MixingSkill, CreateSkill
- **Agents** (`src/agents/`) — Workflow composers: MasteringAgent (8 profiles), BatchCreateAgent

### Layer 2: Browser Use (intelligent navigation)
- **SunoBrowserAgent** (`src/agent/browser_use_agent.py`) — Browser Use with custom Suno actions registered via `@controller.action`
- Connects to same Chrome via CDP as Layer 1 skills

### Layer 3: LangGraph (orchestration + planning)
- **Tools** (`src/agent/tools.py`) — Async LangChain `@tool` wrappers around Layer 1 skills
- **Workflows** (`src/agent/workflows.py`) — LangGraph StateGraphs: mastering_workflow, batch_workflow, interactive_workflow (ReAct)
- **LLM Config** (`src/agent/llm_config.py`) — Multi-provider resolver: DeepSeek, Ollama, OpenAI, Anthropic

### Entry Points
- **CLI** (`main.py`) — Click commands for skills-based automation
- **Agent** (`agent.py`) — Click command for LLM-driven agent (CLI REPL, Gradio, one-shot)
- **Web UI** (`src/ui/gradio_app.py`) — Gradio interface with Create/Master/Export/Chat/Monitor tabs

### Config
- `config/settings.py` — Pydantic SunoConfig, EQ presets
- `config/agent_config.yaml` — LLM provider, browser, autonomy levels, UI settings
- `config/suno_controls.json` — Complete UI control map with pixel positions

## Key Patterns

- **Fully async**: all browser/workflow/tool code uses `async/await`. CLI uses `asyncio.run()` at boundary.
- **Async tools**: LangChain tools are `async def` to avoid event loop conflicts with Playwright.
- **CDP sharing**: BrowserController supports `cdp_port` param; Browser Use connects to same Chrome via CDP.
- **Skills are atomic**: Skills never call other skills; agents/workflows compose them.
- **Pixel-coordinate precision**: EQ bands, faders, buttons use hardcoded positions (1280x900 viewport).
- **Rich console**: all CLI output uses Rich tables, spinners, and panels.
- **YAML config**: `config/agent_config.yaml` for LLM provider, model, autonomy levels.

## Dependencies

Core: playwright, pydantic, rich, click, python-dotenv
AI Agent: browser-use, langchain-core, langgraph, langchain-deepseek, langchain-ollama, gradio, pyyaml
Optional: langchain-openai, langchain-anthropic

Requires Python >=3.9. Pinned in `suno_mastering_agent/requirements.txt`.
