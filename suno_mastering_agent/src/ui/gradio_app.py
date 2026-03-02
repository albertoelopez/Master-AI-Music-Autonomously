"""Gradio web UI for the Suno AI Agent.

Provides a browser-based interface with tabs for:
  - Create: Song creation with lyrics, styles, and parameters
  - Master: Apply mastering profiles to tracks
  - Export: Export projects in various formats
  - Agent Chat: Natural language interaction with the agent
  - Monitor: Live screenshots and action log
"""
import asyncio
import os
import time
from typing import Optional

import gradio as gr
from langchain_core.language_models.chat_models import BaseChatModel

from ..browser import BrowserController
from ..agents.mastering import MASTERING_PROFILES
from ..skills import (
    NavigateSkill, ModalSkill, StudioSkill,
    EQSkill, MixingSkill, CreateSkill,
)
from ..agent.tools import set_browser
from ..agent.workflows import run_interactive


# Module-level state
_browser: Optional[BrowserController] = None
_llm: Optional[BaseChatModel] = None
_chat_history: Optional[list] = None
_action_log: list[str] = []
_main_loop: Optional[asyncio.AbstractEventLoop] = None


def set_main_loop(loop: asyncio.AbstractEventLoop):
    """Set the main event loop for async operations from Gradio threads."""
    global _main_loop
    _main_loop = loop


def _log(msg: str):
    """Append to the action log."""
    ts = time.strftime("%H:%M:%S")
    _action_log.append(f"[{ts}] {msg}")
    if len(_action_log) > 200:
        _action_log.pop(0)


def _get_log() -> str:
    return "\n".join(_action_log[-50:])


def _run_async(coro):
    """Schedule an async coroutine on the main event loop from sync Gradio callbacks."""
    if _main_loop is None or _main_loop.is_closed():
        raise RuntimeError("Main event loop not available. Restart the agent.")
    future = asyncio.run_coroutine_threadsafe(coro, _main_loop)
    return future.result(timeout=120)


# --- Create tab callbacks ---

def create_song_handler(lyrics, styles, title, weirdness, style_influence):
    """Create a song with the given parameters."""
    global _browser
    if not _browser or not _browser.page:
        return "Browser not connected. Please restart the agent."

    async def _create():
        nav = NavigateSkill(_browser)
        modal = ModalSkill(_browser)
        create = CreateSkill(_browser)

        await nav.to_create()
        await modal.dismiss_all()

        r = await create.create_song(
            lyrics=lyrics,
            styles=styles,
            title=title if title else None,
            weirdness=int(weirdness) if weirdness else None,
            style_influence=int(style_influence) if style_influence else None,
        )
        _log(f"Create: {r.message}")
        return r.message

    try:
        return _run_async(_create())
    except Exception as e:
        return f"Error: {e}"


# --- Master tab callbacks ---

def master_handler(profile, track_num, master_all):
    """Apply mastering to tracks."""
    global _browser
    if not _browser or not _browser.page:
        return "Browser not connected."

    async def _master():
        from ..agents.mastering import MasteringAgent

        nav = NavigateSkill(_browser)
        modal = ModalSkill(_browser)
        await nav.to_studio()
        await modal.dismiss_all()

        agent = MasteringAgent(_browser)

        if master_all:
            results = await agent.master_all_tracks(profile)
            ok = sum(1 for r in results if r.success)
            msg = f"Mastered {ok}/{len(results)} tracks with '{profile}'"
        else:
            idx = int(track_num) - 1 if track_num else 0
            r = await agent.master_track(idx, profile)
            msg = r.message

        _log(f"Master: {msg}")
        return msg

    try:
        return _run_async(_master())
    except Exception as e:
        return f"Error: {e}"


def get_tracks_handler():
    """Get current track info."""
    global _browser
    if not _browser or not _browser.page:
        return "Browser not connected."

    async def _get():
        mixing = MixingSkill(_browser)
        studio = StudioSkill(_browser)
        info = await mixing.get_track_info()
        count = await studio.get_track_count()
        tracks = info.data or []
        lines = [f"Tracks: {count.data or 0}"]
        for i, t in enumerate(tracks, 1):
            lines.append(f"  {i}. {t['name']}")
        return "\n".join(lines)

    try:
        return _run_async(_get())
    except Exception as e:
        return f"Error: {e}"


# --- Export tab callbacks ---

def export_handler(export_type):
    """Export the current project."""
    global _browser
    if not _browser or not _browser.page:
        return "Browser not connected."

    async def _export():
        nav = NavigateSkill(_browser)
        modal = ModalSkill(_browser)
        studio = StudioSkill(_browser)

        await nav.to_studio()
        await modal.dismiss_all()

        if export_type == "Full Song":
            r = await studio.export_full_song()
        elif export_type == "Multitrack":
            r = await studio.export_multitrack()
        else:
            await studio.select_clip(0)
            await modal.dismiss_all()
            r = await studio.extract_stems("all")

        _log(f"Export: {r.message}")
        return r.message

    try:
        return _run_async(_export())
    except Exception as e:
        return f"Error: {e}"


# --- Agent Chat callbacks ---

def chat_handler(message, chat_history):
    """Process a chat message through the ReAct agent."""
    global _browser, _llm, _chat_history
    if chat_history is None:
        chat_history = []

    if not _browser or not _browser.page:
        chat_history.append((message, "Browser not connected. Please restart the agent."))
        return "", chat_history

    try:
        response, _chat_history = _run_async(
            run_interactive(_browser, message, llm=_llm, history=_chat_history)
        )
        _log(f"Chat: {message[:50]}... -> {response[:50]}...")
        chat_history.append((message, response))
        return "", chat_history
    except Exception as e:
        chat_history.append((message, f"Error: {e}"))
        return "", chat_history


# --- Monitor tab callbacks ---

def screenshot_handler():
    """Take and return a screenshot."""
    global _browser
    if not _browser or not _browser.page:
        return None, "Browser not connected."

    async def _screenshot():
        os.makedirs("/tmp/suno_skills", exist_ok=True)
        path = "/tmp/suno_skills/gradio_monitor.png"
        ok = await _browser.screenshot(path)
        return path if ok else None

    try:
        path = _run_async(_screenshot())
        _log("Screenshot taken")
        return path, _get_log()
    except Exception as e:
        return None, f"Error: {e}"


def refresh_log():
    """Refresh the action log."""
    return _get_log()


# --- App builder ---

def create_app(browser: BrowserController, llm: BaseChatModel) -> gr.Blocks:
    """Create the Gradio app."""
    global _browser, _llm
    _browser = browser
    _llm = llm
    set_browser(browser)

    # Capture the current event loop for thread-safe async calls
    try:
        loop = asyncio.get_running_loop()
        set_main_loop(loop)
    except RuntimeError:
        pass  # Will be set later when the event loop is running

    profile_choices = list(MASTERING_PROFILES.keys())

    with gr.Blocks(title="Suno AI Agent") as app:
        gr.Markdown("# Suno AI Agent\nAutonomous music creation, mastering, and export")
        gr.Markdown("## Create")
        with gr.Row():
            with gr.Column(scale=2):
                lyrics_input = gr.Textbox(
                    label="Lyrics", lines=8,
                    placeholder="Write your lyrics here...\n\n[Verse 1]\nWalking down the street...",
                )
                styles_input = gr.Textbox(
                    label="Styles",
                    placeholder="indie pop, acoustic, dreamy, female vocals",
                )
            with gr.Column(scale=1):
                title_input = gr.Textbox(label="Title (optional)", placeholder="My Song")
                weirdness_slider = gr.Slider(0, 100, 50, step=5, label="Weirdness")
                influence_slider = gr.Slider(0, 100, 50, step=5, label="Style Influence")
                create_btn = gr.Button("Create Song", variant="primary")
        create_output = gr.Textbox(label="Create Result", interactive=False)
        create_btn.click(
            create_song_handler,
            [lyrics_input, styles_input, title_input, weirdness_slider, influence_slider],
            create_output,
        )

        gr.Markdown("---\n## Master")
        with gr.Row():
            profile_dropdown = gr.Dropdown(
                choices=profile_choices, value="radio_ready",
                label="Mastering Profile",
            )
            track_input = gr.Number(label="Track # (1-based)", value=1, precision=0)
            all_checkbox = gr.Checkbox(label="Master ALL tracks", value=True)

        with gr.Row():
            master_btn = gr.Button("Apply Mastering", variant="primary")
            tracks_btn = gr.Button("Refresh Tracks")

        master_output = gr.Textbox(label="Master Result", interactive=False)
        tracks_output = gr.Textbox(label="Tracks", interactive=False)

        master_btn.click(master_handler, [profile_dropdown, track_input, all_checkbox], master_output)
        tracks_btn.click(get_tracks_handler, [], tracks_output)

        profile_desc = "\n".join(
            f"**{name}**: {prof['description']}"
            for name, prof in MASTERING_PROFILES.items()
        )
        gr.Markdown(f"### Profiles\n{profile_desc}")

        gr.Markdown("---\n## Export")
        export_radio = gr.Radio(
            ["Full Song", "Multitrack", "Stems"],
            value="Full Song", label="Export Type",
        )
        export_btn = gr.Button("Export", variant="primary")
        export_output = gr.Textbox(label="Export Result", interactive=False)
        export_btn.click(export_handler, [export_radio], export_output)

        gr.Markdown("---\n## Agent Chat\nUse natural language to control Suno.")
        chatbot = gr.Chatbot(height=400)
        with gr.Row():
            chat_input = gr.Textbox(
                placeholder="e.g. 'Master all tracks with bass_heavy and export'",
                show_label=False, scale=4,
            )
            send_btn = gr.Button("Send", variant="primary", scale=1)
        send_btn.click(chat_handler, [chat_input, chatbot], [chat_input, chatbot])
        chat_input.submit(chat_handler, [chat_input, chatbot], [chat_input, chatbot])

        gr.Markdown("---\n## Monitor")
        with gr.Row():
            screenshot_btn = gr.Button("Take Screenshot")
            refresh_btn = gr.Button("Refresh Log")

        screenshot_img = gr.Image(label="Browser Screenshot", type="filepath")
        log_output = gr.Textbox(label="Action Log", lines=15, interactive=False)

        screenshot_btn.click(screenshot_handler, [], [screenshot_img, log_output])
        refresh_btn.click(refresh_log, [], log_output)

    return app
