"""Phase 2: Connect to running browser via CDP, click CAPTCHA cells, click Verify.

Usage: python captcha_phase2.py 0,1 2,0
  - Arguments are row,col pairs of cells to click (0-indexed)
  - Reads iframe position from /tmp/suno_skills/captcha_state.json
"""
import asyncio
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Grid cell centers within the hCaptcha iframe
CELL_CENTERS = {
    (0, 0): (70, 190), (0, 1): (200, 190), (0, 2): (330, 190),
    (1, 0): (70, 320), (1, 1): (200, 320), (1, 2): (330, 320),
    (2, 0): (70, 450), (2, 1): (200, 450), (2, 2): (330, 450),
}
VERIFY_BTN = (200, 530)


async def main():
    # Parse cell arguments
    if len(sys.argv) < 2:
        print("Usage: python captcha_phase2.py 0,1 2,0")
        print("  Each arg is row,col of a cell to click")
        return

    cells_to_click = []
    for arg in sys.argv[1:]:
        parts = arg.split(",")
        if len(parts) == 2:
            r, c = int(parts[0]), int(parts[1])
            cells_to_click.append((r, c))

    print(f"Cells to click: {cells_to_click}")

    # Read state from Phase 1
    state_path = "/tmp/suno_skills/captcha_state.json"
    if not os.path.exists(state_path):
        print(f"No state file at {state_path} - is Phase 1 running?")
        return

    with open(state_path) as f:
        state = json.load(f)

    iframe = state["iframe"]
    ix, iy = iframe["x"], iframe["y"]
    print(f"Iframe at ({ix},{iy})")
    print(f"Challenge: {state['prompt']}")

    # Connect to running browser via CDP
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp("http://localhost:9222")
    except Exception as e:
        print(f"Cannot connect to browser on CDP port 9222: {e}")
        print("Is Phase 1 still running?")
        await pw.stop()
        return

    context = browser.contexts[0]
    page = context.pages[0]
    print(f"Connected to browser. Page: {page.url[:60]}")

    # Verify CAPTCHA is still visible
    iframe_pos = await page.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                const r = f.getBoundingClientRect();
                if (r.width > 100) return {x: Math.round(r.x), y: Math.round(r.y)};
            }
        }
        return null;
    }""")

    if not iframe_pos:
        print("CAPTCHA not visible! It may have expired.")
        await pw.stop()
        return

    # Use current iframe position (may have shifted)
    ix, iy = iframe_pos["x"], iframe_pos["y"]
    print(f"Current iframe at ({ix},{iy})")

    # Click each specified cell
    for r, c in cells_to_click:
        if (r, c) not in CELL_CENTERS:
            print(f"  Invalid cell ({r},{c}) - skipping")
            continue
        cx, cy = CELL_CENTERS[(r, c)]
        px, py = ix + cx, iy + cy
        print(f"  Clicking cell [{r},{c}] at page ({px},{py})...")
        await page.mouse.click(px, py)
        await asyncio.sleep(0.8)

    # Take screenshot to verify selections
    await page.screenshot(path="/tmp/suno_skills/captcha_after_clicks.png")
    print("Screenshot saved: captcha_after_clicks.png")

    # Check if cells are selected
    captcha_frame = None
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            captcha_frame = frame
            break

    if captcha_frame:
        selected = await captcha_frame.evaluate("""() => {
            const cells = document.querySelectorAll('.task-image');
            const results = [];
            cells.forEach((c, i) => {
                const isSelected = c.classList.contains('selected') ||
                                   c.getAttribute('aria-pressed') === 'true' ||
                                   c.querySelector('[class*=selected]') !== null;
                if (isSelected) results.push(i);
            });
            return results;
        }""")
        print(f"Selected cells: {selected}")

    # Click Verify button
    vx, vy = ix + VERIFY_BTN[0], iy + VERIFY_BTN[1]
    print(f"\nClicking Verify at ({vx},{vy})...")
    await page.mouse.click(vx, vy)
    await asyncio.sleep(3)

    # Check result
    await page.screenshot(path="/tmp/suno_skills/captcha_after_verify.png")

    # Is CAPTCHA still showing?
    still = await page.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                const r = f.getBoundingClientRect();
                return r.width > 100 && r.x > 0;
            }
        }
        return false;
    }""")

    if still:
        print("CAPTCHA still showing - may need another round or wrong answer.")
        print("Check captcha_after_verify.png")
    else:
        print("CAPTCHA dismissed! Phase 1 should re-click Create automatically.")

    # Update state
    state["status"] = "verified" if not still else "failed"
    with open(state_path, "w") as f:
        json.dump(state, f, indent=2)

    await pw.stop()
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
