#!/usr/bin/env python3
"""Suno AI Agent - Autonomous music creation, mastering, and export.

Entry point for the LLM-driven agent that uses Browser Use + LangGraph
to intelligently interact with Suno's web UI.

Usage:
    python agent.py                                    # Interactive REPL (default config)
    python agent.py --provider ollama --model qwen3:8b  # Override LLM (recommended)
    python agent.py --provider ollama --model qwen3:0.6b  # Smaller/faster local model
    python agent.py --ui gradio                        # Web UI mode
    python agent.py --ui cli                           # CLI REPL mode
    python agent.py --task "Master all tracks with radio_ready and export"
    python agent.py --task "Create 3 indie pop songs"
"""
import asyncio
import json
import os
import sys

import click
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

# Ensure suno_mastering_agent package is importable
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.browser import BrowserController
from src.agent.llm_config import (
    resolve_llm, get_browser_config, get_autonomy_config, get_ui_config,
)
from src.agent.tools import set_browser
from src.agent.workflows import (
    run_mastering, run_batch, run_interactive,
    build_interactive_workflow,
)
from src.agent.browser_use_agent import SunoBrowserAgent

console = Console()

# Remove stale browser lock
LOCK = os.path.join(os.path.dirname(__file__), "browser_data", "SingletonLock")
if os.path.exists(LOCK):
    os.remove(LOCK)


async def run_cli_repl(browser: BrowserController, llm):
    """Run the interactive CLI REPL."""
    console.print(Panel(
        "[bold blue]Suno AI Agent - Interactive Mode[/bold blue]\n\n"
        "Talk to the agent in natural language. It will navigate Suno,\n"
        "create songs, master tracks, and export for you.\n\n"
        "Commands:\n"
        "  [cyan]master all <profile>[/cyan]  - Master all tracks\n"
        "  [cyan]create <description>[/cyan]  - Describe a song to create\n"
        "  [cyan]export[/cyan]                - Export current project\n"
        "  [cyan]screenshot[/cyan]            - Take a screenshot\n"
        "  [cyan]status[/cyan]                - Get current studio state\n"
        "  [cyan]quit[/cyan]                  - Exit\n\n"
        "Or just type any instruction in natural language.",
        title="Suno AI Agent",
    ))

    history = None

    while True:
        try:
            user_input = Prompt.ask("\n[bold green]agent>[/bold green]").strip()
            if not user_input:
                continue

            if user_input.lower() in ("quit", "exit", "q"):
                break

            # Quick commands that bypass the LLM for speed
            if user_input.lower() == "status":
                from src.agent.tools import get_studio_state
                result = await get_studio_state.ainvoke({})
                console.print(result)
                continue

            if user_input.lower() == "screenshot":
                from src.agent.tools import take_screenshot
                result = await take_screenshot.ainvoke({"filename": "agent_repl"})
                console.print(result)
                continue

            # Run through the ReAct agent
            with console.status("[bold yellow]Thinking...[/bold yellow]"):
                response, history = await run_interactive(
                    browser, user_input, llm=llm, history=history,
                )

            console.print(f"\n[bold]Agent:[/bold] {response}")

        except KeyboardInterrupt:
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")

    console.print("[dim]Goodbye![/dim]")


async def run_one_shot(browser: BrowserController, llm, task: str):
    """Run a single task and exit."""
    console.print(f"[bold]Task:[/bold] {task}\n")

    with console.status("[bold yellow]Working...[/bold yellow]"):
        response, _ = await run_interactive(browser, task, llm=llm)

    console.print(f"\n[bold]Result:[/bold] {response}")


async def run_gradio(browser: BrowserController, llm, port: int):
    """Launch the Gradio web UI."""
    from src.ui.gradio_app import create_app, set_main_loop

    # Set the main loop so Gradio callbacks can schedule async work
    set_main_loop(asyncio.get_running_loop())
    app = create_app(browser, llm)

    # Run Gradio's blocking launch in a thread
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, lambda: app.launch(server_port=port, share=False)
    )


@click.command()
@click.option("--provider", "-p", help="LLM provider (deepseek, ollama, openai, anthropic)")
@click.option("--model", "-m", help="Model name (provider-specific)")
@click.option("--temperature", "-t", type=float, help="LLM temperature")
@click.option("--api-key", help="API key (overrides env var)")
@click.option("--base-url", help="Custom API base URL")
@click.option("--ui", "ui_type", type=click.Choice(["cli", "gradio"]),
              help="UI mode (cli or gradio)")
@click.option("--port", type=int, help="Gradio port (default: 7860)")
@click.option("--task", help="One-shot task to execute (non-interactive)")
@click.option("--cdp-port", type=int, help="Chrome CDP port (default: 9222)")
@click.option("--headless", is_flag=True, help="Run Chrome headless")
def main(provider, model, temperature, api_key, base_url, ui_type, port, task, cdp_port, headless):
    """Suno AI Agent - Autonomous music creation and mastering.

    Start an LLM-driven agent that navigates Suno's web UI to create,
    master, and export music.
    """
    # Resolve config
    browser_config = get_browser_config()
    ui_config = get_ui_config()

    cdp_port = cdp_port or browser_config.get("cdp_port", 9222)
    ui_type = ui_type or ui_config.get("type", "cli")
    port = port or ui_config.get("port", 7860)

    # Resolve LLM
    llm_kwargs = {}
    if base_url:
        llm_kwargs["base_url"] = base_url

    try:
        llm = resolve_llm(
            provider=provider,
            model=model,
            temperature=temperature,
            api_key=api_key,
            **llm_kwargs,
        )
        console.print(f"[green]✓[/green] LLM: {provider or 'config default'} / {model or 'config default'}")
    except Exception as e:
        console.print(f"[red]✗[/red] Failed to initialize LLM: {e}")
        console.print("[yellow]Tip:[/yellow] Set your API key or use --provider ollama for local models")
        return

    async def _run():
        # Initialize browser
        browser = BrowserController(
            headless=headless or browser_config.get("headless", False),
            cdp_port=cdp_port,
        )
        if not await browser.connect():
            return

        set_browser(browser)

        try:
            if task:
                await run_one_shot(browser, llm, task)
            elif ui_type == "gradio":
                await run_gradio(browser, llm, port)
            else:
                await run_cli_repl(browser, llm)
        finally:
            await browser.close()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
