"""Attempt to solve hCaptcha by visual analysis + iframe clicks."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, CreateSkill


async def get_captcha_frame(page):
    """Find the hCaptcha challenge frame."""
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            return frame
    return None


async def screenshot_captcha(browser, name):
    """Take a screenshot and return path."""
    path = f"/tmp/suno_skills/{name}.png"
    await browser.screenshot(path)
    return path


async def click_grid_cell(page, iframe_x, iframe_y, row, col):
    """Click a cell in the 3x3 grid.

    Grid cells are 120x120px, starting at ~(10, 130) within the iframe.
    Row/col are 0-indexed.
    """
    # Cell positions within the iframe (from the grid analysis)
    # Top-left cell center: (70, 190), spacing ~130px
    cell_x = 70 + col * 130
    cell_y = 190 + row * 130

    # Convert to main page coordinates
    page_x = iframe_x + cell_x
    page_y = iframe_y + cell_y

    print(f"  Clicking grid ({row},{col}) -> page ({page_x},{page_y})")
    await page.mouse.click(page_x, page_y)
    await asyncio.sleep(0.8)


async def main():
    browser = BrowserController(headless=False, cdp_port=9222)
    ok = await browser.connect()
    if not ok:
        print("FAIL: Browser launch")
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    create = CreateSkill(browser)
    page = browser.page

    # Login
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)

    # Navigate and fill form
    await nav.to_create()
    await modal.dismiss_all()
    await asyncio.sleep(1)

    await create.switch_to_custom()
    await create._dismiss_modals()

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

    # Click Create to trigger CAPTCHA
    print("Clicking Create...")
    await create.click_button("Create")
    await asyncio.sleep(5)

    # Find the hCaptcha iframe position on the main page
    iframe_pos = await browser.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                const r = f.getBoundingClientRect();
                if (r.width > 100) {
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
        }
        return null;
    }""")

    if not iframe_pos:
        print("No visible hCaptcha iframe found - maybe no CAPTCHA this time?")
        await asyncio.sleep(10)
        await screenshot_captcha(browser, "no_captcha")
        await asyncio.sleep(60)
        await browser.close()
        return

    print(f"hCaptcha iframe at ({iframe_pos['x']},{iframe_pos['y']}) {iframe_pos['w']}x{iframe_pos['h']}")

    # Screenshot for visual analysis
    path = await screenshot_captcha(browser, "captcha_to_solve")
    print(f"Screenshot: {path}")

    # Get the challenge prompt from the frame
    captcha_frame = await get_captcha_frame(page)
    if captcha_frame:
        prompt = await captcha_frame.evaluate("""() => {
            const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
            return el ? el.textContent.trim() : 'unknown';
        }""")
        print(f"Challenge: {prompt}")
    else:
        print("Could not access captcha frame")
        prompt = "unknown"

    print(f"\n=== CAPTCHA visible at ({iframe_pos['x']},{iframe_pos['y']}) ===")
    print(f"Challenge: {prompt}")
    print("Taking screenshot for you to see...")
    print("Please solve the CAPTCHA in the browser window.")
    print("Waiting for you to solve it (up to 3 minutes)...\n")

    # Wait for user to solve
    solved = False
    for tick in range(36):  # 3 minutes
        await asyncio.sleep(5)

        # Check if hCaptcha iframe is still visible
        still_visible = await browser.evaluate("""() => {
            const iframes = document.querySelectorAll('iframe');
            for (const f of iframes) {
                if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                    const r = f.getBoundingClientRect();
                    return r.width > 100 && r.height > 100 && r.x > 0;
                }
            }
            return false;
        }""")

        if not still_visible:
            print(f"[{tick*5}s] CAPTCHA dismissed!")
            solved = True
            break

        if tick % 6 == 0 and tick > 0:
            print(f"[{tick*5}s] Still waiting for CAPTCHA solve...")

    if solved:
        await asyncio.sleep(2)

        # Re-click Create since the CAPTCHA consumed the original click
        print("Re-clicking Create button...")
        clicked = await create.click_button("Create")
        if clicked:
            print("Create clicked!")
        else:
            print("Create button not found via text, trying to find it...")
            btn = await browser.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    const t = b.textContent.trim();
                    const r = b.getBoundingClientRect();
                    if (t === 'Create' && r.width > 100 && r.height > 30) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
                return null;
            }""")
            if btn:
                await page.mouse.click(btn['x'], btn['y'])
                print(f"Clicked at ({btn['x']},{btn['y']})")

        await asyncio.sleep(5)

        # Check for another CAPTCHA
        another = await browser.evaluate("""() => {
            const iframes = document.querySelectorAll('iframe');
            for (const f of iframes) {
                if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                    const r = f.getBoundingClientRect();
                    return r.width > 100;
                }
            }
            return false;
        }""")

        if another:
            print("Another CAPTCHA appeared! Please solve it again...")
            # Wait again
            for tick2 in range(36):
                await asyncio.sleep(5)
                still = await browser.evaluate("""() => {
                    const iframes = document.querySelectorAll('iframe');
                    for (const f of iframes) {
                        if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                            const r = f.getBoundingClientRect();
                            return r.width > 100 && r.x > 0;
                        }
                    }
                    return false;
                }""")
                if not still:
                    print("Second CAPTCHA solved! Re-clicking Create...")
                    await asyncio.sleep(2)
                    await create.click_button("Create")
                    await asyncio.sleep(5)
                    break

        # Final check - is the song generating?
        await asyncio.sleep(10)
        await screenshot_captcha(browser, "final_result")

        still_form = await browser.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 200) return true;
            }
            return false;
        }""")

        if still_form:
            print("\nStill on create form. Song may not have been created.")
        else:
            print("\nSong generation started!")
    else:
        print("\nCAPTCHA timeout. Please try again.")

    # Keep open
    print("\nKeeping browser open for 60s...")
    await asyncio.sleep(60)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
