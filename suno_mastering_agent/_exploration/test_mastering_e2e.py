#!/usr/bin/env python3
"""End-to-end mastering test - master a track with radio_ready profile."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.agents.mastering import MasteringAgent
from src.skills import NavigateSkill, ModalSkill, StudioSkill
from rich.console import Console

console = Console()


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    studio = StudioSkill(browser)

    os.makedirs("/tmp/suno_skills", exist_ok=True)

    # Navigate to Studio
    await nav.to_studio()
    await asyncio.sleep(3)
    await modal.dismiss_all()

    # Check for tracks - drag one if empty
    r = await studio.get_track_count()
    console.print(f"Track count: {r.data}")

    if r.data == 0:
        console.print("Dragging clip to timeline...")
        await studio.drag_clip_to_timeline(0)
        await asyncio.sleep(3)

    # Screenshot before mastering
    await browser.screenshot("/tmp/suno_skills/master_01_before.png")

    # Run mastering agent
    console.print("\n[bold]Running MasteringAgent.master_track(0, 'radio_ready')...[/bold]")
    agent = MasteringAgent(browser)
    r = await agent.master_track(0, "radio_ready")
    console.print(f"Result: {r.success} - {r.message}")

    # Screenshot after mastering
    await browser.screenshot("/tmp/suno_skills/master_02_after.png")

    # Show summary
    agent.show_summary()

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
