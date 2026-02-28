"""Final comprehensive test of all features.

Tests: Login, Create (lyrics/styles/title), Studio (clip/tracks/EQ/mastering), Export
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, StudioSkill, EQSkill, MixingSkill, CreateSkill
from src.agents.mastering import MasteringAgent, MASTERING_PROFILES

PASS = 0
FAIL = 0


def check(name, result):
    global PASS, FAIL
    ok = result.success if hasattr(result, 'success') else bool(result)
    msg = result.message if hasattr(result, 'message') else str(result)
    if ok:
        PASS += 1
        print(f"  [PASS] {name}: {msg}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}: {msg}")
    return ok


async def main():
    global PASS, FAIL
    browser = BrowserController(headless=False, cdp_port=9222)
    ok = await browser.connect()
    if not ok:
        print("FATAL: Browser launch failed")
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    studio = StudioSkill(browser)
    eq = EQSkill(browser)
    mixing = MixingSkill(browser)
    create = CreateSkill(browser)

    # ===== 1. LOGIN =====
    print("\n=== 1. LOGIN ===")
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)
    r = await nav.is_logged_in()
    check("Login check", r)

    # ===== 2. CREATE PAGE =====
    print("\n=== 2. CREATE PAGE ===")
    r = await nav.to_create()
    check("Navigate to Create", r)
    await modal.dismiss_all()

    r = await create.switch_to_custom()
    check("Switch to Custom", r)
    await asyncio.sleep(1)

    r = await create.set_lyrics("[Verse]\nTest lyrics for automation\n[Chorus]\nEverything works perfectly")
    check("Set lyrics", r)
    await create._dismiss_modals()

    r = await create.set_styles("indie pop, acoustic, dreamy")
    check("Set styles", r)
    await create._dismiss_modals()

    r = await create.set_title("Automation Test Song")
    check("Set title", r)
    await create._dismiss_modals()

    # Verify title was set
    title_val = await browser.evaluate("""() => {
        const inputs = document.querySelectorAll('input');
        let best = null;
        for (const inp of inputs) {
            const ph = (inp.getAttribute('placeholder') || '').toLowerCase();
            const r = inp.getBoundingClientRect();
            if (ph.includes('title') && r.width > 100 && r.y > 60) {
                if (!best || r.y > best.y) best = {val: inp.value, y: r.y};
            }
        }
        return best ? best.val : null;
    }""")
    if title_val == "Automation Test Song":
        PASS += 1
        print(f"  [PASS] Title verification: '{title_val}'")
    else:
        FAIL += 1
        print(f"  [FAIL] Title verification: expected 'Automation Test Song', got '{title_val}'")

    # Check Create button exists
    create_btn = await browser.evaluate("""() => {
        const btns = document.querySelectorAll('button');
        for (const b of btns) {
            if (b.textContent.trim() === 'Create' && b.getBoundingClientRect().width > 50) return true;
        }
        return false;
    }""")
    if create_btn:
        PASS += 1
        print("  [PASS] Create button found (not clicking to save credits)")
    else:
        FAIL += 1
        print("  [FAIL] Create button not found")

    await browser.screenshot("/tmp/suno_skills/final_create.png")

    # ===== 3. STUDIO =====
    print("\n=== 3. STUDIO ===")
    r = await nav.to_studio()
    check("Navigate to Studio", r)
    await modal.dismiss_all()
    await asyncio.sleep(2)

    # Ensure a track exists
    tc = await studio.get_track_count()
    if tc.data == 0:
        print("  (Dragging clip to timeline...)")
        await studio.drag_clip_to_timeline(0)
        await asyncio.sleep(5)
        tc = await studio.get_track_count()
    check("Track count > 0", type('R', (), {'success': tc.data > 0, 'message': f"{tc.data} tracks"})())

    # Select clip
    r = await studio.select_clip(0)
    check("Select clip", r)
    await modal.dismiss_all()

    # Switch tabs
    r = await studio.switch_to_track_tab()
    check("Switch to Track tab", r)

    r = await studio.switch_to_clip_tab()
    check("Switch to Clip tab", r)

    # ===== 4. EQ =====
    print("\n=== 4. EQ ===")
    await studio.switch_to_track_tab()
    await asyncio.sleep(1)

    r = await eq.enable()
    check("Enable EQ", r)

    r = await eq.set_preset("Flat (Reset)")
    check("Set Flat preset", r)

    r = await eq.set_preset("Presence")
    check("Set Presence preset", r)

    r = await eq.set_band(4, gain="1.5dB")
    check("Set band 4 gain", r)

    r = await eq.get_current_state()
    check("Get EQ state", r)

    await browser.screenshot("/tmp/suno_skills/final_eq.png")

    # ===== 5. MIXING =====
    print("\n=== 5. MIXING ===")
    r = await mixing.get_track_info()
    check("Get track info", r)
    if r.data:
        for t in r.data:
            print(f"    Track: {t.get('name', '?')}")

    # ===== 6. EXPORT =====
    print("\n=== 6. EXPORT ===")
    # Just verify the dropdown opens - don't actually export
    clicked = await studio.click_button("Export")
    if not clicked:
        await browser.page.mouse.click(917, 86)
        clicked = True
    await asyncio.sleep(1.5)

    # Check for Full Song option
    full_btn = await browser.evaluate("""() => {
        const els = document.querySelectorAll('*');
        for (const el of els) {
            if (el.textContent.trim() === 'Full Song' && el.getBoundingClientRect().width > 0 &&
                el.children.length === 0) return true;
        }
        return false;
    }""")
    if full_btn:
        PASS += 1
        print("  [PASS] Export dropdown: Full Song found")
    else:
        FAIL += 1
        print("  [FAIL] Export dropdown: Full Song not found")

    await browser.screenshot("/tmp/suno_skills/final_export.png")
    await browser.page.keyboard.press("Escape")

    # ===== 7. MASTERING PROFILES =====
    print("\n=== 7. MASTERING PROFILES ===")
    from src.skills.eq import EQ_PRESETS
    for name, prof in MASTERING_PROFILES.items():
        preset = prof.get("eq_preset", "Flat (Reset)")
        if preset in EQ_PRESETS:
            PASS += 1
            print(f"  [PASS] Profile '{name}' -> preset '{preset}'")
        else:
            FAIL += 1
            print(f"  [FAIL] Profile '{name}' -> unknown preset '{preset}'")

    # ===== SUMMARY =====
    print(f"\n{'='*50}")
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {PASS + FAIL} total")
    print(f"{'='*50}")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
