"""Suno AI Studio interface module."""
import asyncio
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from rich.console import Console

from .browser import BrowserController

console = Console()


@dataclass
class Track:
    """Represents a track in Suno AI Studio."""
    id: str
    title: str
    duration: Optional[str] = None
    status: Optional[str] = None
    element_selector: Optional[str] = None


class SunoSelectors:
    """CSS selectors for Suno AI Studio elements.

    These selectors may need to be updated based on Suno's actual interface.
    Run the explorer to discover the correct selectors for your session.
    """
    # Navigation
    STUDIO_TAB = '[data-testid="studio-tab"], a[href*="studio"], text=Studio'
    LIBRARY_TAB = '[data-testid="library-tab"], a[href*="library"], text=Library'
    CREATE_TAB = '[data-testid="create-tab"], a[href*="create"], text=Create'

    # Track list
    TRACK_LIST = '[data-testid="track-list"], .track-list, .songs-list'
    TRACK_ITEM = '[data-testid="track-item"], .track-item, .song-item, .song-card'
    TRACK_TITLE = '[data-testid="track-title"], .track-title, .song-title'

    # Player controls
    PLAY_BUTTON = '[data-testid="play-button"], button[aria-label*="Play"], .play-button'
    PAUSE_BUTTON = '[data-testid="pause-button"], button[aria-label*="Pause"], .pause-button'

    # Mastering controls (these need to be discovered)
    MASTER_BUTTON = '[data-testid="master-button"], button:has-text("Master"), text=Master'
    MASTERING_PANEL = '[data-testid="mastering-panel"], .mastering-panel, .master-controls'
    LOUDNESS_SLIDER = '[data-testid="loudness"], input[name="loudness"], .loudness-slider'
    CLARITY_SLIDER = '[data-testid="clarity"], input[name="clarity"], .clarity-slider'
    WARMTH_SLIDER = '[data-testid="warmth"], input[name="warmth"], .warmth-slider'
    APPLY_MASTER = '[data-testid="apply-master"], button:has-text("Apply"), text=Apply'

    # Download
    DOWNLOAD_BUTTON = '[data-testid="download"], button[aria-label*="Download"], text=Download'

    # Modals/dialogs
    MODAL = '[role="dialog"], .modal, [data-testid="modal"]'
    CLOSE_MODAL = '[data-testid="close-modal"], button[aria-label*="Close"], .close-button'


class SunoInterface:
    """Interface for interacting with Suno AI Studio."""

    def __init__(self, browser: BrowserController):
        self.browser = browser
        self.selectors = SunoSelectors()
        self.tracks: List[Track] = []

    async def navigate_to_studio(self) -> bool:
        """Navigate to Suno AI Studio."""
        return await self.browser.navigate("https://suno.com/studio")

    async def navigate_to_library(self) -> bool:
        """Navigate to the user's library."""
        return await self.browser.navigate("https://suno.com/library")

    async def is_logged_in(self) -> bool:
        """Check if user is logged into Suno."""
        # Look for common logged-in indicators
        logged_in_selectors = [
            '[data-testid="user-menu"]',
            '[data-testid="profile"]',
            '.user-avatar',
            'button:has-text("Create")',
        ]

        for selector in logged_in_selectors:
            if await self.browser.wait_for_selector(selector, timeout=5000):
                return True
        return False

    async def get_tracks(self) -> List[Track]:
        """Get all tracks from the current view."""
        if not self.browser.page:
            return []

        tracks = []
        try:
            # Get all track elements
            track_elements = await self.browser.page.query_selector_all(
                self.selectors.TRACK_ITEM
            )

            for i, element in enumerate(track_elements):
                # Extract track info
                title_el = await element.query_selector(self.selectors.TRACK_TITLE)
                title = await title_el.text_content() if title_el else f"Track {i+1}"

                # Generate unique ID
                track_id = await element.get_attribute("data-id") or f"track-{i}"

                track = Track(
                    id=track_id,
                    title=title.strip() if title else f"Track {i+1}",
                    element_selector=f'{self.selectors.TRACK_ITEM}:nth-child({i+1})'
                )
                tracks.append(track)

            self.tracks = tracks
            console.print(f"[green]✓[/green] Found {len(tracks)} tracks")

        except Exception as e:
            console.print(f"[red]✗[/red] Error getting tracks: {e}")

        return tracks

    async def select_track(self, track: Track) -> bool:
        """Select a track for editing/mastering."""
        if track.element_selector:
            return await self.browser.click(track.element_selector)
        return False

    async def open_mastering_panel(self) -> bool:
        """Open the mastering panel for the selected track."""
        return await self.browser.click(self.selectors.MASTER_BUTTON, timeout=5000)

    async def apply_mastering(
        self,
        loudness: Optional[float] = None,
        clarity: Optional[float] = None,
        warmth: Optional[float] = None
    ) -> bool:
        """Apply mastering settings to the selected track."""
        try:
            # Wait for mastering panel
            if not await self.browser.wait_for_selector(
                self.selectors.MASTERING_PANEL, timeout=10000
            ):
                console.print("[red]✗[/red] Mastering panel not found")
                return False

            # Set loudness if provided
            if loudness is not None:
                await self._set_slider(self.selectors.LOUDNESS_SLIDER, loudness)

            # Set clarity if provided
            if clarity is not None:
                await self._set_slider(self.selectors.CLARITY_SLIDER, clarity)

            # Set warmth if provided
            if warmth is not None:
                await self._set_slider(self.selectors.WARMTH_SLIDER, warmth)

            # Apply the mastering
            if await self.browser.click(self.selectors.APPLY_MASTER):
                console.print("[green]✓[/green] Mastering applied")
                return True

            return False

        except Exception as e:
            console.print(f"[red]✗[/red] Mastering failed: {e}")
            return False

    async def _set_slider(self, selector: str, value: float) -> bool:
        """Set a slider value (0.0 to 1.0)."""
        if not self.browser.page:
            return False

        try:
            # Try to set via input value
            await self.browser.page.fill(selector, str(value))
            return True
        except Exception:
            # Try JavaScript approach for custom sliders
            script = f"""
                const slider = document.querySelector('{selector}');
                if (slider) {{
                    slider.value = {value};
                    slider.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    slider.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    return true;
                }}
                return false;
            """
            return await self.browser.evaluate(script) or False

    async def download_track(self, track: Track) -> bool:
        """Download a track."""
        # First select the track
        if not await self.select_track(track):
            return False

        # Click download button
        return await self.browser.click(self.selectors.DOWNLOAD_BUTTON)

    async def explore_interface(self) -> Dict[str, Any]:
        """Explore the Suno interface to discover elements and selectors.

        Use this to learn the actual structure of Suno's interface.
        """
        if not self.browser.page:
            return {}

        result = {
            "url": self.browser.page.url,
            "title": await self.browser.page.title(),
            "buttons": [],
            "inputs": [],
            "sliders": [],
            "track_elements": [],
        }

        # Find all interactive elements
        try:
            # Buttons
            buttons = await self.browser.page.query_selector_all("button")
            for btn in buttons[:20]:  # Limit to first 20
                text = await btn.text_content()
                aria = await btn.get_attribute("aria-label")
                result["buttons"].append({
                    "text": text.strip() if text else "",
                    "aria_label": aria
                })

            # Inputs and sliders
            inputs = await self.browser.page.query_selector_all("input, [role='slider']")
            for inp in inputs[:20]:
                inp_type = await inp.get_attribute("type")
                name = await inp.get_attribute("name")
                result["inputs"].append({
                    "type": inp_type,
                    "name": name
                })

            # Find anything that looks like tracks/songs
            potential_tracks = await self.browser.page.query_selector_all(
                "[class*='song'], [class*='track'], [class*='audio'], [data-testid*='song']"
            )
            result["track_elements"] = len(potential_tracks)

        except Exception as e:
            result["error"] = str(e)

        return result
