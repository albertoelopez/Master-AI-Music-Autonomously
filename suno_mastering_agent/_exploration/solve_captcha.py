"""Attempt to interact with hCaptcha in the Suno Create page."""
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

    # Login check
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)
    r = await nav.is_logged_in()
    print(f"Login: {r.success}")

    # Navigate to Create and fill form
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

    print("Form filled. Clicking Create...")
    await create.click_button("Create")
    await asyncio.sleep(4)

    # Take a full-page screenshot to see the CAPTCHA clearly
    await browser.screenshot("/tmp/suno_skills/captcha_challenge.png")
    print("CAPTCHA screenshot saved")

    # Find the hCaptcha challenge frame
    page = browser.page
    captcha_frame = None
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            captcha_frame = frame
            break

    if not captcha_frame:
        print("No hCaptcha challenge frame found!")
        # Check if maybe no CAPTCHA appeared
        await asyncio.sleep(60)
        await browser.close()
        return

    print(f"Found hCaptcha frame: {captcha_frame.url[:100]}")

    # Get the challenge prompt text
    prompt_text = await captcha_frame.evaluate("""() => {
        const prompt = document.querySelector('.prompt-text, h2, [class*=prompt]');
        return prompt ? prompt.textContent.trim() : null;
    }""")
    print(f"Challenge prompt: {prompt_text}")

    # Get info about the image grid
    grid_info = await captcha_frame.evaluate("""() => {
        const cells = document.querySelectorAll('.task-image, [class*=task], [role=button]');
        const results = [];
        cells.forEach((cell, i) => {
            const r = cell.getBoundingClientRect();
            const img = cell.querySelector('img');
            results.push({
                index: i,
                x: Math.round(r.x + r.width/2),
                y: Math.round(r.y + r.height/2),
                w: Math.round(r.width),
                h: Math.round(r.height),
                imgSrc: img ? img.src.substring(0, 80) : null
            });
        });
        return results;
    }""")

    print(f"\nGrid cells found: {len(grid_info)}")
    for cell in grid_info:
        print(f"  Cell {cell['index']}: [{cell['x']},{cell['y']}] {cell['w']}x{cell['h']} img={cell.get('imgSrc', 'none')}")

    # Take a screenshot of just the captcha area for better analysis
    # The iframe is at (441,151) 400x600 on the main page
    # Save each cell image if possible
    print("\nScreenshotting individual cells from the captcha frame...")

    # Take a full screenshot for visual analysis
    await browser.screenshot("/tmp/suno_skills/captcha_full.png")

    print("\n=== CAPTCHA ANALYSIS ===")
    print(f"Prompt: {prompt_text}")
    print(f"Grid: {len(grid_info)} cells")
    print("\nPlease solve the CAPTCHA in the browser window.")
    print("Waiting up to 3 minutes...")

    # Wait for user to solve, then re-click Create
    for i in range(36):  # 36 * 5s = 3 minutes
        await asyncio.sleep(5)
        # Check if captcha is gone
        still_captcha = False
        for frame in page.frames:
            if "hcaptcha" in frame.url and "challenge" in frame.url:
                fr_visible = await browser.evaluate("""() => {
                    const iframes = document.querySelectorAll('iframe');
                    for (const f of iframes) {
                        if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                            const r = f.getBoundingClientRect();
                            return r.width > 100 && r.height > 100;
                        }
                    }
                    return false;
                }""")
                still_captcha = fr_visible
                break

        if not still_captcha:
            print(f"\n[{i*5}s] CAPTCHA gone! Re-clicking Create...")
            await asyncio.sleep(1)
            clicked = await create.click_button("Create")
            if clicked:
                print("Create re-clicked!")
            else:
                print("Create button not found, trying coordinate click...")
                # Find Create button position
                btn_pos = await browser.evaluate("""() => {
                    const btns = document.querySelectorAll('button');
                    for (const b of btns) {
                        if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 100) {
                            const r = b.getBoundingClientRect();
                            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                        }
                    }
                    return null;
                }""")
                if btn_pos:
                    await page.mouse.click(btn_pos['x'], btn_pos['y'])
                    print(f"Clicked Create at ({btn_pos['x']}, {btn_pos['y']})")

            await asyncio.sleep(5)

            # Check if another CAPTCHA appeared
            await browser.screenshot("/tmp/suno_skills/after_reclick.png")
            print("Post-reclick screenshot saved")

            # Wait to see if song starts generating
            await asyncio.sleep(15)
            still_form = await browser.evaluate("""() => {
                const btns = document.querySelectorAll('button');
                for (const b of btns) {
                    if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 200) return true;
                }
                return false;
            }""")
            if still_form:
                print("Still on create form - may need another CAPTCHA solve")
                await browser.screenshot("/tmp/suno_skills/still_form.png")
            else:
                print("SUCCESS - Song generation started!")
                await browser.screenshot("/tmp/suno_skills/song_generating.png")

            break

    # Keep alive for verification
    print("\nKeeping browser open for 60s...")
    await asyncio.sleep(60)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
