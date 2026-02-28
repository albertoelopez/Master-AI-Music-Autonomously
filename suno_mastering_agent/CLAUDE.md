# Suno AI Studio Automation Agent

Playwright-based browser automation for creating, mastering (EQ/mixing), and exporting music on Suno.com. Uses a skills-based architecture where atomic browser actions (skills) are composed into higher-level workflows (agents). Now includes an LLM-driven AI agent mode using Browser Use + LangGraph.

## Project Structure

```
suno_mastering_agent/
  main.py                  # Click CLI entry point (login, master, create, batch, export, profiles, interactive, agent)
  agent.py                 # AI Agent entry point (CLI REPL, Gradio web UI, one-shot tasks)
  requirements.txt         # All dependencies (core + AI agent)
  src/
    browser.py             # BrowserController - Playwright Chromium with CDP port support + persistent profile
    skills/
      __init__.py          # Re-exports all skill classes
      base.py              # Skill base class, SkillResult dataclass, loads CONTROLS from suno_controls.json
      navigate.py          # NavigateSkill: to_studio, to_create, to_library, to_song, is_logged_in
      modal.py             # ModalSkill: dismiss_all (Escape + close buttons + z-index hiding), check_blocking
      studio.py            # StudioSkill: select_clip, switch_to_track_tab/clip_tab, export, extract_stems, get_track_count
      eq.py                # EQSkill: enable/disable, set_preset, select_band, set_band, set_filter_type, apply_custom_eq, get_current_state
      mixing.py            # MixingSkill: set_volume, set_pan, solo, mute, get_track_info
      create.py            # CreateSkill: set_lyrics, set_styles, set_title, set_weirdness, create_song (Custom mode)
    agents/
      __init__.py          # Re-exports MasteringAgent, BatchCreateAgent
      mastering.py         # MasteringAgent: master_track, master_all_tracks, master_and_export; defines MASTERING_PROFILES
      batch_create.py      # BatchCreateAgent: create_song, create_batch; defines SongSpec dataclass
    agent/
      __init__.py          # Re-exports: resolve_llm, SunoBrowserAgent, workflows
      llm_config.py        # Multi-provider LLM resolver (DeepSeek, Ollama, OpenAI, Anthropic) + YAML config
      tools.py             # Async LangChain @tool wrappers for all skills (13 tools)
      browser_use_agent.py # Browser Use integration with custom Suno actions via @controller.action
      workflows.py         # LangGraph StateGraphs: mastering_workflow, batch_workflow, interactive (ReAct)
    ui/
      __init__.py
      gradio_app.py        # Gradio web UI with Create/Master/Export/Agent Chat/Monitor tabs
  config/
    settings.py            # SunoConfig (pydantic), SUNO_EQ_PRESETS list, DEFAULT_CONFIG
    agent_config.yaml      # LLM provider/model, browser CDP settings, autonomy levels, UI config
    suno_controls.json     # Complete UI control map with pixel positions, API endpoints, page URLs
  browser_data/            # Persistent Chromium profile directory (login cookies survive restarts)
```

## Architecture

**Skills** are atomic, repeatable browser actions. Each skill class extends `Skill` (from `base.py`) which provides:
- `click_at(x, y)` - Click at exact pixel coordinates
- `click_button(text)` - Find and click a button by visible text (with optional region constraint)
- `drag(from_x, from_y, to_x, to_y)` - Smooth multi-step drag
- `set_input_value(x, y, value)` - Triple-click to select, then type a value
- `get_right_panel_text()` - Read text from the right 30% of the viewport
- `screenshot(name)` - Save a screenshot to `/tmp/suno_skills/`
- `self.controls` - The loaded `suno_controls.json` control map

All skills return `SkillResult(success: bool, message: str, data: Any)`.

**Agents** compose multiple skills into multi-step workflows. They handle initialization (browser connect, login check, navigation) and produce summary tables via Rich.

**BrowserController** (`src/browser.py`) wraps Playwright's `launch_persistent_context` at 1280x900 viewport. The persistent profile in `browser_data/` keeps login cookies between sessions.

**Control Map** (`config/suno_controls.json`) contains all pixel positions, API endpoints, and page URLs. Skills read positions from this file at import time via the `CONTROLS` global in `base.py`.

## CLI Commands

```bash
python main.py login                                    # Open browser, sign into Suno manually, session is saved
python main.py master --all --profile radio_ready       # Master all tracks with a profile
python main.py master --track 1 --profile warm_vinyl    # Master a specific track (1-based)
python main.py master --all --profile bass_heavy --export  # Master all tracks then export
python main.py create -l "lyrics here" -s "indie pop, acoustic" -t "My Song"
python main.py batch songs.json --wait 90               # Batch create from JSON array of SongSpec objects
python main.py export --type full|selected|multitrack|stems  # Export current studio project
python main.py profiles                                  # List available mastering profiles
python main.py interactive                               # Interactive REPL with all skills
```

## Mastering Profiles

Defined in `src/agents/mastering.py` as `MASTERING_PROFILES` dict. Each profile specifies a Suno built-in EQ preset plus optional per-band tweaks:

| Profile | Description | EQ Preset | Custom Bands |
|---------|-------------|-----------|-------------|
| radio_ready | Bright, punchy for streaming/radio | Presence | B1, B4, B5 |
| warm_vinyl | Warm analog with rolled-off highs | Warm | B2, B5, B6 |
| bass_heavy | Deep bass for hip-hop/EDM/trap | Bass Boost | B1, B2, B6 |
| vocal_focus | Clear vocals, reduced mud | Vocal | B2, B3, B4 |
| bright_pop | Sparkly high-end for pop/dance | Air | B5, B6 |
| lo_fi | Muffled, warm lo-fi aesthetic | Lo-fi | none |
| clarity | Maximum clarity and definition | Clarity | B2, B4 |
| flat | Reset to neutral EQ | Flat (Reset) | none |

## Suno Built-in EQ Presets

Available in the Studio EQ preset selector (cycled with prev/next arrows):
Flat (Reset), Hi-Pass, Vocal, Warm, Bright, Presence, Bass Boost, Air, Clarity, Fullness, Lo-Fi, Modern

## EQ Details

6-band parametric EQ. Each band has: frequency, gain (dB), Q/resonance, and filter type.
Filter types: Bell/Peak, High-pass, Low-pass, High-shelf, Low-shelf, Notch.
Band defaults (Flat): B1=60Hz HP, B2=200Hz Bell, B3=450Hz Bell, B4=2kHz Bell, B5=6kHz Bell, B6=8.8kHz LP.
Pixel positions for all EQ controls are hardcoded in `src/skills/eq.py` (`EQ_POSITIONS` dict).

## Batch JSON Format

```json
[
  {"lyrics": "Verse 1...", "styles": "indie pop, acoustic", "title": "Song Name", "weirdness": 50, "style_influence": 70},
  {"lyrics": "Another song...", "styles": "lo-fi hip hop"}
]
```

Fields `title`, `weirdness`, and `style_influence` are optional.

## Setup

```bash
pip install -r requirements.txt
playwright install chromium
python main.py login        # One-time: sign into Suno in the browser window, then press Enter
```

## Critical Operational Notes

- **Login required first**: Run `python main.py login` before any other command. The persistent Chromium profile in `browser_data/` stores session cookies.
- **SingletonLock cleanup**: If the browser crashes, `browser_data/SingletonLock` must be removed before the next run. `main.py` does this automatically on startup.
- **Modal overlays block clicks**: After navigating to Studio, always call `ModalSkill.dismiss_all()` before interacting with controls. Agents handle this internally.
- **EQ requires clip selection + Track tab**: To manipulate EQ, a clip must be selected on the timeline and the right panel must be on the Track tab (not Clip tab). The mastering agent handles this sequence: `select_clip` -> `dismiss_all` -> `switch_to_track_tab` -> `enable` -> `set_preset` -> `set_band`.
- **Viewport is fixed at 1280x900**: All pixel positions in `suno_controls.json` and `eq.py` assume this viewport size. Do not change the viewport dimensions.
- **Track indices**: CLI uses 1-based (`--track 1`), internal code uses 0-based. `main.py` converts with `track - 1`.
- **Batch creation wait times**: Songs take time to generate on Suno's servers. Default wait between batch songs is 60 seconds (`--wait` flag).
- **No headless mode for login**: `BrowserController` runs headed by default (`headless=False`) so the user can see and interact with the browser.
- **Create page modals**: Suno's Create page triggers chakra-portal modals (Personas, etc.) that block clicks. `CreateSkill` dismisses these between steps. The Styles field is a `textarea` (not input); "Exclude styles" is a separate input that must not be confused with it.
- **Song Title position**: In Custom mode, Song Title input appears at two y-positions; the correct one is the lower one (y≈732). The upper duplicate (y≈112) overlaps the Persona button area.
- **Export options**: Studio Export dropdown has 3 options: Full Song, Selected Time Range, Multitrack.

## Development Notes

- All async: skills and agents use `async/await`. CLI commands wrap with `asyncio.run()`.
- Skills never call other skills directly; agents orchestrate skill composition.
- `SkillResult.data` carries typed payloads (dicts, lists, ints) for programmatic consumption.
- The `click_button(text, region)` method in `base.py` finds buttons by exact `textContent` match and bounding box, which is fragile if Suno changes button labels.
- EQ preset cycling (`set_preset`) resets to Flat first (up to 12 prev-arrow clicks), then clicks next-arrow to reach the target preset by index.
- The `suno_controls.json` file also documents all known Suno API endpoints (under `"api"` key), though the current implementation uses browser automation rather than direct API calls.
