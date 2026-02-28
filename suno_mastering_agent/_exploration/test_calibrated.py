#!/usr/bin/env python3
"""Test all calibrated skill positions against live Suno Studio."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, StudioSkill, EQSkill, MixingSkill
from rich.console import Console
from rich.table import Table

console = Console()
results = []


def log(test_name, success, message=""):
    results.append((test_name, success, message))
    icon = "[green]PASS[/green]" if success else "[red]FAIL[/red]"
    console.print(f"  {icon} {test_name}: {message}")


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    studio = StudioSkill(browser)
    eq = EQSkill(browser)
    mixing = MixingSkill(browser)

    os.makedirs("/tmp/suno_skills", exist_ok=True)

    # 1. Navigate to Studio
    console.print("\n[bold]1. Navigation[/bold]")
    r = await nav.to_studio()
    log("Navigate to Studio", r.success, r.message)
    await asyncio.sleep(3)

    # 2. Dismiss modals
    r = await modal.dismiss_all()
    log("Dismiss modals", r.success, r.message)

    # 3. Check if timeline has clips - if not, drag one
    console.print("\n[bold]2. Timeline Setup[/bold]")
    r = await studio.get_track_count()
    log("Get track count", r.success, f"count={r.data}")

    if r.data == 0:
        console.print("  Timeline empty, dragging clip from sidebar...")
        r = await studio.drag_clip_to_timeline(0)
        log("Drag clip to timeline", r.success, r.message)
        await asyncio.sleep(3)

        # Re-check track count
        r = await studio.get_track_count()
        log("Track count after drag", r.success, f"count={r.data}")

    # 4. Select clip
    console.print("\n[bold]3. Clip Selection[/bold]")
    r = await studio.select_clip(0)
    log("Select clip (track 1)", r.success, r.message)
    await browser.screenshot("/tmp/suno_skills/test_01_clip_selected.png")

    # 5. Switch to Track tab
    console.print("\n[bold]4. Track Tab / EQ[/bold]")
    r = await studio.switch_to_track_tab()
    log("Switch to Track tab", r.success, r.message)
    await browser.screenshot("/tmp/suno_skills/test_02_track_tab.png")

    # 6. Enable EQ
    r = await eq.enable()
    log("Enable EQ", r.success, r.message)

    # 7. Read current preset
    preset = await eq._get_current_preset()
    log("Read preset", preset is not None, f"preset='{preset}'")

    # 8. Set preset to Warm
    r = await eq.set_preset("Warm")
    log("Set preset Warm", r.success, r.message)
    await browser.screenshot("/tmp/suno_skills/test_03_eq_warm.png")

    # Verify preset changed
    preset = await eq._get_current_preset()
    log("Verify Warm preset", preset is not None and "Warm" in (preset or ""), f"preset='{preset}'")

    # 9. Set back to Flat
    r = await eq.set_preset("Flat (Reset)")
    log("Reset to Flat", r.success, r.message)

    # 10. Set a specific band
    r = await eq.set_band(3, freq="500Hz", gain="2.0dB")
    log("Set band 3", r.success, r.message)

    # 11. Read EQ state
    r = await eq.get_current_state()
    log("Read EQ state", r.success and r.data is not None, f"bands={len(r.data or {})}")
    if r.data:
        for band_num, vals in r.data.items():
            console.print(f"    Band {band_num}: {vals}")

    # 12. Track info
    console.print("\n[bold]5. Mixing[/bold]")
    r = await mixing.get_track_info()
    log("Get track info", r.success, f"tracks={r.data}")

    # 13. Export button
    console.print("\n[bold]6. Export[/bold]")
    # Don't actually export, just test if the button is found
    export_found = await browser.evaluate("""() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            if (btn.textContent.trim().includes('Export')) {
                const r = btn.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), text: btn.textContent.trim()};
            }
        }
        return null;
    }""")
    log("Export button found", export_found is not None, f"pos={export_found}")

    # 14. Switch back to Clip tab
    r = await studio.switch_to_clip_tab()
    log("Switch to Clip tab", r.success, r.message)

    # Take final screenshot
    await browser.screenshot("/tmp/suno_skills/test_04_final.png")

    # Summary
    console.print("\n")
    table = Table(title="Calibration Test Results")
    table.add_column("Test", style="cyan")
    table.add_column("Result", style="bold")
    table.add_column("Details")

    passed = 0
    for name, success, msg in results:
        status = "[green]PASS[/green]" if success else "[red]FAIL[/red]"
        table.add_row(name, status, msg[:60])
        if success:
            passed += 1

    console.print(table)
    console.print(f"\n[bold]{passed}/{len(results)} tests passed[/bold]")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
