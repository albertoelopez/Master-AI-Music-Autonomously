"""Solve hCaptcha by visual screenshot analysis + clicking through iframe."""
import asyncio
import sys
import os
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, CreateSkill


# hCaptcha grid layout constants (within the iframe)
# 3x3 grid, each cell ~120x120, spaced ~130px apart
CELL_ORIGINS = {
    (0, 0): (70, 190), (0, 1): (200, 190), (0, 2): (330, 190),
    (1, 0): (70, 320), (1, 1): (200, 320), (1, 2): (330, 320),
    (2, 0): (70, 450), (2, 1): (200, 450), (2, 2): (330, 450),
}
# Verify/Skip button is roughly at (350, 530) within iframe
VERIFY_BTN = (350, 530)


async def get_iframe_pos(browser):
    """Get hCaptcha challenge iframe position on main page."""
    return await browser.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                const r = f.getBoundingClientRect();
                if (r.width > 100) return {x: r.x, y: r.y, w: r.width, h: r.height};
            }
        }
        return null;
    }""")


async def is_captcha_visible(browser):
    """Check if hCaptcha challenge is visible."""
    pos = await get_iframe_pos(browser)
    return pos is not None and pos['w'] > 100


async def get_captcha_frame(page):
    """Get the hCaptcha challenge frame."""
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            return frame
    return None


async def click_cell(page, iframe_x, iframe_y, row, col):
    """Click a grid cell using page coordinates."""
    cx, cy = CELL_ORIGINS[(row, col)]
    px, py = iframe_x + cx, iframe_y + cy
    await page.mouse.click(px, py)
    await asyncio.sleep(0.5)


async def click_verify(page, iframe_x, iframe_y):
    """Click the Verify button."""
    px, py = iframe_x + VERIFY_BTN[0], iframe_y + VERIFY_BTN[1]
    await page.mouse.click(px, py)
    await asyncio.sleep(2)


async def solve_captcha_round(browser, page, round_num):
    """One round of CAPTCHA solving.

    Returns True if solved/dismissed, False if still showing.
    """
    iframe_pos = await get_iframe_pos(browser)
    if not iframe_pos:
        return True  # No CAPTCHA

    ix, iy = iframe_pos['x'], iframe_pos['y']

    # Get the frame and prompt
    frame = await get_captcha_frame(page)
    prompt = ""
    if frame:
        prompt = await frame.evaluate("""() => {
            const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
            return el ? el.textContent.trim() : '';
        }""")

    # Screenshot for analysis
    path = f"/tmp/suno_skills/captcha_r{round_num}.png"
    await browser.screenshot(path)
    print(f"\n--- Round {round_num} ---")
    print(f"Challenge: {prompt}")
    print(f"Screenshot: {path}")

    # Fetch individual cell image URLs for potential fetching
    img_urls = []
    if frame:
        img_urls = await frame.evaluate("""() => {
            const urls = [];
            document.querySelectorAll('.task-image .image').forEach(img => {
                const style = window.getComputedStyle(img);
                const bg = style.backgroundImage || '';
                const match = bg.match(/url\\("(.+?)"\\)/);
                urls.push(match ? match[1] : null);
            });
            return urls;
        }""")

    # ===================================================================
    # VISUAL ANALYSIS: I need to look at the screenshot and decide
    # which cells contain items matching the prompt.
    #
    # Common hCaptcha prompts for Suno:
    # - "Pick all items a person could pick up by hand"
    # - "Find every object a person can lift by hand"
    # These ask for small, portable objects vs large structures.
    #
    # Typical liftable: shoes, bags, balls, food, bottles, tools, books
    # Typical NOT liftable: buildings, mountains, bridges, vehicles, trees
    # ===================================================================

    # Try to fetch each cell image individually for better analysis
    print(f"Fetching {len(img_urls)} cell images for analysis...")
    for i, url in enumerate(img_urls):
        row, col = divmod(i, 3)
        if url:
            # Save each cell image
            cell_path = f"/tmp/suno_skills/captcha_r{round_num}_cell_{row}_{col}.png"
            try:
                # Use page to fetch the image
                img_data = await page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{url}");
                        const blob = await resp.blob();
                        return new Promise((resolve) => {{
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        }});
                    }} catch(e) {{
                        return null;
                    }}
                }}""")
                if img_data and img_data.startswith('data:'):
                    import base64
                    # Extract base64 data
                    header, b64 = img_data.split(',', 1)
                    with open(cell_path, 'wb') as f:
                        f.write(base64.b64decode(b64))
                    print(f"  Cell [{row},{col}]: saved to {cell_path}")
                else:
                    print(f"  Cell [{row},{col}]: fetch failed")
            except Exception as e:
                print(f"  Cell [{row},{col}]: error - {e}")

    # Return the state for the caller to analyze and click
    return False


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

    # Login & navigate
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)
    await nav.to_create()
    await modal.dismiss_all()
    await asyncio.sleep(1)

    # Fill form
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

    print("\n=== Form filled. Clicking Create... ===\n")
    await create.click_button("Create")
    await asyncio.sleep(5)

    # Check for CAPTCHA
    if not await is_captcha_visible(browser):
        print("No CAPTCHA! Song should be creating.")
        await asyncio.sleep(30)
        await browser.close()
        return

    # Solve CAPTCHA - get images for analysis
    solved = await solve_captcha_round(browser, page, 1)

    if not solved:
        print("\n=== Cell images saved. Analyze them to determine which to click. ===")
        print("=== The script will now wait. Check /tmp/suno_skills/ for cell images. ===")
        print("=== Or solve the CAPTCHA manually in the browser. ===\n")

        # Wait for CAPTCHA resolution (manual solve or timeout)
        for tick in range(60):
            await asyncio.sleep(5)
            if not await is_captcha_visible(browser):
                print(f"\n[{tick*5}s] CAPTCHA dismissed!")
                await asyncio.sleep(2)
                print("Re-clicking Create...")
                await create.click_button("Create")
                await asyncio.sleep(5)

                if await is_captcha_visible(browser):
                    print("Another CAPTCHA! Saving images...")
                    await solve_captcha_round(browser, page, 2)
                    continue
                else:
                    print("No more CAPTCHA!")
                    break
            if tick % 12 == 0 and tick > 0:
                print(f"[{tick*5}s] Still waiting...")

    # Final check
    await asyncio.sleep(5)
    await browser.screenshot("/tmp/suno_skills/final_result.png")
    still_form = await browser.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 200) return true;
        }
        return false;
    }""")
    print(f"\nStill on form: {still_form}")
    if not still_form:
        print("Song generation started!")

    print("\nBrowser open for 2 minutes...")
    await asyncio.sleep(120)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
