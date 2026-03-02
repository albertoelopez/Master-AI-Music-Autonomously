"""Create a song on Suno - attempt to solve CAPTCHA visually."""
import asyncio
import sys
import os
import json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, CreateSkill


async def screenshot_and_dump(browser, name):
    """Take screenshot and dump CAPTCHA frame info."""
    path = f"/tmp/suno_skills/{name}.png"
    await browser.screenshot(path)
    print(f"Screenshot: {path}")

    # Check for iframes (CAPTCHAs are often in iframes)
    frames = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('iframe').forEach(f => {
            const r = f.getBoundingClientRect();
            results.push({
                src: (f.src || '').substring(0, 100),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
                visible: r.width > 0 && r.height > 0
            });
        });
        return results;
    }""") or []

    if frames:
        print(f"Iframes found ({len(frames)}):")
        for f in frames:
            print(f"  [{f['x']},{f['y']}] {f['w']}x{f['h']} visible={f['visible']} src={f['src']}")

    return path


async def main():
    browser = BrowserController(headless=False, cdp_port=9222)
    ok = await browser.connect()
    if not ok:
        print("FAIL: Browser launch")
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    create = CreateSkill(browser)

    # Login check
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)
    r = await nav.is_logged_in()
    print(f"Login: {r.success}")

    # Navigate to Create
    await nav.to_create()
    await modal.dismiss_all()
    await asyncio.sleep(1)

    # Switch to Custom and fill form
    await create.switch_to_custom()
    await create._dismiss_modals()
    await asyncio.sleep(0.5)

    await create.set_lyrics("""[Verse 1]
Neon lights flicker on the midnight train
Strangers passing shadows through the windowpane
City hums a melody that no one wrote
Carried on the wind like a half-remembered note

[Chorus]
We are the signal in the noise
We are the quiet steady voice
Through the static we will rise
Dancing underneath electric skies

[Verse 2]
Every screen a window to a thousand lives
Binary heartbeats keeping time
The future whispers from a satellite above
Sending down a frequency of love

[Chorus]
We are the signal in the noise
We are the quiet steady voice
Through the static we will rise
Dancing underneath electric skies

[Bridge]
Turn the dial up, let it glow
Every wavelength has a soul
In the echo, find your own
You were never meant to walk alone

[Outro]
Signal in the noise
Signal in the noise""")
    await create._dismiss_modals()

    await create.set_styles("synthwave, electronic pop, dreamy, retro-futuristic, 80s inspired")
    await create._dismiss_modals()

    await create.set_title("Signal in the Noise")
    await create._dismiss_modals()

    print("\nForm filled. Taking pre-click screenshot...")
    await screenshot_and_dump(browser, "pre_create")

    # Click Create
    print("\nClicking Create...")
    await create.click_button("Create")
    await asyncio.sleep(5)

    # Screenshot immediately to see what appeared
    print("\nPost-click screenshot:")
    await screenshot_and_dump(browser, "post_create")

    # Check all frames for CAPTCHA content
    page = browser.page
    all_frames = page.frames
    print(f"\nPlaywright frames: {len(all_frames)}")
    for i, frame in enumerate(all_frames):
        url = frame.url
        print(f"  Frame {i}: {url[:120]}")

    # Keep alive so we can inspect
    print("\n=== Browser staying open. Check screenshots. ===")
    print("Keeping alive for 5 minutes for manual inspection...")

    # Poll for CAPTCHA every 5s and screenshot
    for tick in range(60):
        await asyncio.sleep(5)
        # Check if Create form is still showing
        still_form = await browser.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 200) return true;
            }
            return false;
        }""")
        if not still_form:
            print(f"\n[tick {tick}] Create form gone - song may be generating!")
            await browser.screenshot(f"/tmp/suno_skills/generating_{tick}.png")
            break
        if tick % 6 == 0:  # Every 30s
            await browser.screenshot(f"/tmp/suno_skills/waiting_{tick}.png")
            print(f"[tick {tick}] Still on form... screenshot saved")

    await asyncio.sleep(30)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
