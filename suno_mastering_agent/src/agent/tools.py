"""LangChain tool wrappers for existing Suno skills and agents.

Each tool is async, matching our Playwright-based skills.
The shared browser instance must be set before running any tool.
"""
import os
from typing import Optional

from langchain_core.tools import tool

from ..browser import BrowserController
from ..skills import (
    NavigateSkill, ModalSkill, StudioSkill,
    EQSkill, MixingSkill, CreateSkill,
)
from ..agents.mastering import MasteringAgent, MASTERING_PROFILES
from ..agents.batch_create import BatchCreateAgent, SongSpec


# Shared browser instance (set by the workflow before running tools)
_browser: Optional[BrowserController] = None


def set_browser(browser: BrowserController):
    """Set the shared browser instance for all tools."""
    global _browser
    _browser = browser


def get_browser() -> BrowserController:
    """Get the shared browser instance."""
    if _browser is None:
        raise RuntimeError("Browser not initialized. Call set_browser() first.")
    return _browser


# --- Navigation tools ---

@tool
async def navigate_to(page: str) -> str:
    """Navigate to a Suno page.

    Args:
        page: Page name - one of 'studio', 'create', 'library'
    """
    browser = get_browser()
    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)

    if page == "studio":
        r = await nav.to_studio()
    elif page == "create":
        r = await nav.to_create()
    elif page == "library":
        r = await nav.to_library()
    else:
        return f"Unknown page: {page}. Use studio, create, or library."

    await modal.dismiss_all()
    return r.message


@tool
async def take_screenshot(filename: str = "screenshot") -> str:
    """Take a screenshot of the current browser page.

    Args:
        filename: Base name for the screenshot file (saved to /tmp/suno_skills/)
    """
    browser = get_browser()
    os.makedirs("/tmp/suno_skills", exist_ok=True)
    path = f"/tmp/suno_skills/{filename}.png"
    ok = await browser.screenshot(path)
    if ok:
        return f"Screenshot saved to {path}"
    return "Screenshot failed"


# --- Studio tools ---

@tool
async def get_studio_state() -> str:
    """Get the current state of the Suno Studio - track names, count, and current page URL."""
    browser = get_browser()
    mixing = MixingSkill(browser)
    studio = StudioSkill(browser)

    track_info = await mixing.get_track_info()
    track_count = await studio.get_track_count()

    url = browser.page.url if browser.page else "unknown"

    tracks = track_info.data or []
    track_names = [t["name"] for t in tracks]

    return (
        f"URL: {url}\n"
        f"Tracks: {track_count.data or 0}\n"
        f"Track names: {track_names}"
    )


@tool
async def select_track(track_number: int) -> str:
    """Select a track in the Studio by clicking its clip on the timeline.

    Args:
        track_number: Track number (1-based, e.g. 1 for first track)
    """
    browser = get_browser()
    studio = StudioSkill(browser)
    modal = ModalSkill(browser)

    r = await studio.select_clip(track_number - 1)
    await modal.dismiss_all()
    return r.message


# --- Mastering tools ---

@tool
async def master_track(track_number: int, profile: str = "radio_ready") -> str:
    """Apply a mastering profile to a specific track.

    This sets the EQ preset and applies per-band tweaks from the profile.

    Args:
        track_number: Track number (1-based)
        profile: Mastering profile name. Available: radio_ready, warm_vinyl, bass_heavy,
                 vocal_focus, bright_pop, lo_fi, clarity, flat
    """
    browser = get_browser()
    studio = StudioSkill(browser)
    modal = ModalSkill(browser)
    eq = EQSkill(browser)

    if profile not in MASTERING_PROFILES:
        return f"Unknown profile: {profile}. Available: {list(MASTERING_PROFILES.keys())}"

    prof = MASTERING_PROFILES[profile]
    idx = track_number - 1

    # Select clip, dismiss modals, switch to Track tab
    r = await studio.select_clip(idx)
    if not r.success:
        return f"Failed to select track {track_number}: {r.message}"

    await modal.dismiss_all()
    await studio.switch_to_track_tab()
    await eq.enable()

    # Set preset
    r = await eq.set_preset(prof.get("eq_preset", "Flat (Reset)"))
    results = [f"Preset: {r.message}"]

    # Apply tweaks
    for band_num, params in prof.get("band_tweaks", {}).items():
        r = await eq.set_band(
            int(band_num),
            freq=params.get("freq"),
            gain=params.get("gain"),
            q=params.get("q"),
        )
        if "filter_type" in params:
            await eq.set_filter_type(int(band_num), params["filter_type"])
        results.append(r.message)

    return f"Mastered track {track_number} with '{profile}': " + "; ".join(results)


@tool
async def master_all_tracks(profile: str = "radio_ready") -> str:
    """Master all tracks in the current Studio project with a mastering profile.

    Args:
        profile: Mastering profile name. Available: radio_ready, warm_vinyl, bass_heavy,
                 vocal_focus, bright_pop, lo_fi, clarity, flat
    """
    browser = get_browser()
    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)

    await nav.to_studio()
    await modal.dismiss_all()

    agent = MasteringAgent(browser)
    results = await agent.master_all_tracks(profile)
    ok = sum(1 for r in results if r.success)
    return f"Mastered {ok}/{len(results)} tracks with '{profile}'"


@tool
async def list_mastering_profiles() -> str:
    """List all available mastering profiles with descriptions."""
    lines = []
    for name, prof in MASTERING_PROFILES.items():
        lines.append(f"- {name}: {prof['description']} (EQ: {prof.get('eq_preset', 'Flat')})")
    return "Available mastering profiles:\n" + "\n".join(lines)


# --- EQ tools ---

@tool
async def set_eq_band(band: int, freq: Optional[str] = None,
                      gain: Optional[str] = None, q: Optional[str] = None) -> str:
    """Set EQ parameters for a specific band on the currently selected track.

    Must have a track selected and be on the Track tab first.

    Args:
        band: Band number (1-6)
        freq: Frequency (e.g. '200Hz', '2kHz')
        gain: Gain in dB (e.g. '3.0dB', '-2.5dB')
        q: Q/resonance value (e.g. '1.5', '0.5')
    """
    browser = get_browser()
    eq = EQSkill(browser)
    await eq.enable()
    r = await eq.set_band(band, freq=freq, gain=gain, q=q)
    return r.message


@tool
async def set_eq_preset(preset_name: str) -> str:
    """Set a built-in EQ preset on the currently selected track.

    Args:
        preset_name: Preset name. Available: Flat (Reset), High-pass, Vocal, Warm,
                     Presence, Bass Boost, Air, Clarity, Fullness, Lo-fi, Modern
    """
    browser = get_browser()
    eq = EQSkill(browser)
    await eq.enable()
    r = await eq.set_preset(preset_name)
    return r.message


# --- Song creation tools ---

@tool
async def create_song(lyrics: str, styles: str, title: Optional[str] = None,
                      weirdness: Optional[int] = None,
                      style_influence: Optional[int] = None) -> str:
    """Create a new song on Suno with given lyrics and styles.

    Navigates to the Create page, fills in Custom mode fields, and clicks Create.

    Args:
        lyrics: Song lyrics or prompt text
        styles: Style tags/description (e.g. 'indie pop, acoustic, dreamy')
        title: Optional song title
        weirdness: Weirdness slider 0-100 (default 50)
        style_influence: Style influence slider 0-100 (default 50)
    """
    browser = get_browser()
    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    create = CreateSkill(browser)

    await nav.to_create()
    await modal.dismiss_all()

    r = await create.create_song(
        lyrics=lyrics, styles=styles, title=title,
        weirdness=weirdness, style_influence=style_influence,
    )
    return r.message


# --- Export tools ---

@tool
async def export_song(export_type: str = "full") -> str:
    """Export the current Studio project.

    Args:
        export_type: Export type - 'full' (full song WAV), 'multitrack' (separate tracks),
                     or 'stems' (extract stems from selected clip)
    """
    browser = get_browser()
    studio = StudioSkill(browser)
    modal = ModalSkill(browser)
    nav = NavigateSkill(browser)

    await nav.to_studio()
    await modal.dismiss_all()

    if export_type == "full":
        r = await studio.export_full_song()
    elif export_type == "multitrack":
        r = await studio.export_multitrack()
    elif export_type == "stems":
        await studio.select_clip(0)
        await modal.dismiss_all()
        r = await studio.extract_stems("all")
    else:
        return f"Unknown export type: {export_type}. Use full, multitrack, or stems."

    return r.message


# --- Mixing tools ---

@tool
async def set_track_volume(track_number: int, db_offset: float) -> str:
    """Adjust volume for a track.

    Args:
        track_number: Track number (1-based)
        db_offset: Volume adjustment in dB (positive = louder, negative = quieter)
    """
    browser = get_browser()
    mixing = MixingSkill(browser)
    r = await mixing.set_volume(track_number - 1, db_offset)
    return r.message


@tool
async def set_track_pan(track_number: int, pan: float) -> str:
    """Set pan position for a track.

    Args:
        track_number: Track number (1-based)
        pan: Pan value from -1.0 (full left) to 1.0 (full right), 0 = center
    """
    browser = get_browser()
    mixing = MixingSkill(browser)
    r = await mixing.set_pan(track_number - 1, pan)
    return r.message


# --- Collect all tools ---

ALL_TOOLS = [
    navigate_to,
    take_screenshot,
    get_studio_state,
    select_track,
    master_track,
    master_all_tracks,
    list_mastering_profiles,
    set_eq_band,
    set_eq_preset,
    create_song,
    export_song,
    set_track_volume,
    set_track_pan,
]
