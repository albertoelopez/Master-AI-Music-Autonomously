#!/usr/bin/env python3
"""Suno AI Studio Automation - CLI Interface.

Skills-based automation for creating, mastering, and exporting music on Suno.
"""
import asyncio
import json
import os
import sys
import click
from rich.console import Console
from rich.prompt import Prompt

from src.browser import BrowserController
from src.agents.mastering import MasteringAgent, MASTERING_PROFILES
from src.agents.batch_create import BatchCreateAgent, SongSpec
from src.agents.autonomous_create import AutoCreateAgent, AutoCreateConfig
from src.agents.autopilot import AutopilotAgent, AutopilotConfig

console = Console()

# Remove stale browser lock on startup
LOCK = os.path.join(os.path.dirname(__file__), "browser_data", "SingletonLock")
if os.path.exists(LOCK):
    os.remove(LOCK)


@click.group()
def cli():
    """Suno AI Studio Automation Agent.

    Automate song creation, EQ mastering, mixing, and export using
    Playwright browser automation with persistent login.

    Commands:
      login     - Sign into Suno (one-time setup)
      master    - Apply EQ mastering to studio tracks
      create    - Create a new song with lyrics and styles
      batch     - Create multiple songs from a JSON file
      export    - Export the current studio project
      profiles  - List available mastering profiles
    """


@cli.command()
def login():
    """Open browser for Suno login (one-time setup)."""

    async def run():
        browser = BrowserController()
        if not await browser.connect():
            return

        await browser.navigate("https://suno.com")
        await asyncio.sleep(3)

        console.print("\n[bold]A Chromium browser window has opened.[/bold]")
        console.print("Sign in to Suno, then press [bold green]Enter[/bold green] here.\n")

        await asyncio.get_event_loop().run_in_executor(None, input)

        from src.skills import NavigateSkill
        nav = NavigateSkill(browser)
        r = await nav.is_logged_in()
        if r.success:
            console.print("[green]Login successful! Session saved.[/green]")
        else:
            console.print(f"[yellow]Could not confirm login: {r.message}[/yellow]")

        await browser.close()

    asyncio.run(run())


@cli.command()
@click.option("--track", "-t", type=int, help="Track number (1-based)")
@click.option("--profile", "-p", default="radio_ready",
              type=click.Choice(list(MASTERING_PROFILES.keys())),
              help="Mastering profile")
@click.option("--all", "master_all", is_flag=True, help="Master all tracks")
@click.option("--export", "do_export", is_flag=True, help="Export after mastering")
def master(track, profile, master_all, do_export):
    """Apply EQ mastering to studio tracks.

    Examples:
        suno master --all --profile radio_ready
        suno master --track 1 --profile warm_vinyl
        suno master --all --profile bass_heavy --export
    """

    async def run():
        browser = BrowserController()
        agent = MasteringAgent(browser)

        if not await agent.initialize():
            await agent.cleanup()
            return

        if do_export:
            await agent.master_and_export(profile)
        elif master_all:
            await agent.master_all_tracks(profile)
        elif track:
            await agent.master_track(track - 1, profile)
        else:
            console.print("Specify --track N or --all")
            await agent.cleanup()
            return

        agent.show_summary()
        await agent.cleanup()

    asyncio.run(run())


@cli.command()
@click.option("--lyrics", "-l", required=True, help="Song lyrics or prompt")
@click.option("--styles", "-s", required=True, help="Style tags/description")
@click.option("--title", "-t", help="Song title")
@click.option("--weirdness", "-w", type=int, help="Weirdness 0-100")
@click.option("--influence", "-i", type=int, help="Style influence 0-100")
def create(lyrics, styles, title, weirdness, influence):
    """Create a new song with lyrics and styles.

    Example:
        suno create -l "Verse 1: Walking down..." -s "indie pop, acoustic" -t "Morning Walk"
    """

    async def run():
        browser = BrowserController()
        agent = BatchCreateAgent(browser)

        if not await agent.initialize():
            await agent.cleanup()
            return

        spec = SongSpec(
            lyrics=lyrics, styles=styles, title=title,
            weirdness=weirdness, style_influence=influence,
        )
        await agent.create_song(spec)
        agent.show_summary()
        await agent.cleanup()

    asyncio.run(run())


@cli.command()
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--wait", "-w", type=int, default=60, help="Seconds between songs")
def batch(json_file, wait):
    """Create multiple songs from a JSON file.

    JSON format: [{"lyrics": "...", "styles": "...", "title": "...", "weirdness": 50}, ...]

    Example:
        suno batch songs.json --wait 90
    """

    async def run():
        with open(json_file) as f:
            songs = json.load(f)

        specs = [SongSpec(**s) for s in songs]
        console.print(f"Loaded {len(specs)} songs from {json_file}")

        browser = BrowserController()
        agent = BatchCreateAgent(browser)

        if not await agent.initialize():
            await agent.cleanup()
            return

        await agent.create_batch(specs, wait_between=wait)
        agent.show_summary()
        await agent.cleanup()

    asyncio.run(run())


@cli.command()
@click.argument("json_file", type=click.Path(exists=True))
@click.option("--max-songs", type=int, default=0,
              help="Stop after N successful songs (0 = no song limit)")
@click.option("--hours", type=float, default=0.0,
              help="Stop after this many hours (0 = no time limit)")
@click.option("--forever", is_flag=True,
              help="Run continuously until interrupted")
@click.option("--wait", "wait_between", type=int, default=75,
              help="Seconds to wait after each successful create")
@click.option("--retries", type=int, default=2,
              help="Retries per song spec before skipping")
@click.option("--retry-wait", type=int, default=20,
              help="Seconds between retries")
@click.option("--cycle/--no-cycle", default=True,
              help="Loop back to start of JSON specs when end is reached")
@click.option("--log-file", default="/tmp/suno_autocreate.jsonl",
              help="JSONL log path for attempts/results")
@click.option("--pause-on-captcha/--no-pause-on-captcha", default=True,
              help="Pause queue when CAPTCHA blocks creation")
@click.option("--resume-file", default="/tmp/suno_autocreate.resume",
              help="File signal used to resume after CAPTCHA pause")
@click.option("--notify-cmd", default=None,
              help="Optional shell command run on CAPTCHA pause; message is passed as one arg")
def autocreate(
    json_file,
    max_songs,
    hours,
    forever,
    wait_between,
    retries,
    retry_wait,
    cycle,
    log_file,
    pause_on_captcha,
    resume_file,
    notify_cmd,
):
    """Run autonomous song creation queue from a JSON spec file.

    JSON format: [{"lyrics": "...", "styles": "...", "title": "..."}]

    Examples:
        suno autocreate songs.json --max-songs 100 --wait 90
        suno autocreate songs.json --hours 6 --cycle
        suno autocreate songs.json --forever --retries 3
    """

    if max_songs < 0:
        raise click.BadParameter("--max-songs must be >= 0")
    if hours < 0:
        raise click.BadParameter("--hours must be >= 0")
    if wait_between < 0 or retries < 0 or retry_wait < 0:
        raise click.BadParameter("wait/retries values must be >= 0")

    async def run():
        with open(json_file, encoding="utf-8") as f:
            songs = json.load(f)
        specs = [SongSpec(**s) for s in songs]
        console.print(f"Loaded {len(specs)} song specs from {json_file}")

        browser = BrowserController()
        agent = AutoCreateAgent(browser)
        cfg = AutoCreateConfig(
            wait_between=wait_between,
            retry_wait=retry_wait,
            retries=retries,
            max_songs=max_songs,
            max_hours=hours,
            forever=forever,
            cycle_specs=cycle,
            log_file=log_file,
            pause_on_captcha=pause_on_captcha,
            resume_file=resume_file,
            notify_cmd=notify_cmd,
        )

        if not await agent.initialize():
            await agent.cleanup()
            return

        try:
            await agent.run(specs, cfg)
        finally:
            await agent.cleanup()

    asyncio.run(run())


@cli.command()
@click.option("--music-type", "-m", required=True,
              help="High-level type (e.g. pop, edm, lofi, rock, hiphop, rnb)")
@click.option("--count", "-n", type=int, default=1,
              help="How many songs to generate in this run")
@click.option("--wait-generation", type=int, default=90,
              help="Seconds to wait after Create before mastering/export")
@click.option("--wait-between", type=int, default=20,
              help="Seconds between songs")
@click.option("--export-type", type=click.Choice(["full", "multitrack"]), default="full",
              help="Export mode after mastering")
@click.option("--step-retries", type=int, default=2,
              help="Retries for create/master_export steps")
@click.option("--checkpoint-file", default="/tmp/suno_autopilot_checkpoint.json",
              help="Checkpoint file for resume support")
@click.option("--resume/--no-resume", default=False,
              help="Resume from checkpoint if available")
@click.option("--continue-on-error/--stop-on-error", default=True,
              help="Continue to next song on failures")
@click.option("--planner", type=click.Choice(["auto", "template", "dspy"]), default="auto",
              help="Spec planner backend")
@click.option("--dspy-model", default=None,
              help="DSPy model string (overrides DSPY_MODEL env var)")
@click.option("--phase2/--no-phase2", default=False,
              help="Enable BMAD/Gastown-inspired phased multi-candidate planning")
@click.option("--candidate-count", type=int, default=3,
              help="Number of parallel planning candidates in phase2 mode")
@click.option("--phase2-artifact-log", default="/tmp/suno_phase2_artifacts.jsonl",
              help="JSONL artifact log for phase2 planning phases")
def autopilot(
    music_type,
    count,
    wait_generation,
    wait_between,
    export_type,
    step_retries,
    checkpoint_file,
    resume,
    continue_on_error,
    planner,
    dspy_model,
    phase2,
    candidate_count,
    phase2_artifact_log,
):
    """Fully automated: generate spec from music type, create, master, export.

    Example:
        suno autopilot --music-type "edm" --count 5 --wait-generation 100
    """
    if count <= 0:
        raise click.BadParameter("--count must be > 0")
    if wait_generation < 0 or wait_between < 0:
        raise click.BadParameter("wait values must be >= 0")
    if step_retries < 0:
        raise click.BadParameter("--step-retries must be >= 0")
    if candidate_count <= 0:
        raise click.BadParameter("--candidate-count must be > 0")

    async def run():
        browser = BrowserController()
        agent = AutopilotAgent(browser)
        cfg = AutopilotConfig(
            music_type=music_type,
            count=count,
            wait_generation=wait_generation,
            wait_between=wait_between,
            export_type=export_type,
            step_retries=step_retries,
            checkpoint_file=checkpoint_file,
            resume=resume,
            continue_on_error=continue_on_error,
            planner=planner,
            dspy_model=dspy_model,
            phase2=phase2,
            candidate_count=candidate_count,
            phase2_artifact_log=phase2_artifact_log,
        )
        if not await agent.initialize():
            await browser.close()
            return
        try:
            await agent.run(cfg)
        finally:
            await browser.close()

    asyncio.run(run())


@cli.command()
@click.option("--type", "export_type", default="full",
              type=click.Choice(["full", "selected", "multitrack", "stems"]),
              help="Export type")
def export(export_type):
    """Export the current studio project.

    Types:
        full       - Export full song as WAV
        selected   - Export selected time range as WAV
        multitrack - Export each track as separate WAV
        stems      - Extract stems from selected clip
    """

    async def run():
        browser = BrowserController()
        if not await browser.connect():
            return

        from src.skills import NavigateSkill, ModalSkill, StudioSkill
        nav = NavigateSkill(browser)
        modal = ModalSkill(browser)
        studio = StudioSkill(browser)

        await nav.to_studio()
        await modal.dismiss_all()

        if export_type == "full":
            r = await studio.export_full_song()
        elif export_type == "selected":
            r = await studio.export_selected_range()
        elif export_type == "multitrack":
            r = await studio.export_multitrack()
        else:
            await studio.select_clip(0)
            await modal.dismiss_all()
            r = await studio.extract_stems("all")

        console.print(f"{'[green]' if r.success else '[red]'}{r.message}")
        await browser.close()

    asyncio.run(run())


@cli.command()
def profiles():
    """List available mastering profiles."""
    MasteringAgent.list_profiles()


@cli.command()
@click.option("--provider", "-p", help="LLM provider (deepseek, ollama, openai, anthropic)")
@click.option("--model", "-m", help="Model name")
@click.option("--ui", "ui_type", type=click.Choice(["cli", "gradio"]), default="cli",
              help="UI mode")
@click.option("--task", help="One-shot task (non-interactive)")
@click.pass_context
def agent(ctx, provider, model, ui_type, task):
    """Start the AI agent for autonomous Suno control.

    Uses an LLM (DeepSeek, Ollama, etc.) with Browser Use for intelligent
    navigation and our existing skills for precise actions.

    Examples:
        suno agent                                      # Interactive CLI
        suno agent --provider ollama --model llama3.3    # Use local Ollama
        suno agent --ui gradio                           # Web UI at localhost:7860
        suno agent --task "Master all tracks with radio_ready"
    """
    # Delegate to agent.py
    import subprocess
    cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "agent.py")]
    if provider:
        cmd.extend(["--provider", provider])
    if model:
        cmd.extend(["--model", model])
    if ui_type:
        cmd.extend(["--ui", ui_type])
    if task:
        cmd.extend(["--task", task])

    result = subprocess.run(cmd)
    sys.exit(result.returncode)


@cli.command()
def interactive():
    """Start interactive session with all skills available."""

    async def run():
        browser = BrowserController()
        if not await browser.connect():
            return

        from src.skills import NavigateSkill, ModalSkill, StudioSkill, EQSkill, MixingSkill, CreateSkill

        nav = NavigateSkill(browser)
        modal = ModalSkill(browser)
        studio = StudioSkill(browser)
        eq = EQSkill(browser)
        mixing = MixingSkill(browser)
        create = CreateSkill(browser)

        console.print("\n[bold blue]Suno Studio Interactive Mode[/bold blue]")
        console.print("Commands: studio, create, library, eq <preset>, band <n> <freq> <gain> <q>")
        console.print("          master <profile>, export, stems, tracks, profiles, quit\n")

        while True:
            try:
                cmd = Prompt.ask("[bold]suno>[/bold]").strip()
                parts = cmd.split()
                if not parts:
                    continue

                action = parts[0].lower()

                if action in ("quit", "exit", "q"):
                    break
                elif action == "studio":
                    await nav.to_studio()
                    await modal.dismiss_all()
                elif action == "create":
                    await nav.to_create()
                    await modal.dismiss_all()
                elif action == "library":
                    await nav.to_library()
                elif action == "dismiss":
                    r = await modal.dismiss_all()
                    console.print(r.message)
                elif action == "select":
                    idx = int(parts[1]) - 1 if len(parts) > 1 else 0
                    r = await studio.select_clip(idx)
                    console.print(r.message)
                elif action == "clip":
                    r = await studio.switch_to_clip_tab()
                    console.print(r.message)
                elif action == "track":
                    r = await studio.switch_to_track_tab()
                    console.print(r.message)
                elif action == "eq":
                    if len(parts) > 1:
                        preset = " ".join(parts[1:])
                        r = await eq.set_preset(preset)
                    else:
                        r = await eq.get_current_state()
                        if r.data:
                            for b, v in r.data.items():
                                console.print(f"  Band {b}: {v}")
                    console.print(r.message)
                elif action == "band":
                    if len(parts) >= 3:
                        b = int(parts[1])
                        freq = parts[2] if len(parts) > 2 else None
                        gain = parts[3] if len(parts) > 3 else None
                        q = parts[4] if len(parts) > 4 else None
                        r = await eq.set_band(b, freq=freq, gain=gain, q=q)
                        console.print(r.message)
                    else:
                        console.print("Usage: band <n> [freq] [gain] [q]")
                elif action == "master":
                    profile = parts[1] if len(parts) > 1 else "radio_ready"
                    agent = MasteringAgent(browser)
                    await agent.master_all_tracks(profile)
                    agent.show_summary()
                elif action == "export":
                    r = await studio.export_full_song()
                    console.print(r.message)
                elif action == "stems":
                    r = await studio.extract_stems()
                    console.print(r.message)
                elif action == "tracks":
                    r = await mixing.get_track_info()
                    if r.data:
                        for t in r.data:
                            console.print(f"  {t['name']}")
                    console.print(r.message)
                elif action == "profiles":
                    MasteringAgent.list_profiles()
                elif action == "screenshot":
                    path = parts[1] if len(parts) > 1 else "/tmp/suno_screenshot.png"
                    await browser.screenshot(path)
                elif action == "help":
                    console.print("Commands:")
                    console.print("  studio/create/library - Navigate pages")
                    console.print("  select [N]           - Select clip on track N")
                    console.print("  clip/track           - Switch right panel tab")
                    console.print("  eq [preset]          - Set EQ preset or show state")
                    console.print("  band N freq gain q   - Set band parameters")
                    console.print("  master [profile]     - Master all tracks")
                    console.print("  export               - Export full song")
                    console.print("  stems                - Extract stems")
                    console.print("  tracks               - List tracks")
                    console.print("  profiles             - List mastering profiles")
                    console.print("  screenshot [path]    - Take screenshot")
                    console.print("  dismiss              - Dismiss modals")
                    console.print("  quit                 - Exit")
                else:
                    console.print(f"Unknown: {action}. Type 'help' for commands.")

            except KeyboardInterrupt:
                break
            except Exception as e:
                console.print(f"[red]Error: {e}[/red]")

        await browser.close()
        console.print("[dim]Goodbye![/dim]")

    asyncio.run(run())


if __name__ == "__main__":
    cli()
