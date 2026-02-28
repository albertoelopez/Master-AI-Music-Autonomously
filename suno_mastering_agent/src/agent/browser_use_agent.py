"""Browser Use integration for intelligent Suno navigation.

Connects Browser Use to our CDP Chrome instance so that an LLM can
navigate Suno's UI, read page state, and invoke our Suno skills as
custom actions.

IMPORTANT: browser-use 0.12+ has its own LLM wrappers (ChatOllama, etc.)
that are NOT compatible with LangChain models. Use resolve_browser_use_llm()
instead of resolve_llm() for the Browser Use Agent.
"""
import asyncio
import os
from typing import Optional

from browser_use import Agent, Browser, Controller
from rich.console import Console

from .llm_config import resolve_browser_use_llm, load_agent_config
from ..browser import BrowserController
from ..skills import (
    NavigateSkill, ModalSkill, StudioSkill,
    EQSkill, MixingSkill, CreateSkill,
)
from ..agents.mastering import MasteringAgent, MASTERING_PROFILES

console = Console()


def create_controller(browser_ctrl: BrowserController) -> Controller:
    """Create a Browser Use Controller with custom Suno skill actions.

    These actions let the LLM call our deterministic skills through
    natural language, e.g. 'master track 1 with bass_heavy'.
    """
    controller = Controller()

    # --- Custom actions wrapping our Suno skills ---

    @controller.action("Navigate to a Suno page (studio, create, or library)")
    async def navigate_to_page(page: str):
        nav = NavigateSkill(browser_ctrl)
        modal = ModalSkill(browser_ctrl)
        if page == "studio":
            r = await nav.to_studio()
        elif page == "create":
            r = await nav.to_create()
        elif page == "library":
            r = await nav.to_library()
        else:
            return f"Unknown page: {page}"
        await modal.dismiss_all()
        return r.message

    @controller.action("Dismiss any modal overlays blocking the UI")
    async def dismiss_modals():
        modal = ModalSkill(browser_ctrl)
        r = await modal.dismiss_all()
        return r.message

    @controller.action("Get the number of tracks and their names in the Studio")
    async def get_studio_info():
        studio = StudioSkill(browser_ctrl)
        mixing = MixingSkill(browser_ctrl)
        count_r = await studio.get_track_count()
        info_r = await mixing.get_track_info()
        tracks = info_r.data or []
        names = [t["name"] for t in tracks]
        return f"{count_r.data} tracks: {names}"

    @controller.action("Select a clip on a track by track number (1-based)")
    async def select_clip(track_number: int):
        studio = StudioSkill(browser_ctrl)
        modal = ModalSkill(browser_ctrl)
        r = await studio.select_clip(track_number - 1)
        await modal.dismiss_all()
        return r.message

    @controller.action(
        "Master a track with a profile. "
        "Profiles: radio_ready, warm_vinyl, bass_heavy, vocal_focus, bright_pop, lo_fi, clarity, flat"
    )
    async def master_track(track_number: int, profile: str = "radio_ready"):
        agent = MasteringAgent(browser_ctrl)
        r = await agent.master_track(track_number - 1, profile)
        return r.message

    @controller.action("Master all tracks with a profile")
    async def master_all(profile: str = "radio_ready"):
        agent = MasteringAgent(browser_ctrl)
        nav = NavigateSkill(browser_ctrl)
        modal = ModalSkill(browser_ctrl)
        await nav.to_studio()
        await modal.dismiss_all()
        results = await agent.master_all_tracks(profile)
        ok = sum(1 for r in results if r.success)
        return f"Mastered {ok}/{len(results)} tracks with '{profile}'"

    @controller.action("Set an EQ band parameter on the currently selected track")
    async def set_eq(band: int, freq: str = None, gain: str = None, q: str = None):
        eq = EQSkill(browser_ctrl)
        await eq.enable()
        r = await eq.set_band(band, freq=freq, gain=gain, q=q)
        return r.message

    @controller.action("Set a built-in EQ preset on the currently selected track")
    async def set_eq_preset(preset: str):
        eq = EQSkill(browser_ctrl)
        await eq.enable()
        r = await eq.set_preset(preset)
        return r.message

    @controller.action("Create a song with lyrics and styles in Custom mode")
    async def create_song(lyrics: str, styles: str, title: str = None):
        nav = NavigateSkill(browser_ctrl)
        modal = ModalSkill(browser_ctrl)
        create = CreateSkill(browser_ctrl)
        await nav.to_create()
        await modal.dismiss_all()
        r = await create.create_song(lyrics=lyrics, styles=styles, title=title)
        return r.message

    @controller.action("Export the current project (full, multitrack, or stems)")
    async def export_project(export_type: str = "full"):
        nav = NavigateSkill(browser_ctrl)
        modal = ModalSkill(browser_ctrl)
        studio = StudioSkill(browser_ctrl)
        await nav.to_studio()
        await modal.dismiss_all()
        if export_type == "full":
            r = await studio.export_full_song()
        elif export_type == "multitrack":
            r = await studio.export_multitrack()
        else:
            await studio.select_clip(0)
            await modal.dismiss_all()
            r = await studio.extract_stems("all")
        return r.message

    @controller.action("Take a screenshot of the current page")
    async def screenshot():
        os.makedirs("/tmp/suno_skills", exist_ok=True)
        path = "/tmp/suno_skills/agent_screenshot.png"
        await browser_ctrl.screenshot(path)
        return f"Screenshot saved: {path}"

    return controller


class SunoBrowserAgent:
    """High-level wrapper around Browser Use + our Suno skills.

    Connects to a running Chrome via CDP and provides an LLM-driven
    agent that can navigate Suno intelligently while also calling our
    deterministic skill actions.

    Uses browser-use native LLM wrappers (NOT LangChain) as required
    by browser-use 0.12+.
    """

    def __init__(
        self,
        llm=None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        cdp_port: int = 9222,
        browser_ctrl: Optional[BrowserController] = None,
        use_vision: bool = False,
        flash_mode: bool = True,
        llm_timeout: int = 300,
    ):
        self.cdp_port = cdp_port
        self.llm = llm or resolve_browser_use_llm(provider=provider, model=model)
        self.use_vision = use_vision
        self.flash_mode = flash_mode
        self.llm_timeout = llm_timeout
        self._browser_ctrl = browser_ctrl
        self._browser_use_browser: Optional[Browser] = None
        self._controller: Optional[Controller] = None

    async def initialize(self) -> bool:
        """Set up Chrome connection (CDP) and create the Browser Use agent."""
        try:
            # Initialize our BrowserController if not provided
            if self._browser_ctrl is None:
                self._browser_ctrl = BrowserController(cdp_port=self.cdp_port)
                if not await self._browser_ctrl.connect():
                    return False

            # Create Browser Use browser session connected to same CDP port
            self._browser_use_browser = Browser(
                cdp_url=f"http://localhost:{self.cdp_port}",
            )

            # Create controller with our custom Suno actions
            self._controller = create_controller(self._browser_ctrl)

            console.print("[green]✓[/green] Browser Use agent initialized")
            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to initialize Browser Use agent: {e}")
            return False

    async def run_task(self, instruction: str, max_steps: int = 25) -> str:
        """Run a natural language task using the Browser Use agent.

        Args:
            instruction: Natural language instruction (e.g. 'Navigate to Studio
                        and tell me how many tracks there are')
            max_steps: Maximum number of agent steps

        Returns:
            The agent's final response/result
        """
        if not self._browser_use_browser or not self._controller:
            return "Agent not initialized. Call initialize() first."

        agent = Agent(
            task=instruction,
            llm=self.llm,
            browser=self._browser_use_browser,
            controller=self._controller,
            max_actions_per_step=5,
            use_vision=self.use_vision,
            flash_mode=self.flash_mode,
            llm_timeout=self.llm_timeout,
        )

        try:
            result = await agent.run(max_steps=max_steps)
            # Extract the final result text
            if result and hasattr(result, 'final_result'):
                return result.final_result() or "Task completed (no text result)"
            return str(result) if result else "Task completed"
        except Exception as e:
            return f"Agent error: {e}"

    async def cleanup(self):
        """Close browsers and clean up."""
        if self._browser_use_browser:
            await self._browser_use_browser.close()
        if self._browser_ctrl:
            await self._browser_ctrl.close()

    @property
    def browser_ctrl(self) -> Optional[BrowserController]:
        return self._browser_ctrl
