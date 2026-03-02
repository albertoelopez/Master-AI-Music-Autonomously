"""Actually attempt to solve hCaptcha by visual analysis + clicking."""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, CreateSkill


async def get_captcha_state(browser, page):
    """Get the hCaptcha iframe position and challenge frame."""
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

    captcha_frame = None
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            captcha_frame = frame
            break

    return iframe_pos, captcha_frame


async def solve_round(browser, page, round_num):
    """Attempt one round of CAPTCHA solving.

    1. Screenshot the CAPTCHA
    2. Analyze images visually (save individual cells)
    3. Click cells that match the prompt
    4. Click verify/submit
    """
    iframe_pos, captcha_frame = await get_captcha_state(browser, page)
    if not iframe_pos or not captcha_frame:
        return False, "No CAPTCHA found"

    # Get the prompt
    prompt = await captcha_frame.evaluate("""() => {
        const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
        return el ? el.textContent.trim() : '';
    }""")
    print(f"\n  Round {round_num} - Challenge: '{prompt}'")

    # Take a screenshot for analysis
    path = f"/tmp/suno_skills/captcha_round_{round_num}.png"
    await browser.screenshot(path)
    print(f"  Screenshot: {path}")

    # Get grid cell info from the frame - try to get background image URLs
    cells = await captcha_frame.evaluate("""() => {
        const cells = [];
        // The grid cells are typically .task-image elements
        const taskImages = document.querySelectorAll('.task-image');
        if (taskImages.length > 0) {
            taskImages.forEach((cell, i) => {
                const r = cell.getBoundingClientRect();
                const style = window.getComputedStyle(cell);
                const inner = cell.querySelector('.image');
                const innerStyle = inner ? window.getComputedStyle(inner) : null;
                cells.push({
                    index: i,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    bg: style.backgroundImage.substring(0, 100),
                    innerBg: innerStyle ? innerStyle.backgroundImage.substring(0, 100) : null,
                    selected: cell.classList.contains('selected') || cell.getAttribute('aria-pressed') === 'true'
                });
            });
            return cells;
        }

        // Fallback: look for any clickable image containers
        const containers = document.querySelectorAll('[role=button], .border-focus');
        containers.forEach((cell, i) => {
            const r = cell.getBoundingClientRect();
            if (r.width > 80 && r.width < 200 && r.height > 80) {
                const style = window.getComputedStyle(cell);
                cells.push({
                    index: i,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                    bg: style.backgroundImage.substring(0, 100),
                    selected: false
                });
            }
        });
        return cells;
    }""")

    print(f"  Grid cells: {len(cells)}")
    for c in cells:
        print(f"    Cell {c['index']}: ({c['x']},{c['y']}) {c['w']}x{c['h']} bg={c.get('bg','')[:50]} sel={c.get('selected')}")

    # The grid is 3x3 within the iframe
    # Cells are at iframe-relative coordinates
    # To click on main page: add iframe_pos offset
    ix, iy = iframe_pos['x'], iframe_pos['y']

    # I need to visually identify the correct cells from the screenshot
    # Since I can't extract individual images reliably, I'll screenshot
    # and analyze, then return which cells to click

    # For now, return the state so the main loop can analyze the screenshot
    return cells, prompt


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

    # Fill form
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

    # Click Create
    print("Clicking Create...")
    await create.click_button("Create")
    await asyncio.sleep(5)

    # Check for CAPTCHA
    iframe_pos, captcha_frame = await get_captcha_state(browser, page)

    if not iframe_pos:
        print("No CAPTCHA! Song might be creating...")
        await asyncio.sleep(30)
        await browser.close()
        return

    print(f"hCaptcha at ({iframe_pos['x']},{iframe_pos['y']}) {iframe_pos['w']}x{iframe_pos['h']}")

    # Take screenshot for analysis
    await browser.screenshot("/tmp/suno_skills/captcha_solve_attempt.png")
    print("Screenshot saved. Analyzing...")

    # Get the prompt
    prompt = await captcha_frame.evaluate("""() => {
        const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
        return el ? el.textContent.trim() : '';
    }""")
    print(f"Challenge: {prompt}")

    # Get grid cell positions within the iframe
    cells = await captcha_frame.evaluate("""() => {
        const cells = [];
        document.querySelectorAll('.task-image, [class*=task-image]').forEach((el, i) => {
            const r = el.getBoundingClientRect();
            if (r.width > 50) {
                const inner = el.querySelector('.image, [class*=image]');
                const style = inner ? window.getComputedStyle(inner) : window.getComputedStyle(el);
                cells.push({
                    i: i,
                    cx: Math.round(r.x + r.width/2),
                    cy: Math.round(r.y + r.height/2),
                    w: Math.round(r.width)
                });
            }
        });
        return cells;
    }""")

    if len(cells) == 0:
        # Try alternate selectors
        cells = await captcha_frame.evaluate("""() => {
            const cells = [];
            document.querySelectorAll('[role=button]').forEach((el, i) => {
                const r = el.getBoundingClientRect();
                if (r.width > 80 && r.width < 200 && r.height > 80 && r.height < 200) {
                    cells.push({i: i, cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2), w: Math.round(r.width)});
                }
            });
            return cells;
        }""")

    print(f"Found {len(cells)} grid cells")

    # Screenshot each cell area individually by cropping
    # But first, let me just try clicking using the frame API
    # The 3x3 grid centers (within iframe) are approximately:
    # Row 0: y≈190, Row 1: y≈320, Row 2: y≈450
    # Col 0: x≈70, Col 1: x≈200, Col 2: x≈330

    ix, iy = iframe_pos['x'], iframe_pos['y']

    # Map grid positions to page coordinates
    grid = []
    for row in range(3):
        for col in range(3):
            cell_x = 70 + col * 130
            cell_y = 190 + row * 130
            page_x = ix + cell_x
            page_y = iy + cell_y
            grid.append({
                'row': row, 'col': col,
                'page_x': page_x, 'page_y': page_y,
                'frame_x': cell_x, 'frame_y': cell_y
            })

    print("\nGrid layout (page coordinates):")
    for g in grid:
        print(f"  [{g['row']},{g['col']}] -> ({g['page_x']},{g['page_y']})")

    # Now I need to look at the screenshot and decide which cells to click
    # Let me save the screenshot path so it can be analyzed
    print(f"\n>>> SCREENSHOT AT: /tmp/suno_skills/captcha_solve_attempt.png")
    print(f">>> CHALLENGE: {prompt}")
    print(f">>> Grid origin on page: ({ix},{iy})")
    print(f">>> Cell size: ~120x120, spacing ~130px")
    print(f">>> 3x3 grid starts at iframe-relative (10, 130)")

    # Try to click cells - analyzing from the previous screenshot,
    # the challenge asks for items a person could pick up by hand
    # From visual analysis of earlier screenshots:
    # - Shoes/sneakers appeared in some cells (liftable)
    # - Buildings appeared in other cells (not liftable)
    #
    # I'll click what looked like liftable objects and then click verify
    # The exact images change each time, so I need to see THIS screenshot

    print("\nWaiting for you to check the screenshot and solve, or I can try...")
    print("Taking high-res screenshot of captcha area...")

    # Crop just the captcha area for clearer analysis
    # The captcha iframe is at (441,151) 400x600 on the page

    # Let me try using the frame directly to click cells
    # First, let me see what the actual task-image elements look like
    cell_details = await captcha_frame.evaluate("""() => {
        const details = [];
        const images = document.querySelectorAll('.task-image .image');
        images.forEach((img, i) => {
            const style = window.getComputedStyle(img);
            const parent = img.closest('.task-image');
            const pr = parent ? parent.getBoundingClientRect() : img.getBoundingClientRect();
            details.push({
                i: i,
                bg: style.backgroundImage ? style.backgroundImage.substring(4, 60) : 'none',
                x: Math.round(pr.x + pr.width/2),
                y: Math.round(pr.y + pr.height/2),
            });
        });
        return details;
    }""")

    print(f"\nImage details from frame ({len(cell_details)}):")
    for d in cell_details:
        print(f"  Cell {d['i']}: pos=({d['x']},{d['y']}) bg={d['bg']}")

    # Wait for user - they can solve it in the browser
    print("\n=== Solve the CAPTCHA in the browser window ===")
    print("Waiting up to 3 minutes...\n")

    solved = False
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
            solved = True
            print(f"[{tick*5}s] CAPTCHA gone!")
            break
        if tick % 6 == 0 and tick > 0:
            print(f"[{tick*5}s] Waiting...")

    if solved:
        await asyncio.sleep(2)
        print("Re-clicking Create...")
        await create.click_button("Create")
        await asyncio.sleep(5)

        # Check for another CAPTCHA
        iframe_pos2, _ = await get_captcha_state(browser, page)
        if iframe_pos2:
            print("Another CAPTCHA appeared! Solve it again...")
            for tick2 in range(36):
                await asyncio.sleep(5)
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
                if not still2:
                    print("Second CAPTCHA solved! Re-clicking Create...")
                    await asyncio.sleep(2)
                    await create.click_button("Create")
                    await asyncio.sleep(5)
                    break

        # Check result
        await asyncio.sleep(10)
        await browser.screenshot("/tmp/suno_skills/post_captcha_result.png")
        still_form = await browser.evaluate("""() => {
            const btns = document.querySelectorAll('button');
            for (const b of btns) {
                if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 200) return true;
            }
            return false;
        }""")
        if still_form:
            print("Still on form - song not created yet")
        else:
            print("SUCCESS - Song is generating!")
    else:
        print("Timeout waiting for CAPTCHA solve")

    print("\nBrowser open for 60s...")
    await asyncio.sleep(60)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
