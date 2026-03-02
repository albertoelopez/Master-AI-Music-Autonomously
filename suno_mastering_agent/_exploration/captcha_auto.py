"""Automated CAPTCHA solver: fill form, save cell images, wait for clicks file, execute.

Flow:
1. Fill form, click Create, detect CAPTCHA
2. Save 9 cell images to /tmp/suno_skills/cell_R_C.png
3. Write state to /tmp/suno_skills/captcha_state.json
4. Poll for /tmp/suno_skills/clicks.json (created by the analyzer)
5. When found, click the specified cells and Verify
6. Handle additional CAPTCHA rounds
7. Re-click Create after CAPTCHA is solved
"""
import asyncio
import base64
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, CreateSkill

CLICKS_FILE = "/tmp/suno_skills/clicks.json"
STATE_FILE = "/tmp/suno_skills/captcha_state.json"

# Grid cell centers within the hCaptcha iframe (iframe-relative coords)
CELL_CENTERS = {
    (0, 0): (70, 190), (0, 1): (200, 190), (0, 2): (330, 190),
    (1, 0): (70, 320), (1, 1): (200, 320), (1, 2): (330, 320),
    (2, 0): (70, 450), (2, 1): (200, 450), (2, 2): (330, 450),
}
VERIFY_BTN = (360, 500)  # Bottom-right of CAPTCHA panel


def write_state(iframe_pos, prompt, status, round_num=1):
    state = {
        "iframe": iframe_pos,
        "prompt": prompt,
        "status": status,
        "round": round_num,
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


async def get_iframe_pos(browser):
    return await browser.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                const r = f.getBoundingClientRect();
                // Must be on-screen: width>100, y>-100 (not hidden at -9999), x>10
                if (r.width > 100 && r.y > -100 && r.x > 10) {
                    return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
                }
            }
        }
        return null;
    }""")


async def is_captcha_visible(browser):
    pos = await get_iframe_pos(browser)
    return pos is not None and pos.get('w', 0) > 100


async def get_captcha_frame(page):
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            return frame
    return None


async def get_prompt(frame):
    if not frame:
        return ""
    return await frame.evaluate("""() => {
        const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
        return el ? el.textContent.trim() : '';
    }""")


async def save_cell_images(page, frame, round_num):
    """Fetch and save individual cell images from the CAPTCHA grid."""
    if not frame:
        return []

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

    saved = []
    for i, url in enumerate(img_urls):
        row, col = divmod(i, 3)
        if not url:
            continue
        try:
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
                header, b64 = img_data.split(',', 1)
                cell_path = f"/tmp/suno_skills/cell_{row}_{col}.png"
                with open(cell_path, 'wb') as f:
                    f.write(base64.b64decode(b64))
                saved.append((row, col))
        except Exception as e:
            print(f"  Cell [{row},{col}] error: {e}")

    return saved


async def click_cells_and_verify(page, browser, iframe_pos, cells):
    """Click specified cells in the CAPTCHA grid and then click Verify."""
    ix, iy = iframe_pos['x'], iframe_pos['y']

    for r, c in cells:
        if (r, c) not in CELL_CENTERS:
            print(f"  Invalid cell ({r},{c})")
            continue
        cx, cy = CELL_CENTERS[(r, c)]
        px, py = ix + cx, iy + cy
        print(f"  Clicking [{r},{c}] at ({px},{py})")
        await page.mouse.click(px, py)
        await asyncio.sleep(0.8)

    await asyncio.sleep(1)

    # Try to find Verify/Submit button dynamically from the frame
    frame = await get_captcha_frame(page)
    verify_pos = None
    if frame:
        verify_pos = await frame.evaluate("""() => {
            // Look for the submit/verify button
            const btns = document.querySelectorAll('button, .button, [role=button]');
            for (const b of btns) {
                const text = b.textContent.trim().toLowerCase();
                if (text.includes('verify') || text.includes('submit') || text.includes('check') || text.includes('next')) {
                    const r = b.getBoundingClientRect();
                    if (r.width > 30 && r.height > 20) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
            }
            // Fallback: look for .button-submit class
            const submit = document.querySelector('.button-submit, [class*=submit], [class*=verify]');
            if (submit) {
                const r = submit.getBoundingClientRect();
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
            }
            return null;
        }""")

    if verify_pos:
        # Frame-relative coords need iframe offset
        vx, vy = ix + verify_pos['x'], iy + verify_pos['y']
        print(f"  Found Verify button at frame({verify_pos['x']},{verify_pos['y']}) -> page({vx},{vy})")
    else:
        # Fallback to hardcoded position
        vx, vy = ix + VERIFY_BTN[0], iy + VERIFY_BTN[1]
        print(f"  Using fallback Verify at ({vx},{vy})")

    await page.mouse.click(vx, vy)
    await asyncio.sleep(3)


async def solve_round(browser, page, round_num):
    """Handle one CAPTCHA round: save images, wait for clicks, execute."""
    iframe_pos = await get_iframe_pos(browser)
    if not iframe_pos:
        return True  # No CAPTCHA

    frame = await get_captcha_frame(page)
    prompt = await get_prompt(frame)

    print(f"\n=== CAPTCHA Round {round_num} ===")
    print(f"Challenge: {prompt}")
    print(f"Iframe: ({iframe_pos['x']},{iframe_pos['y']})")

    # Save screenshot
    await browser.screenshot(f"/tmp/suno_skills/captcha_round_{round_num}.png")

    # Save cell images
    saved = await save_cell_images(page, frame, round_num)
    print(f"Saved {len(saved)} cell images")

    # Write state
    write_state(iframe_pos, prompt, "waiting_for_clicks", round_num)

    # Remove old clicks file
    if os.path.exists(CLICKS_FILE):
        os.remove(CLICKS_FILE)

    print(f"\n>>> Waiting for {CLICKS_FILE}")
    print(f">>> Write JSON like: {{\"cells\": [[0,0], [1,1]]}}")

    # Poll for clicks file (up to 5 minutes)
    for tick in range(60):
        await asyncio.sleep(5)

        # Check if CAPTCHA went away (user solved manually)
        if not await is_captcha_visible(browser):
            print("CAPTCHA dismissed externally!")
            return True

        # Check for clicks file
        if os.path.exists(CLICKS_FILE):
            with open(CLICKS_FILE) as f:
                data = json.load(f)
            cells = [tuple(c) for c in data.get("cells", [])]
            print(f"\nGot clicks: {cells}")
            os.remove(CLICKS_FILE)

            # Refresh iframe position (may have shifted)
            iframe_pos = await get_iframe_pos(browser)
            if not iframe_pos:
                print("CAPTCHA gone before clicking!")
                return True

            await click_cells_and_verify(page, browser, iframe_pos, cells)

            # Check if solved - wait longer for transition
            await asyncio.sleep(4)
            if not await is_captcha_visible(browser):
                print("CAPTCHA solved!")
                write_state(iframe_pos, prompt, "solved", round_num)
                return True

            # Check if iframe moved off-screen (transition state)
            new_pos = await get_iframe_pos(browser)
            if new_pos and new_pos.get('y', 0) < -100:
                print("CAPTCHA transitioning (iframe off-screen)...")
                await asyncio.sleep(3)
                if not await is_captcha_visible(browser):
                    print("CAPTCHA solved after transition!")
                    write_state(iframe_pos, prompt, "solved", round_num)
                    return True

            print("CAPTCHA still visible - may be a new round...")
            write_state(iframe_pos, prompt, "new_round", round_num)
            return False  # Another round needed

        if tick % 6 == 0 and tick > 0:
            print(f"  [{tick*5}s] Still waiting for clicks...")

    print("Timeout waiting for clicks!")
    return False


async def main():
    os.makedirs("/tmp/suno_skills", exist_ok=True)

    # Clean up old files
    for f in ["clicks.json", "captcha_state.json"]:
        p = f"/tmp/suno_skills/{f}"
        if os.path.exists(p):
            os.remove(p)

    browser = BrowserController(headless=False, cdp_port=9222)
    ok = await browser.connect()
    if not ok:
        print("FAIL: Browser launch")
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    create = CreateSkill(browser)
    page = browser.page

    # Navigate to Create
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

    # Solve CAPTCHA (up to 5 rounds)
    for round_num in range(1, 6):
        solved = await solve_round(browser, page, round_num)
        if solved:
            break
        # If not solved, it's a new round - loop again
        await asyncio.sleep(2)

    # CAPTCHA solved — do NOT re-click Create!
    # hCaptcha's callback should automatically trigger Suno's form submission.
    # Just wait and check if the song starts generating.
    print("\n=== CAPTCHA solved. Waiting for Suno to process... ===")
    await asyncio.sleep(8)

    # Check if song generation started (page navigates or form disappears)
    for check in range(30):  # Up to 60 seconds
        await asyncio.sleep(2)

        # Check if we left the create page
        current_url = page.url
        if "/create" not in current_url:
            print(f"\nNavigated away to: {current_url}")
            print("Song generation started!")
            break

        # Check if Create button is gone or loading
        form_state = await browser.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                const text = b.textContent.trim();
                const r = b.getBoundingClientRect();
                if (text === 'Create' && r.width > 200) return 'form_ready';
                if ((text.includes('Creating') || text.includes('Loading')) && r.width > 200) return 'creating';
            }
            // Check for any hcaptcha still visible
            const iframes = document.querySelectorAll('iframe');
            for (const f of iframes) {
                if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                    const r = f.getBoundingClientRect();
                    if (r.width > 100 && r.y > -100 && r.x > 10) return 'captcha_visible';
                }
            }
            return 'unknown';
        }""")

        if form_state == 'creating':
            print("\nSong is being created!")
            break
        elif form_state == 'captcha_visible':
            print("\nAnother CAPTCHA appeared after solve. Solving...")
            for round_num in range(6, 11):
                solved = await solve_round(browser, page, round_num)
                if solved:
                    break
                await asyncio.sleep(2)
            # After this solve, wait again (don't re-click)
            await asyncio.sleep(5)
            continue
        elif form_state == 'form_ready' and check > 5:
            # Form is still there after 10+ seconds - the callback didn't fire
            # Try clicking Create once as last resort
            print("\nForm still ready after 10s - callback may not have fired.")
            print("Clicking Create as last resort...")
            await create.click_button("Create")
            await asyncio.sleep(5)
            # If another CAPTCHA appears, solve it
            if await is_captcha_visible(browser):
                print("CAPTCHA after last-resort click. Solving...")
                for round_num in range(11, 16):
                    solved = await solve_round(browser, page, round_num)
                    if solved:
                        break
                    await asyncio.sleep(2)
                await asyncio.sleep(5)
            break

        if check % 5 == 0 and check > 0:
            print(f"  [{check*2}s] State: {form_state}")

    # Final screenshot
    await asyncio.sleep(3)
    await browser.screenshot("/tmp/suno_skills/final_result.png")

    # Check final state
    still_form = await browser.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 200) return true;
        }
        return false;
    }""")

    if still_form:
        print("\nStill on form - song not yet created")
    else:
        print("\nSong generation likely started!")

    print("\nBrowser staying open for 2 minutes...")
    await asyncio.sleep(120)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
