"""Autonomous queue runner for high-throughput song creation."""
import asyncio
import json
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.table import Table

from ..browser import BrowserController
from ..skills import NavigateSkill, ModalSkill, CreateSkill
from .batch_create import SongSpec

console = Console()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class AutoCreateConfig:
    """Runtime config for autonomous creation."""
    wait_between: int = 75
    retry_wait: int = 20
    retries: int = 2
    max_songs: int = 0
    max_hours: float = 0.0
    forever: bool = False
    cycle_specs: bool = True
    log_file: str = "/tmp/suno_autocreate.jsonl"
    pause_on_captcha: bool = True
    resume_file: str = "/tmp/suno_autocreate.resume"
    notify_cmd: Optional[str] = None


class AutoCreateAgent:
    """Create songs continuously from a spec queue until limits are reached."""

    def __init__(self, browser: BrowserController):
        self.browser = browser
        self.nav = NavigateSkill(browser)
        self.modal = ModalSkill(browser)
        self.create = CreateSkill(browser)
        self.successes = 0
        self.failures = 0
        self.attempts = 0
        self._stop_requested = False

    async def initialize(self) -> bool:
        """Connect, navigate, and verify login."""
        if not await self.browser.connect():
            return False

        await self.nav.to_create()
        await self.modal.dismiss_all()

        login = await self.nav.is_logged_in()
        if not login.success:
            console.print(f"[yellow]Not logged in: {login.message}[/yellow]")
            return False
        return True

    async def cleanup(self):
        await self.browser.close()

    async def run(self, specs: list[SongSpec], config: AutoCreateConfig):
        """Run autonomous queue."""
        if not specs:
            console.print("[red]No song specs provided.[/red]")
            return

        start_monotonic = asyncio.get_event_loop().time()
        started_at = _utc_now()
        log_path = Path(config.log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        def should_stop() -> Optional[str]:
            if self._stop_requested:
                return "stop requested"
            elapsed_hours = (asyncio.get_event_loop().time() - start_monotonic) / 3600.0
            if config.max_songs > 0 and self.successes >= config.max_songs:
                return f"target reached ({self.successes}/{config.max_songs} successful songs)"
            if config.max_hours > 0 and elapsed_hours >= config.max_hours:
                return f"time limit reached ({elapsed_hours:.2f}h/{config.max_hours:.2f}h)"
            if not config.forever and config.max_songs <= 0 and config.max_hours <= 0:
                # Safe default: one pass over specs.
                if spec_idx >= len(specs):
                    return "completed single pass over input specs"
            return None

        def append_log(event: dict):
            with log_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")

        def notify(message: str):
            console.print(f"[yellow]{message}[/yellow]")
            if config.notify_cmd:
                try:
                    subprocess.run(
                        f"{config.notify_cmd} {json.dumps(message)}",
                        shell=True,
                        check=False,
                    )
                except Exception as exc:
                    console.print(f"[red]notify_cmd failed: {exc}[/red]")

        console.print(
            "[bold]Autonomous Create Started[/bold]\n"
            f"  Specs: {len(specs)}\n"
            f"  Wait between successes: {config.wait_between}s\n"
            f"  Retries per song: {config.retries}\n"
            f"  Retry wait: {config.retry_wait}s\n"
            f"  Max songs: {config.max_songs or 'none'}\n"
            f"  Max hours: {config.max_hours or 'none'}\n"
            f"  Forever: {config.forever}\n"
            f"  Cycle specs: {config.cycle_specs}\n"
            f"  Log: {config.log_file}\n"
        )

        spec_idx = 0
        while True:
            stop_reason = should_stop()
            if stop_reason:
                console.print(f"[cyan]Stopping: {stop_reason}[/cyan]")
                break

            if spec_idx >= len(specs):
                if config.cycle_specs:
                    spec_idx = 0
                else:
                    console.print("[cyan]Stopping: all specs consumed (no-cycle mode).[/cyan]")
                    break

            spec = specs[spec_idx]
            title_display = spec.title or (spec.lyrics[:40] + "...")
            created = False

            for attempt in range(1, config.retries + 2):
                self.attempts += 1
                await self.nav.to_create()
                await self.modal.dismiss_all()
                await asyncio.sleep(1)

                result = await self.create.create_song(
                    lyrics=spec.lyrics,
                    styles=spec.styles,
                    title=spec.title,
                    weirdness=spec.weirdness,
                    style_influence=spec.style_influence,
                )

                log_entry = {
                    "ts": _utc_now(),
                    "started_at": started_at,
                    "event": "create_attempt",
                    "spec_index": spec_idx,
                    "attempt": attempt,
                    "title": spec.title,
                    "styles": spec.styles,
                    "success": result.success,
                    "message": result.message,
                }
                append_log(log_entry)

                if result.success:
                    self.successes += 1
                    created = True
                    console.print(
                        f"[green]Created[/green] #{self.successes} "
                        f"(spec {spec_idx + 1}, attempt {attempt}): {title_display}"
                    )
                    break

                console.print(
                    f"[red]Create failed[/red] (spec {spec_idx + 1}, attempt {attempt}): {result.message}"
                )

                if config.pause_on_captcha and "captcha" in result.message.lower():
                    pause_msg = (
                        f"CAPTCHA pause at spec {spec_idx + 1}, attempt {attempt}. "
                        f"Solve challenge in browser, then resume with: touch {config.resume_file}"
                    )
                    append_log(
                        {
                            "ts": _utc_now(),
                            "started_at": started_at,
                            "event": "captcha_pause",
                            "spec_index": spec_idx,
                            "attempt": attempt,
                            "message": pause_msg,
                        }
                    )
                    notify(pause_msg)

                    resume_path = Path(config.resume_file)
                    while True:
                        await asyncio.sleep(2)
                        if resume_path.exists():
                            try:
                                resume_path.unlink()
                            except OSError:
                                pass
                            append_log(
                                {
                                    "ts": _utc_now(),
                                    "started_at": started_at,
                                    "event": "captcha_resume",
                                    "spec_index": spec_idx,
                                    "attempt": attempt,
                                    "message": "manual resume signal received",
                                }
                            )
                            console.print("[green]Resume signal received. Retrying...[/green]")
                            break

                if attempt <= config.retries:
                    console.print(f"[dim]Retrying in {config.retry_wait}s...[/dim]")
                    await asyncio.sleep(config.retry_wait)

            if not created:
                self.failures += 1
                console.print(f"[yellow]Skipping spec {spec_idx + 1} after retries.[/yellow]")

            if created and config.wait_between > 0:
                console.print(f"[dim]Cooldown: {config.wait_between}s[/dim]")
                await asyncio.sleep(config.wait_between)

            spec_idx += 1

        self.show_summary()

    def show_summary(self):
        table = Table(title="Autonomous Create Summary")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="white")
        table.add_row("Attempts", str(self.attempts))
        table.add_row("Successes", str(self.successes))
        table.add_row("Failed Specs", str(self.failures))
        console.print(table)
