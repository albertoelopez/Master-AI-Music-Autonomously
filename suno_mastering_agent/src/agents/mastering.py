"""Mastering agent - applies EQ presets and mixing to tracks."""
import asyncio
from dataclasses import dataclass
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from ..browser import BrowserController
from ..skills import NavigateSkill, ModalSkill, StudioSkill, EQSkill, MixingSkill

console = Console()


# Custom mastering profiles that combine EQ preset + per-band tweaks + mixing
MASTERING_PROFILES = {
    "radio_ready": {
        "description": "Bright, punchy mix for streaming/radio",
        "eq_preset": "Presence",
        "band_tweaks": {
            1: {"freq": "80Hz", "gain": "-2dB", "filter_type": "High-pass"},
            4: {"gain": "1.5dB"},
            5: {"gain": "2dB"},
        },
    },
    "warm_vinyl": {
        "description": "Warm analog feel with rolled-off highs",
        "eq_preset": "Warm",
        "band_tweaks": {
            2: {"gain": "2dB"},
            5: {"gain": "-1.5dB"},
            6: {"freq": "6kHz", "gain": "-3dB", "filter_type": "Low-pass"},
        },
    },
    "bass_heavy": {
        "description": "Deep bass for hip-hop, EDM, trap",
        "eq_preset": "Bass Boost",
        "band_tweaks": {
            1: {"freq": "50Hz", "gain": "3dB", "q": "0.5"},
            2: {"freq": "150Hz", "gain": "2dB"},
            6: {"gain": "1dB"},
        },
    },
    "vocal_focus": {
        "description": "Clear vocals, reduced mud",
        "eq_preset": "Vocal",
        "band_tweaks": {
            2: {"freq": "250Hz", "gain": "-2dB"},
            3: {"freq": "500Hz", "gain": "-1dB"},
            4: {"freq": "3kHz", "gain": "2dB"},
        },
    },
    "bright_pop": {
        "description": "Sparkly high-end for pop/dance",
        "eq_preset": "Air",
        "band_tweaks": {
            5: {"freq": "8kHz", "gain": "2dB"},
            6: {"freq": "12kHz", "gain": "3dB", "filter_type": "High-shelf"},
        },
    },
    "lo_fi": {
        "description": "Muffled, warm lo-fi aesthetic",
        "eq_preset": "Lo-Fi",
    },
    "clarity": {
        "description": "Maximum clarity and definition",
        "eq_preset": "Clarity",
        "band_tweaks": {
            2: {"freq": "300Hz", "gain": "-1.5dB"},
            4: {"freq": "2.5kHz", "gain": "1.5dB"},
        },
    },
    "flat": {
        "description": "Reset to flat/neutral EQ",
        "eq_preset": "Flat (Reset)",
    },
}


@dataclass
class MasteringResult:
    """Result of mastering a single track."""
    track_index: int
    track_name: str
    success: bool
    message: str
    profile: str


class MasteringAgent:
    """Applies mastering (EQ + mixing) to tracks in Suno Studio.

    Composes NavigateSkill, ModalSkill, StudioSkill, EQSkill, and MixingSkill.
    """

    def __init__(self, browser: BrowserController):
        self.browser = browser
        self.nav = NavigateSkill(browser)
        self.modal = ModalSkill(browser)
        self.studio = StudioSkill(browser)
        self.eq = EQSkill(browser)
        self.mixing = MixingSkill(browser)
        self.results: List[MasteringResult] = []

    async def initialize(self) -> bool:
        """Navigate to Studio and prepare for mastering."""
        if not self.browser.page:
            if not await self.browser.connect():
                return False

        login = await self.nav.is_logged_in()
        if not login.success:
            console.print(f"[yellow]Not logged in: {login.message}[/yellow]")
            console.print("Please run 'suno login' first")
            return False

        await self.nav.to_studio()
        await self.modal.dismiss_all()
        return True

    async def master_track(self, track_index: int, profile: str = "radio_ready") -> MasteringResult:
        """Master a single track with a mastering profile.

        Args:
            track_index: 0-based track index
            profile: Name from MASTERING_PROFILES
        """
        if profile not in MASTERING_PROFILES:
            return MasteringResult(
                track_index=track_index, track_name="?",
                success=False, message=f"Unknown profile: {profile}. Available: {list(MASTERING_PROFILES.keys())}",
                profile=profile
            )

        prof = MASTERING_PROFILES[profile]
        console.print(f"\n[bold]Mastering track {track_index + 1}: {prof['description']}[/bold]")

        # Step 1: Select the clip on this track
        r = await self.studio.select_clip(track_index)
        if not r.success:
            return MasteringResult(track_index=track_index, track_name="?",
                                   success=False, message=r.message, profile=profile)

        # Step 2: Dismiss any modals that appeared
        await self.modal.dismiss_all()

        # Step 3: Switch to Track tab (where EQ lives)
        r = await self.studio.switch_to_track_tab()
        if not r.success:
            return MasteringResult(track_index=track_index, track_name="?",
                                   success=False, message=r.message, profile=profile)

        # Step 4: Enable EQ
        await self.eq.enable()

        # Step 5: Set EQ preset
        eq_preset = prof.get("eq_preset", "Flat (Reset)")
        r = await self.eq.set_preset(eq_preset)
        console.print(f"  EQ preset: {r.message}")

        # Step 6: Apply per-band tweaks
        tweaks = prof.get("band_tweaks", {})
        for band_num, params in tweaks.items():
            # Set filter type first (may change available parameters)
            if "filter_type" in params:
                await self.eq.set_filter_type(int(band_num), params["filter_type"])
                await asyncio.sleep(0.3)
            r = await self.eq.set_band(
                int(band_num),
                freq=params.get("freq"),
                gain=params.get("gain"),
                q=params.get("q"),
            )
            console.print(f"  {r.message}")

        # Get track name
        track_info = await self.mixing.get_track_info()
        tracks = track_info.data or []
        track_name = tracks[track_index]["name"] if track_index < len(tracks) else f"Track {track_index + 1}"

        result = MasteringResult(
            track_index=track_index, track_name=track_name,
            success=True, message=f"Applied '{profile}' mastering",
            profile=profile
        )
        self.results.append(result)
        console.print(f"  [green]Done[/green]: {result.message}")
        return result

    async def master_all_tracks(self, profile: str = "radio_ready") -> List[MasteringResult]:
        """Master all tracks with the same profile."""
        count_result = await self.studio.get_track_count()
        track_count = count_result.data or 0

        if track_count == 0:
            console.print("[yellow]No tracks found[/yellow]")
            return []

        console.print(f"\n[bold]Mastering {track_count} tracks with '{profile}' profile[/bold]")

        results = []
        for i in range(track_count):
            result = await self.master_track(i, profile)
            results.append(result)
            await asyncio.sleep(1)

        self.results = results
        return results

    async def master_and_export(self, profile: str = "radio_ready",
                                export_type: str = "full") -> List[MasteringResult]:
        """Master all tracks then export.

        Args:
            profile: Mastering profile name
            export_type: 'full' for full song, 'multitrack' for individual tracks
        """
        results = await self.master_all_tracks(profile)

        if any(r.success for r in results):
            console.print("\n[bold]Exporting...[/bold]")
            if export_type == "multitrack":
                r = await self.studio.export_multitrack()
            else:
                r = await self.studio.export_full_song()
            console.print(f"  {r.message}")

        return results

    def show_summary(self):
        """Print a summary of mastering results."""
        if not self.results:
            return

        table = Table(title="Mastering Results")
        table.add_column("Track", style="cyan")
        table.add_column("Profile")
        table.add_column("Status")
        table.add_column("Message", style="dim")

        ok = 0
        for r in self.results:
            status = "[green]OK[/green]" if r.success else "[red]FAIL[/red]"
            if r.success:
                ok += 1
            table.add_row(r.track_name, r.profile, status, r.message)

        console.print(table)
        console.print(f"\n[bold]{ok}/{len(self.results)} tracks mastered[/bold]")

    async def cleanup(self):
        await self.browser.close()

    @staticmethod
    def list_profiles():
        """Print available mastering profiles."""
        table = Table(title="Mastering Profiles")
        table.add_column("Name", style="cyan")
        table.add_column("Description")
        table.add_column("EQ Preset")
        table.add_column("Custom Bands")

        for name, prof in MASTERING_PROFILES.items():
            tweaks = prof.get("band_tweaks", {})
            tweak_str = ", ".join(f"B{k}" for k in tweaks.keys()) if tweaks else "-"
            table.add_row(name, prof["description"], prof.get("eq_preset", "-"), tweak_str)

        console.print(table)
