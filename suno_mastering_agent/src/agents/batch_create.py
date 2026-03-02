"""Batch song creation agent - create multiple songs from a list of prompts."""
import asyncio
from dataclasses import dataclass
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from ..browser import BrowserController
from ..skills import NavigateSkill, ModalSkill, CreateSkill

console = Console()


@dataclass
class SongSpec:
    """Specification for a song to create."""
    lyrics: str
    styles: str
    title: Optional[str] = None
    weirdness: Optional[int] = None
    style_influence: Optional[int] = None


@dataclass
class CreateResult:
    """Result of creating a song."""
    spec: SongSpec
    success: bool
    message: str


class BatchCreateAgent:
    """Create multiple songs in batch from a list of specifications.

    Navigates to Create page, fills in each song's details, and clicks Create.
    Waits between creations for generation to complete.
    """

    def __init__(self, browser: BrowserController):
        self.browser = browser
        self.nav = NavigateSkill(browser)
        self.modal = ModalSkill(browser)
        self.create = CreateSkill(browser)
        self.results: List[CreateResult] = []

    async def initialize(self) -> bool:
        """Connect and navigate to Create page."""
        if not await self.browser.connect():
            return False

        # Navigate to Create page first, then check login
        await self.nav.to_create()
        await self.modal.dismiss_all()

        login = await self.nav.is_logged_in()
        if not login.success:
            console.print(f"[yellow]Not logged in: {login.message}[/yellow]")
            return False

        return True

    async def create_song(self, spec: SongSpec) -> CreateResult:
        """Create a single song from a spec."""
        title_display = spec.title or spec.lyrics[:30] + "..."
        console.print(f"\n[bold]Creating: {title_display}[/bold]")

        r = await self.create.create_song(
            lyrics=spec.lyrics,
            styles=spec.styles,
            title=spec.title,
            weirdness=spec.weirdness,
            style_influence=spec.style_influence,
        )

        result = CreateResult(spec=spec, success=r.success, message=r.message)
        self.results.append(result)

        if r.success:
            console.print(f"  [green]Created[/green]")
        else:
            console.print(f"  [red]Failed: {r.message}[/red]")

        return result

    async def create_batch(self, specs: List[SongSpec],
                           wait_between: int = 60) -> List[CreateResult]:
        """Create multiple songs from a list of specs.

        Args:
            specs: List of SongSpec to create
            wait_between: Seconds to wait between creations for generation
        """
        console.print(f"\n[bold]Batch creating {len(specs)} songs[/bold]")
        console.print(f"Wait time between songs: {wait_between}s\n")

        results = []
        for i, spec in enumerate(specs):
            console.print(f"[dim]({i + 1}/{len(specs)})[/dim]")

            # Navigate to create page fresh each time
            await self.nav.to_create()
            await self.modal.dismiss_all()
            await asyncio.sleep(2)

            result = await self.create_song(spec)
            results.append(result)

            if i < len(specs) - 1 and result.success:
                console.print(f"  Waiting {wait_between}s for generation...")
                await asyncio.sleep(wait_between)

        self.results = results
        return results

    def show_summary(self):
        """Print summary of batch creation."""
        if not self.results:
            return

        table = Table(title="Batch Creation Results")
        table.add_column("#", style="dim", width=4)
        table.add_column("Title/Lyrics", style="cyan")
        table.add_column("Styles")
        table.add_column("Status")

        ok = 0
        for i, r in enumerate(self.results, 1):
            title = r.spec.title or r.spec.lyrics[:30]
            status = "[green]OK[/green]" if r.success else f"[red]{r.message[:30]}[/red]"
            if r.success:
                ok += 1
            table.add_row(str(i), title, r.spec.styles[:30], status)

        console.print(table)
        console.print(f"\n[bold]{ok}/{len(self.results)} songs created[/bold]")

    async def cleanup(self):
        await self.browser.close()
