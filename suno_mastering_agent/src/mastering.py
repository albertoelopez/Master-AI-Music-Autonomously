"""Mastering workflow module for Suno AI Studio."""
import asyncio
from typing import List, Optional
from dataclasses import dataclass
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

from .browser import BrowserController
from .suno_interface import SunoInterface, Track
from config.settings import MasteringPreset, MASTERING_PRESETS

console = Console()


@dataclass
class MasteringResult:
    """Result of a mastering operation."""
    track: Track
    success: bool
    message: str


class MasteringWorkflow:
    """Workflow manager for mastering tracks in Suno AI Studio."""

    def __init__(self, browser: BrowserController):
        self.browser = browser
        self.suno = SunoInterface(browser)
        self.results: List[MasteringResult] = []

    async def initialize(self) -> bool:
        """Initialize the mastering workflow."""
        console.print("\n[bold blue]Initializing Suno Mastering Agent[/bold blue]\n")

        # Connect to browser
        if not await self.browser.connect():
            return False

        # Check if we're on Suno
        current_url = self.browser.page.url if self.browser.page else ""
        if "suno.com" not in current_url:
            console.print("[yellow]![/yellow] Not on Suno.com, navigating...")
            await self.suno.navigate_to_studio()

        # Check login status
        if await self.suno.is_logged_in():
            console.print("[green]✓[/green] User is logged in")
        else:
            console.print("[yellow]![/yellow] User may not be logged in")
            console.print("Please log in to Suno in your browser first")

        return True

    async def list_tracks(self) -> List[Track]:
        """List all available tracks."""
        console.print("\n[bold]Fetching tracks...[/bold]")
        tracks = await self.suno.get_tracks()

        if tracks:
            table = Table(title="Available Tracks")
            table.add_column("#", style="dim", width=4)
            table.add_column("Title", style="cyan")
            table.add_column("ID", style="dim")

            for i, track in enumerate(tracks, 1):
                table.add_row(str(i), track.title, track.id)

            console.print(table)
        else:
            console.print("[yellow]No tracks found[/yellow]")

        return tracks

    async def master_track(
        self,
        track: Track,
        preset: Optional[str] = None,
        loudness: Optional[float] = None,
        clarity: Optional[float] = None,
        warmth: Optional[float] = None
    ) -> MasteringResult:
        """Master a single track."""
        console.print(f"\n[bold]Mastering: {track.title}[/bold]")

        # Apply preset if specified
        if preset and preset in MASTERING_PRESETS:
            p = MASTERING_PRESETS[preset]
            loudness = loudness or p.loudness
            clarity = clarity or p.clarity
            warmth = warmth or p.warmth
            console.print(f"Using preset: {preset}")

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console
        ) as progress:
            task = progress.add_task("Selecting track...", total=None)

            # Select the track
            if not await self.suno.select_track(track):
                return MasteringResult(
                    track=track,
                    success=False,
                    message="Failed to select track"
                )

            progress.update(task, description="Opening mastering panel...")

            # Open mastering panel
            if not await self.suno.open_mastering_panel():
                return MasteringResult(
                    track=track,
                    success=False,
                    message="Failed to open mastering panel"
                )

            progress.update(task, description="Applying mastering...")

            # Apply mastering
            success = await self.suno.apply_mastering(
                loudness=loudness,
                clarity=clarity,
                warmth=warmth
            )

            if success:
                return MasteringResult(
                    track=track,
                    success=True,
                    message="Mastering applied successfully"
                )
            else:
                return MasteringResult(
                    track=track,
                    success=False,
                    message="Failed to apply mastering"
                )

    async def master_multiple(
        self,
        tracks: List[Track],
        preset: Optional[str] = None,
        **kwargs
    ) -> List[MasteringResult]:
        """Master multiple tracks with the same settings."""
        results = []
        total = len(tracks)

        console.print(f"\n[bold]Mastering {total} tracks[/bold]\n")

        for i, track in enumerate(tracks, 1):
            console.print(f"[dim]({i}/{total})[/dim]", end=" ")
            result = await self.master_track(track, preset=preset, **kwargs)
            results.append(result)

            if result.success:
                console.print(f"[green]✓[/green] {track.title}")
            else:
                console.print(f"[red]✗[/red] {track.title}: {result.message}")

            # Small delay between tracks
            await asyncio.sleep(1)

        self.results = results
        return results

    async def explore(self) -> None:
        """Explore the current Suno interface to discover elements."""
        console.print("\n[bold]Exploring Suno Interface...[/bold]\n")

        info = await self.suno.explore_interface()

        console.print(f"URL: {info.get('url', 'N/A')}")
        console.print(f"Title: {info.get('title', 'N/A')}")
        console.print(f"Track elements found: {info.get('track_elements', 0)}")

        if info.get("buttons"):
            console.print("\n[bold]Buttons found:[/bold]")
            for btn in info["buttons"][:10]:
                text = btn.get("text", "").strip()[:30]
                aria = btn.get("aria_label", "")
                if text or aria:
                    console.print(f"  - {text or aria}")

        if info.get("inputs"):
            console.print("\n[bold]Inputs found:[/bold]")
            for inp in info["inputs"][:10]:
                console.print(f"  - type={inp.get('type')}, name={inp.get('name')}")

    def show_results_summary(self) -> None:
        """Show a summary of all mastering results."""
        if not self.results:
            return

        console.print("\n[bold]Mastering Results Summary[/bold]")

        table = Table()
        table.add_column("Track", style="cyan")
        table.add_column("Status")
        table.add_column("Message", style="dim")

        success_count = 0
        for result in self.results:
            status = "[green]Success[/green]" if result.success else "[red]Failed[/red]"
            if result.success:
                success_count += 1
            table.add_row(result.track.title, status, result.message)

        console.print(table)
        console.print(
            f"\n[bold]Total:[/bold] {success_count}/{len(self.results)} successful"
        )

    async def cleanup(self):
        """Clean up resources."""
        await self.browser.close()
