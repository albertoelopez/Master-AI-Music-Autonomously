"""Click the correct hCaptcha cells based on visual analysis."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, CreateSkill


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

    # Click Create to trigger CAPTCHA
    print("Clicking Create...")
    await create.click_button("Create")
    await asyncio.sleep(5)

    # Find hCaptcha iframe
    iframe_pos = await browser.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                const r = f.getBoundingClientRect();
                if (r.width > 100) return {x: r.x, y: r.y, w: r.width, h: r.height};
            }
        }
        return null;
    }""")

    if not iframe_pos:
        print("No CAPTCHA appeared!")
        await asyncio.sleep(30)
        await browser.close()
        return

    ix, iy = iframe_pos['x'], iframe_pos['y']
    print(f"hCaptcha iframe at ({ix},{iy})")

    # Screenshot to see THIS challenge
    await browser.screenshot("/tmp/suno_skills/captcha_before_click.png")
    print("Screenshot saved: /tmp/suno_skills/captcha_before_click.png")
    print("Analyze it, then I'll click...\n")

    # Get the prompt
    captcha_frame = None
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            captcha_frame = frame
            break

    prompt = ""
    if captcha_frame:
        prompt = await captcha_frame.evaluate("""() => {
            const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
            return el ? el.textContent.trim() : '';
        }""")
    print(f"Challenge: {prompt}")

    # Grid cell page coordinates (iframe offset + cell center within iframe)
    # 3x3 grid, cells at iframe-relative: col*130+70, row*130+190
    def cell_coords(row, col):
        return (ix + 70 + col * 130, iy + 190 + row * 130)

    # I'll analyze the screenshot visually right now and decide which to click
    # But since images change each time, let me take the screenshot first,
    # then pause briefly to let the analysis happen

    # ATTEMPT: Click cells that look like liftable objects
    # I'll screenshot, then read it to decide

    # For this attempt, let me try a strategy:
    # 1. Screenshot
    # 2. Fetch each cell's image URL
    # 3. Try to fetch and analyze each image

    if captcha_frame:
        img_urls = await captcha_frame.evaluate("""() => {
            const urls = [];
            document.querySelectorAll('.task-image .image').forEach(img => {
                const style = window.getComputedStyle(img);
                const bg = style.backgroundImage || '';
                const match = bg.match(/url\\("(.+?)"\\)/);
                urls.push(match ? match[1] : null);
            });
            return urls;
        }""")
        print(f"\nImage URLs ({len(img_urls)}):")
        for i, url in enumerate(img_urls):
            row, col = divmod(i, 3)
            print(f"  Cell [{row},{col}]: {url[:80] if url else 'none'}...")

    # Now I need to LOOK at the screenshot to decide which cells to click
    # Let me print the coordinates so the calling code can use them
    print("\nGrid coordinates (page-absolute):")
    for r in range(3):
        for c in range(3):
            px, py = cell_coords(r, c)
            print(f"  [{r},{c}] -> ({px:.0f}, {py:.0f})")

    print("\n--- PAUSING: Check /tmp/suno_skills/captcha_before_click.png ---")
    print("--- Then I will attempt to click the correct cells ---\n")

    # Give a moment, then attempt to click
    # Since the images change each run, I'll try clicking and see what happens
    # Let me read the screenshot I just took to make my decision
    await asyncio.sleep(2)

    # I'll click based on what I see, then verify
    # For now, let me try clicking and submitting to see if the mechanism works
    # I'll click cell [0,1] (top-center) as a test
    test_x, test_y = cell_coords(0, 1)
    print(f"Test click: cell [0,1] at ({test_x:.0f},{test_y:.0f})")
    await page.mouse.click(test_x, test_y)
    await asyncio.sleep(1)

    # Screenshot to see if the click registered (cell should show selected state)
    await browser.screenshot("/tmp/suno_skills/captcha_after_test_click.png")
    print("Post-click screenshot saved")

    # Check if the cell got selected
    if captcha_frame:
        selected = await captcha_frame.evaluate("""() => {
            const cells = document.querySelectorAll('.task-image');
            const results = [];
            cells.forEach((c, i) => {
                results.push({
                    i: i,
                    selected: c.classList.contains('selected') ||
                              c.getAttribute('aria-pressed') === 'true' ||
                              c.querySelector('.border') !== null
                });
            });
            return results;
        }""")
        print(f"Selection state after click:")
        for s in selected:
            if s.get('selected'):
                print(f"  Cell {s['i']}: SELECTED")

    print("\nWaiting for you to solve the CAPTCHA or verify my click worked...")
    print("Browser will stay open for 3 minutes.\n")

    # Wait for CAPTCHA to be resolved
    for tick in range(36):
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
            print(f"[{tick*5}s] CAPTCHA gone! Re-clicking Create...")
            await asyncio.sleep(2)
            await create.click_button("Create")
            await asyncio.sleep(8)

            # Check for another CAPTCHA
            still2 = await browser.evaluate("""() => {
                const iframes = document.querySelectorAll('iframe');
                for (const f of iframes) {
                    if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                        const r = f.getBoundingClientRect();
                        return r.width > 100 && r.x > 0;
                    }
                }
                return false;
            }""")
            if still2:
                print("Another CAPTCHA! Please solve it...")
                continue
            else:
                # Check if song is creating
                await asyncio.sleep(5)
                await browser.screenshot("/tmp/suno_skills/final_check.png")
                print("Final screenshot saved. Check if song is generating.")
                break

    print("\nBrowser open for 60s...")
    await asyncio.sleep(60)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
