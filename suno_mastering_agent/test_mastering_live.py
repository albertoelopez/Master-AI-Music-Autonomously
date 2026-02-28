#!/usr/bin/env python3
"""Live test: master track 1 with 'vocal_focus' profile."""
import asyncio
import os
from src.browser import BrowserController
from src.agents.mastering import MasteringAgent

# Remove stale lock
lock = os.path.join(os.path.dirname(__file__), "browser_data", "SingletonLock")
if os.path.exists(lock):
    os.remove(lock)

OUTPUT = "/tmp/suno_master_test"
os.makedirs(OUTPUT, exist_ok=True)


async def main():
    browser = BrowserController()
    agent = MasteringAgent(browser)

    try:
        # Initialize - navigates to Studio
        if not await browser.connect():
            return

        from src.skills import NavigateSkill, ModalSkill
        nav = NavigateSkill(browser)
        modal = ModalSkill(browser)

        await nav.to_studio()
        await asyncio.sleep(6)
        await modal.dismiss_all()

        await browser.screenshot(os.path.join(OUTPUT, "00_studio.png"))

        # Master track 1 with vocal_focus
        result = await agent.master_track(0, "vocal_focus")
        await browser.screenshot(os.path.join(OUTPUT, "01_after_vocal_focus.png"))
        print(f"\nResult: {result}")

        # Now try radio_ready on track 2
        result2 = await agent.master_track(1, "radio_ready")
        await browser.screenshot(os.path.join(OUTPUT, "02_after_radio_ready.png"))
        print(f"\nResult: {result2}")

        # Show summary
        agent.show_summary()

        # Read back EQ state
        from src.skills import EQSkill
        eq = EQSkill(browser)
        state = await eq.get_current_state()
        print(f"\nFinal EQ state: {state.data}")

        await browser.screenshot(os.path.join(OUTPUT, "03_final.png"))

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        await browser.screenshot(os.path.join(OUTPUT, "error.png"))
    finally:
        await browser.close()


asyncio.run(main())
