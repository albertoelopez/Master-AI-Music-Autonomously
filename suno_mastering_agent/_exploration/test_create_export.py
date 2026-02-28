"""Test song creation and export skills on live Suno.

Run: python _exploration/test_create_export.py
Requires: Chrome with CDP port 9222 NOT running (will launch fresh).
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, StudioSkill, CreateSkill


async def main():
    browser = BrowserController(headless=False, cdp_port=9222)
    ok = await browser.connect()
    if not ok:
        print("FAIL: Browser launch")
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    studio = StudioSkill(browser)
    create = CreateSkill(browser)

    # Check login
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)
    login = await nav.is_logged_in()
    print(f"Login: {login.success} - {login.message}")
    if not login.success:
        print("NOT LOGGED IN - please log in manually, then re-run")
        input("Press Enter after logging in...")

    # ===== TEST 1: Navigate to Create page =====
    print("\n=== TEST 1: Navigate to Create page ===")
    r = await nav.to_create()
    print(f"  {r.message}")
    await modal.dismiss_all()

    # Take screenshot to see what we're working with
    await browser.screenshot("/tmp/suno_skills/create_page.png")

    # ===== TEST 2: Explore Create page layout =====
    print("\n=== TEST 2: Explore Create page layout ===")
    # Find all visible buttons
    buttons = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('button').forEach(btn => {
            const r = btn.getBoundingClientRect();
            if (r.width > 0 && btn.offsetParent !== null) {
                results.push({
                    text: btn.textContent.trim().substring(0, 50),
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
        });
        return results;
    }""")
    print(f"  Found {len(buttons)} buttons:")
    for b in buttons[:30]:
        print(f"    [{b['x']},{b['y']}] ({b['w']}x{b['h']}) \"{b['text'][:40]}\"")

    # Find textareas
    textareas = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('textarea').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0) {
                results.push({
                    placeholder: el.getAttribute('placeholder') || '',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
        });
        return results;
    }""")
    print(f"\n  Found {len(textareas)} textareas:")
    for t in textareas:
        print(f"    [{t['x']},{t['y']}] ({t['w']}x{t['h']}) placeholder=\"{t['placeholder'][:50]}\"")

    # Find inputs
    inputs = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('input').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0) {
                results.push({
                    type: el.type,
                    placeholder: el.getAttribute('placeholder') || '',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
        });
        return results;
    }""")
    print(f"\n  Found {len(inputs)} inputs:")
    for i in inputs[:20]:
        print(f"    [{i['x']},{i['y']}] ({i['w']}x{i['h']}) type={i['type']} placeholder=\"{i['placeholder'][:50]}\"")

    # ===== TEST 3: Switch to Custom mode =====
    print("\n=== TEST 3: Switch to Custom mode ===")
    r = await create.switch_to_custom()
    print(f"  {r.success}: {r.message}")
    await asyncio.sleep(1)
    await browser.screenshot("/tmp/suno_skills/create_custom.png")

    # Re-check textareas and inputs in Custom mode
    textareas_custom = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('textarea').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0) {
                results.push({
                    placeholder: el.getAttribute('placeholder') || '',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
        });
        return results;
    }""")
    print(f"\n  Custom mode textareas ({len(textareas_custom)}):")
    for t in textareas_custom:
        print(f"    [{t['x']},{t['y']}] ({t['w']}x{t['h']}) \"{t['placeholder'][:50]}\"")

    inputs_custom = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('input').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0) {
                results.push({
                    type: el.type,
                    placeholder: el.getAttribute('placeholder') || '',
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    h: Math.round(r.height)
                });
            }
        });
        return results;
    }""")
    print(f"\n  Custom mode inputs ({len(inputs_custom)}):")
    for i in inputs_custom:
        print(f"    [{i['x']},{i['y']}] ({i['w']}x{i['h']}) type={i['type']} placeholder=\"{i['placeholder'][:50]}\"")

    # ===== TEST 4: Set lyrics =====
    print("\n=== TEST 4: Set lyrics ===")
    test_lyrics = """[Verse]
Testing one two three
This is a test song for automation
Pixel by pixel we calibrate the machine

[Chorus]
Automated dreams in digital streams
Everything works like a well-oiled machine"""
    r = await create.set_lyrics(test_lyrics)
    print(f"  {r.success}: {r.message}")
    await asyncio.sleep(0.5)

    # ===== TEST 5: Set styles =====
    print("\n=== TEST 5: Set styles ===")
    r = await create.set_styles("indie pop, acoustic, upbeat")
    print(f"  {r.success}: {r.message}")
    await asyncio.sleep(0.5)
    await browser.screenshot("/tmp/suno_skills/create_filled.png")

    # ===== TEST 6: Check for Create button =====
    print("\n=== TEST 6: Find Create button ===")
    create_btn = await browser.evaluate("""() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            const text = btn.textContent.trim();
            const r = btn.getBoundingClientRect();
            if (text === 'Create' && r.width > 50 && btn.offsetParent !== null) {
                return {
                    text: text,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    disabled: btn.disabled
                };
            }
        }
        return null;
    }""")
    if create_btn:
        print(f"  Found Create button at ({create_btn['x']},{create_btn['y']}) w={create_btn['w']} disabled={create_btn['disabled']}")
    else:
        print("  Create button NOT found")

    # ===== DO NOT CLICK CREATE - just validate the form is filled =====
    print("\n=== NOT clicking Create (to avoid using credits) ===")
    print("  Song creation form is ready - would click Create to generate")

    # ===== TEST 7: Navigate to Studio for export test =====
    print("\n=== TEST 7: Navigate to Studio for export test ===")
    r = await nav.to_studio()
    print(f"  {r.message}")
    await modal.dismiss_all()
    await asyncio.sleep(2)

    # Check if there are tracks/clips in Studio
    track_count = await studio.get_track_count()
    print(f"  Tracks: {track_count.data}")
    await browser.screenshot("/tmp/suno_skills/studio_for_export.png")

    # If no tracks, try dragging a clip
    if track_count.data == 0:
        print("  No tracks - dragging clip from sidebar...")
        r = await studio.drag_clip_to_timeline(0)
        print(f"  {r.success}: {r.message}")
        await asyncio.sleep(5)
        track_count = await studio.get_track_count()
        print(f"  Tracks after drag: {track_count.data}")

    # ===== TEST 8: Find Export button =====
    print("\n=== TEST 8: Find Export button ===")
    export_btn = await browser.evaluate("""() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            const text = btn.textContent.trim();
            const r = btn.getBoundingClientRect();
            if (text.includes('Export') && r.width > 0 && btn.offsetParent !== null) {
                return {
                    text: text,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    w: Math.round(r.width),
                    disabled: btn.disabled
                };
            }
        }
        return null;
    }""")
    if export_btn:
        print(f"  Found Export button at ({export_btn['x']},{export_btn['y']}) \"{export_btn['text']}\"")
    else:
        print("  Export button NOT found - looking for it by icon/area...")
        # Check the top toolbar area
        top_buttons = await browser.evaluate("""() => {
            const results = [];
            document.querySelectorAll('button').forEach(btn => {
                const r = btn.getBoundingClientRect();
                if (r.y < 100 && r.x > 800 && r.width > 0 && btn.offsetParent !== null) {
                    results.push({
                        text: btn.textContent.trim().substring(0, 30),
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width),
                        ariaLabel: btn.getAttribute('aria-label') || ''
                    });
                }
            });
            return results;
        }""")
        print(f"  Top-right buttons ({len(top_buttons)}):")
        for b in top_buttons:
            print(f"    [{b['x']},{b['y']}] ({b['w']}px) \"{b['text']}\" aria=\"{b['ariaLabel']}\"")

    # ===== TEST 9: Click Export to see dropdown =====
    if track_count.data > 0:
        print("\n=== TEST 9: Click Export to see dropdown options ===")
        clicked = await create.click_button("Export")
        if not clicked:
            # Try the known position from calibration
            print("  Button text match failed, trying position (917, 86)...")
            await browser.page.mouse.click(917, 86)
        await asyncio.sleep(1.5)
        await browser.screenshot("/tmp/suno_skills/export_dropdown.png")

        # Check what dropdown options appeared
        dropdown_options = await browser.evaluate("""() => {
            const results = [];
            // Check for dropdown menus, popovers, etc.
            document.querySelectorAll('[role=menu] [role=menuitem], [role=listbox] [role=option], [data-state=open] button, [class*=dropdown] button, [class*=menu] li, [class*=popover] button').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.width > 0 && el.offsetParent !== null) {
                    results.push({
                        text: el.textContent.trim().substring(0, 50),
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                    });
                }
            });
            // Also check all visible buttons/links that appeared recently
            document.querySelectorAll('button, a').forEach(el => {
                const r = el.getBoundingClientRect();
                const text = el.textContent.trim();
                if (r.width > 0 && r.y > 50 && r.y < 300 && el.offsetParent !== null &&
                    (text.includes('Full') || text.includes('Multi') || text.includes('Stem') || text.includes('Song') || text.includes('WAV'))) {
                    results.push({
                        text: text.substring(0, 50),
                        x: Math.round(r.x + r.width/2),
                        y: Math.round(r.y + r.height/2),
                    });
                }
            });
            return results;
        }""")
        if dropdown_options:
            print(f"  Export dropdown options ({len(dropdown_options)}):")
            for opt in dropdown_options:
                print(f"    [{opt['x']},{opt['y']}] \"{opt['text']}\"")
        else:
            print("  No dropdown options detected - trying broader search...")
            all_new = await browser.evaluate("""() => {
                const results = [];
                document.querySelectorAll('*').forEach(el => {
                    const r = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    const z = parseInt(style.zIndex);
                    if (z > 10 && r.width > 50 && r.height > 20 && r.y < 400 && el.children.length === 0) {
                        const text = el.textContent.trim();
                        if (text) results.push({
                            text: text.substring(0, 50),
                            x: Math.round(r.x + r.width/2),
                            y: Math.round(r.y + r.height/2),
                            z: z,
                            tag: el.tagName
                        });
                    }
                });
                return results.slice(0, 20);
            }""")
            for item in all_new:
                print(f"    [{item['x']},{item['y']}] z={item['z']} <{item['tag']}> \"{item['text']}\"")

        # Dismiss the dropdown
        await browser.page.keyboard.press("Escape")
        await asyncio.sleep(0.5)
    else:
        print("\n=== SKIP TEST 9: No tracks for export test ===")

    print("\n=== All Create/Export tests complete ===")
    print("Screenshots saved to /tmp/suno_skills/")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
