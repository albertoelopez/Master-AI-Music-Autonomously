#!/usr/bin/env python3
"""Suno AI Studio Mastering Agent - CLI Interface."""
import asyncio
import click
from rich.console import Console
from rich.prompt import Prompt, IntPrompt

from src.browser import BrowserController
from src.mastering import MasteringWorkflow
from config.settings import DEFAULT_CONFIG, MASTERING_PRESETS

console = Console()


@click.group()
@click.option(
    "--port",
    default=DEFAULT_CONFIG.chrome_debug_port,
    help="Chrome remote debugging port"
)
@click.pass_context
def cli(ctx, port):
    """Suno AI Studio Mastering Agent.

    Automate audio mastering for your Suno tracks using browser automation.

    Prerequisites:
    - Chrome must be running with --remote-debugging-port=9222
    - You must be logged into Suno.com in that Chrome instance
    """
    ctx.ensure_object(dict)
    ctx.obj["port"] = port


@cli.command()
@click.pass_context
def list(ctx):
    """List all tracks in your Suno workspace."""
    port = ctx.obj["port"]

    async def run():
        browser = BrowserController(debug_port=port)
        workflow = MasteringWorkflow(browser)

        if await workflow.initialize():
            await workflow.list_tracks()
            await workflow.cleanup()

    asyncio.run(run())


@cli.command()
@click.option("--track", "-t", help="Track number or name to master")
@click.option("--preset", "-p", type=click.Choice(list(MASTERING_PRESETS.keys())), help="Mastering preset")
@click.option("--loudness", "-l", type=float, help="Loudness level (0.0-1.0)")
@click.option("--clarity", "-c", type=float, help="Clarity level (0.0-1.0)")
@click.option("--warmth", "-w", type=float, help="Warmth level (0.0-1.0)")
@click.option("--all", "master_all", is_flag=True, help="Master all tracks")
@click.pass_context
def master(ctx, track, preset, loudness, clarity, warmth, master_all):
    """Master one or more tracks.

    Examples:
        suno-master master --track 1 --preset loud
        suno-master master --track "My Song" --loudness 0.8
        suno-master master --all --preset default
    """
    port = ctx.obj["port"]

    async def run():
        browser = BrowserController(debug_port=port)
        workflow = MasteringWorkflow(browser)

        if not await workflow.initialize():
            return

        tracks = await workflow.list_tracks()
        if not tracks:
            console.print("[red]No tracks found to master[/red]")
            await workflow.cleanup()
            return

        if master_all:
            # Master all tracks
            await workflow.master_multiple(
                tracks,
                preset=preset,
                loudness=loudness,
                clarity=clarity,
                warmth=warmth
            )
        elif track:
            # Find specific track
            target_track = None

            # Try by number
            try:
                idx = int(track) - 1
                if 0 <= idx < len(tracks):
                    target_track = tracks[idx]
            except ValueError:
                # Try by name
                for t in tracks:
                    if track.lower() in t.title.lower():
                        target_track = t
                        break

            if target_track:
                result = await workflow.master_track(
                    target_track,
                    preset=preset,
                    loudness=loudness,
                    clarity=clarity,
                    warmth=warmth
                )
                if result.success:
                    console.print(f"[green]✓[/green] {result.message}")
                else:
                    console.print(f"[red]✗[/red] {result.message}")
            else:
                console.print(f"[red]Track not found: {track}[/red]")
        else:
            # Interactive mode
            console.print("\n[bold]Select a track to master:[/bold]")
            track_num = IntPrompt.ask(
                "Enter track number",
                default=1,
                choices=[str(i) for i in range(1, len(tracks) + 1)]
            )
            target_track = tracks[track_num - 1]

            if not preset:
                preset = Prompt.ask(
                    "Select preset",
                    choices=list(MASTERING_PRESETS.keys()),
                    default="default"
                )

            result = await workflow.master_track(target_track, preset=preset)
            if result.success:
                console.print(f"\n[green]✓[/green] {result.message}")
            else:
                console.print(f"\n[red]✗[/red] {result.message}")

        workflow.show_results_summary()
        await workflow.cleanup()

    asyncio.run(run())


@cli.command()
@click.pass_context
def explore(ctx):
    """Explore the Suno interface to discover elements.

    Use this to debug selector issues or understand the interface structure.
    """
    port = ctx.obj["port"]

    async def run():
        browser = BrowserController(debug_port=port)
        workflow = MasteringWorkflow(browser)

        if await workflow.initialize():
            await workflow.explore()
            await workflow.cleanup()

    asyncio.run(run())


@cli.command()
@click.pass_context
def interactive(ctx):
    """Start interactive mastering session."""
    port = ctx.obj["port"]

    async def run():
        browser = BrowserController(debug_port=port)
        workflow = MasteringWorkflow(browser)

        if not await workflow.initialize():
            return

        console.print("\n[bold blue]Suno Mastering Agent - Interactive Mode[/bold blue]")
        console.print("Commands: list, master, explore, presets, quit\n")

        while True:
            try:
                cmd = Prompt.ask("[bold]suno>[/bold]").strip().lower()

                if cmd in ("quit", "exit", "q"):
                    break
                elif cmd == "list":
                    await workflow.list_tracks()
                elif cmd == "explore":
                    await workflow.explore()
                elif cmd == "presets":
                    console.print("\n[bold]Available Presets:[/bold]")
                    for name, preset in MASTERING_PRESETS.items():
                        console.print(f"  - {name}: {preset.description}")
                elif cmd.startswith("master"):
                    parts = cmd.split()
                    if len(parts) > 1:
                        track_num = int(parts[1]) - 1
                        tracks = await workflow.suno.get_tracks()
                        if 0 <= track_num < len(tracks):
                            preset = parts[2] if len(parts) > 2 else "default"
                            await workflow.master_track(tracks[track_num], preset=preset)
                    else:
                        console.print("Usage: master <track_number> [preset]")
                elif cmd == "help":
                    console.print("Commands:")
                    console.print("  list          - List all tracks")
                    console.print("  master N [P]  - Master track N with preset P")
                    console.print("  explore       - Explore interface elements")
                    console.print("  presets       - Show available presets")
                    console.print("  quit          - Exit interactive mode")
                else:
                    console.print(f"Unknown command: {cmd}")

            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        await workflow.cleanup()
        console.print("\n[dim]Goodbye![/dim]")

    asyncio.run(run())


@cli.command()
@click.option("--path", "-p", default="screenshot.png", help="Path to save screenshot")
@click.pass_context
def screenshot(ctx, path):
    """Take a screenshot of the current browser state."""
    port = ctx.obj["port"]

    async def run():
        browser = BrowserController(debug_port=port)
        if await browser.connect():
            await browser.screenshot(path)
            await browser.close()

    asyncio.run(run())


if __name__ == "__main__":
    cli()
