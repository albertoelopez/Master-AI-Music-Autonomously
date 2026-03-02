# Repository Guidelines

## Project Structure & Module Organization
Core code lives in `suno_mastering_agent/`.
- `main.py`: Click-based CLI for deterministic automation (`login`, `master`, `create`, `batch`, `export`, `profiles`, `agent`)
- `agent.py`: LLM-driven agent entry point (CLI REPL, one-shot task, Gradio mode)
- `src/skills/`: atomic browser actions (navigate, modal handling, EQ, mixing, create, studio)
- `src/agents/`: composed workflows (`MasteringAgent`, `BatchCreateAgent`)
- `src/agent/`: LangGraph and tool wrappers for autonomous execution
- `src/ui/`: Gradio interface
- `config/`: runtime settings and coordinate/control maps
- `_exploration/`: ad-hoc experiments and exploratory scripts

## Build, Test, and Development Commands
Run from `suno_mastering_agent/`:
- `python3 -m venv venv && source venv/bin/activate`: create/activate local environment
- `pip install -r requirements.txt`: install dependencies
- `playwright install chromium`: install browser runtime
- `python main.py login`: one-time Suno login (required before automation)
- `python main.py master --all --profile radio_ready`: deterministic mastering flow
- `python agent.py --ui gradio`: launch web UI (`localhost:7860`)
- `./run.sh`: bootstrap venv (if missing) and launch `main.py`

## Coding Style & Naming Conventions
- Python 3.9+ with 4-space indentation and type-aware, readable async code.
- Use `snake_case` for functions/variables, `PascalCase` for classes, and concise verb-first method names (`create_song`, `master_track`).
- Keep skills atomic; compose behavior in agents/workflows instead of cross-calling skills.
- Prefer explicit `SkillResult` messages and structured `data` payloads.

## Testing Guidelines
There is no formal pytest suite configured yet. Current validation is script-based:
- `python test_mastering_live.py`
- exploratory checks in `_exploration/test_*.py`

For new features, add a focused script test near the relevant module and capture observable outcomes (console summary, screenshot, or exported artifact path).

## Commit & Pull Request Guidelines
Git history uses short, imperative, sentence-style commit messages (example: `Fix bugs and improve reliability for initial testing`).
- Keep commits scoped to one logical change.
- PRs should include:
  - purpose and behavior change summary
  - commands executed to validate
  - config changes (`config/*.yaml`, `suno_controls.json`) called out explicitly
  - screenshots/log snippets when UI automation behavior changes

## Security & Configuration Tips
- Keep secrets in environment variables (`python-dotenv` is available); do not commit keys.
- Treat `browser_data/` as local runtime state.
- Re-check coordinate maps after Suno UI updates before merging automation changes.
