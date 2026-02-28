"""Validation test for fixed create_song and export skills.

Tests:
1. set_styles targets the correct textarea (not "Exclude styles" input)
2. set_title works without Advanced Options
3. Export dropdown has all 3 options
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

    # Navigate to Create
    await browser.navigate("https://suno.com/create")
    await asyncio.sleep(5)
    await modal.dismiss_all()

    # Switch to Custom
    r = await create.switch_to_custom()
    print(f"Switch to Custom: {r.success}")
    await asyncio.sleep(1)

    # ===== TEST 1: set_styles targets correct textarea =====
    print("\n=== TEST 1: set_styles targets correct textarea ===")

    # First, clear any existing content by observing the page
    # Record the "Exclude styles" input value BEFORE
    exclude_before = await browser.evaluate("""() => {
        const inputs = document.querySelectorAll('input');
        for (const inp of inputs) {
            const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
            if (ph.includes('exclude')) {
                return inp.value;
            }
        }
        return null;
    }""")
    print(f"  Exclude styles before: '{exclude_before}'")

    # Set styles
    r = await create.set_styles("test-genre-12345, validation-style")
    print(f"  set_styles result: {r.success} - {r.message}")
    await asyncio.sleep(0.5)

    # Check where the text ended up
    # Check Exclude styles input
    exclude_after = await browser.evaluate("""() => {
        const inputs = document.querySelectorAll('input');
        for (const inp of inputs) {
            const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
            if (ph.includes('exclude')) {
                return inp.value;
            }
        }
        return null;
    }""")
    print(f"  Exclude styles after: '{exclude_after}'")

    # Check styles textarea content
    styles_content = await browser.evaluate("""() => {
        const textareas = document.querySelectorAll('textarea');
        for (const ta of textareas) {
            const r = ta.getBoundingClientRect();
            if (r.y > 350 && r.width > 200) {
                return ta.value;
            }
        }
        return null;
    }""")
    print(f"  Styles textarea content: '{styles_content}'")

    if styles_content and "test-genre-12345" in (styles_content or ""):
        print("  PASS: Styles typed into correct textarea")
    elif exclude_after and "test-genre-12345" in (exclude_after or ""):
        print("  FAIL: Styles typed into EXCLUDE input!")
    else:
        print("  UNCLEAR: Check screenshot")

    await browser.screenshot("/tmp/suno_skills/create_v2_styles.png")

    # ===== TEST 2: set_title works without Advanced Options =====
    print("\n=== TEST 2: set_title ===")
    r = await create.set_title("Test Automation Song")
    print(f"  set_title result: {r.success} - {r.message}")

    # Verify title input content
    title_content = await browser.evaluate("""() => {
        const inputs = document.querySelectorAll('input');
        for (const inp of inputs) {
            const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
            if (ph.includes('title') && inp.getBoundingClientRect().width > 100) {
                return inp.value;
            }
        }
        return null;
    }""")
    print(f"  Title input content: '{title_content}'")
    if title_content and "Test Automation Song" in (title_content or ""):
        print("  PASS: Title set correctly")
    else:
        print("  FAIL: Title not set correctly")

    await browser.screenshot("/tmp/suno_skills/create_v2_title.png")

    # ===== TEST 3: Set lyrics =====
    print("\n=== TEST 3: set_lyrics ===")
    r = await create.set_lyrics("[Verse]\nHello world this is a test\n[Chorus]\nAutomation works the best")
    print(f"  set_lyrics result: {r.success} - {r.message}")

    await browser.screenshot("/tmp/suno_skills/create_v2_complete.png")

    # ===== TEST 4: Navigate to Studio for export test =====
    print("\n=== TEST 4: Export dropdown options ===")
    r = await nav.to_studio()
    await asyncio.sleep(3)
    await modal.dismiss_all()

    # Drag a clip if needed
    track_count = await studio.get_track_count()
    if track_count.data == 0:
        print("  Dragging clip to timeline...")
        await studio.drag_clip_to_timeline(0)
        await asyncio.sleep(5)

    # Click Export
    clicked = await studio.click_button("Export")
    if not clicked:
        await browser.page.mouse.click(917, 86)
    await asyncio.sleep(1.5)

    # Find ALL dropdown items
    dropdown = await browser.evaluate("""() => {
        const items = [];
        // Look for any recently appeared elements (menus, popovers)
        const allEls = document.querySelectorAll('*');
        for (const el of allEls) {
            const r = el.getBoundingClientRect();
            const text = el.textContent.trim();
            // Export dropdown items appear below the Export button (~y=85), in a narrow column
            if (r.y > 100 && r.y < 300 && r.x > 700 && r.x < 1000 &&
                r.width > 60 && r.width < 300 && r.height > 15 && r.height < 60 &&
                el.children.length === 0 && text.length > 3 && text.length < 30 &&
                !text.includes('\\n')) {
                items.push({text: text, x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
            }
        }
        // Deduplicate by text
        const seen = new Set();
        return items.filter(i => {
            if (seen.has(i.text)) return false;
            seen.add(i.text);
            return true;
        });
    }""") or []

    print(f"  Export dropdown items ({len(dropdown)}):")
    for item in dropdown:
        print(f"    [{item['x']},{item['y']}] \"{item['text']}\"")

    has_full = any("Full" in d['text'] for d in dropdown)
    has_selected = any("Selected" in d['text'] for d in dropdown)
    has_multi = any("Multi" in d['text'] for d in dropdown)
    print(f"\n  Full Song: {'PASS' if has_full else 'FAIL'}")
    print(f"  Selected Time Range: {'PASS' if has_selected else 'FAIL'}")
    print(f"  Multitrack: {'PASS' if has_multi else 'FAIL'}")

    await browser.screenshot("/tmp/suno_skills/export_v2_dropdown.png")

    # Dismiss
    await browser.page.keyboard.press("Escape")

    print("\n=== All v2 tests complete ===")
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
