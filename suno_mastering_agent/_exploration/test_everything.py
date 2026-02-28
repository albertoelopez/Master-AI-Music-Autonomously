#!/usr/bin/env python3
"""Actually click and test every single control in Suno Studio.
Takes screenshot after EVERY action. Retries on failure."""
import asyncio
import json
import os
import sys
from src.browser import BrowserController

OUTPUT = "/tmp/suno_test"
os.makedirs(OUTPUT, exist_ok=True)

# Clean lock
lock = os.path.join(os.path.dirname(__file__), "browser_data", "SingletonLock")
if os.path.exists(lock):
    os.remove(lock)

step = 0


async def snap(browser, label):
    """Screenshot + print what we see."""
    global step
    step += 1
    name = f"{step:03d}_{label}"
    path = os.path.join(OUTPUT, f"{name}.png")
    await browser.screenshot(path)

    # Get visible text summary
    text = await browser.evaluate("() => document.body.innerText.substring(0, 300)")
    print(f"\n[{step:03d}] {label}")
    print(f"  Text: {text[:150]}")
    return path


async def wait_and_snap(browser, label, seconds=2):
    await asyncio.sleep(seconds)
    return await snap(browser, label)


async def click_text(browser, text, label=None, timeout=5000):
    """Click a button by text content."""
    try:
        await browser.page.click(f'button:has-text("{text}")', timeout=timeout)
        await asyncio.sleep(1.5)
        await snap(browser, label or f"clicked_{text}")
        return True
    except Exception as e:
        print(f"  Could not click '{text}': {e}")
        return False


async def click_xy(browser, x, y, label="click"):
    """Click at coordinates."""
    await browser.page.mouse.click(x, y)
    await asyncio.sleep(1.5)
    await snap(browser, label)


async def get_buttons(browser, region=None):
    """Get all visible buttons, optionally filtered by region."""
    min_x = region.get("minX", 0) if region else 0
    max_x = region.get("maxX", 9999) if region else 9999
    min_y = region.get("minY", 0) if region else 0
    max_y = region.get("maxY", 9999) if region else 9999
    script = f"""() => {{
        return [...document.querySelectorAll('button')]
            .filter(el => {{
                if (el.offsetParent === null) return false;
                const r = el.getBoundingClientRect();
                if (r.width === 0) return false;
                if (r.x < {min_x} || r.x > {max_x}) return false;
                if (r.y < {min_y} || r.y > {max_y}) return false;
                return true;
            }})
            .map(el => ({{
                text: (el.textContent || '').trim().substring(0, 50),
                ariaLabel: el.getAttribute('aria-label'),
                x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
            }}))
            .filter(b => b.text || b.ariaLabel);
    }}"""
    return await browser.evaluate(script)


async def get_sliders(browser):
    """Get all sliders on page."""
    return await browser.evaluate("""() => {
        return [...document.querySelectorAll('[role=slider], input[type=range], [class*=fader-knob], [class*=Slider]')]
            .filter(el => el.offsetParent !== null)
            .map(el => ({
                ariaLabel: el.getAttribute('aria-label'),
                ariaValueNow: el.getAttribute('aria-valuenow'),
                ariaValueMin: el.getAttribute('aria-valuemin'),
                ariaValueMax: el.getAttribute('aria-valuemax'),
                className: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
                x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
            }));
    }""")


async def get_menus(browser):
    """Check for open menus/dialogs."""
    return await browser.evaluate("""() => {
        const sels = ['[role=menu]', '[role=dialog]', '[role=listbox]',
                      '[data-state=open]', '[data-radix-popper-content-wrapper]'];
        const found = [];
        for (const sel of sels) {
            document.querySelectorAll(sel).forEach(el => {
                if (el.offsetParent !== null || el.getAttribute('data-state') === 'open') {
                    found.push({
                        selector: sel,
                        text: el.textContent.trim().substring(0, 300),
                    });
                }
            });
        }
        return found;
    }""")


async def dismiss(browser):
    """Close any open menu/dialog."""
    await browser.page.keyboard.press("Escape")
    await asyncio.sleep(0.5)


# ============================================================
# TEST PHASES
# ============================================================

async def phase1_setup_studio(browser):
    """Get to Studio with clips on timeline."""
    print("\n" + "=" * 60)
    print("PHASE 1: SETUP STUDIO WITH CLIPS")
    print("=" * 60)

    await browser.navigate("https://suno.com/studio")
    await asyncio.sleep(8)
    await snap(browser, "studio_loaded")

    # Check current state
    text = await browser.evaluate("() => document.body.innerText.substring(0, 2000)")

    if "Sunday Morning" in text or "Remix" in text:
        print("  Clips already on timeline!")
        return True

    # Need to drag clip from sidebar
    print("  Dragging clip to timeline...")

    # First click a thumbnail in the sidebar
    thumbnails = await browser.evaluate("""() => {
        return [...document.querySelectorAll('img')]
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.x < 100 && r.y > 50 && r.width > 30 && r.width < 100 && el.offsetParent !== null;
            })
            .map(el => ({
                x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
            }));
    }""")

    if not thumbnails:
        print("  No thumbnails found in sidebar!")
        return False

    src = thumbnails[0]
    print(f"  Source thumbnail at ({src['x']}, {src['y']})")

    # Drag from thumbnail to timeline center
    await browser.page.mouse.move(src['x'], src['y'])
    await asyncio.sleep(0.5)
    await browser.page.mouse.down()
    await asyncio.sleep(0.3)

    # Smooth drag to timeline area
    target_x, target_y = 500, 300
    steps = 20
    for i in range(steps):
        frac = (i + 1) / steps
        x = src['x'] + (target_x - src['x']) * frac
        y = src['y'] + (target_y - src['y']) * frac
        await browser.page.mouse.move(x, y)
        await asyncio.sleep(0.03)

    await browser.page.mouse.up()
    await asyncio.sleep(3)
    await snap(browser, "after_drag")

    # Handle tempo dialog
    try:
        confirm = await browser.page.query_selector('button:has-text("Confirm")')
        if confirm:
            await confirm.click()
            await asyncio.sleep(3)
            await snap(browser, "tempo_confirmed")
            print("  Confirmed tempo dialog")
    except Exception:
        pass

    return True


async def phase2_clip_tab(browser):
    """Test every control on the Clip tab."""
    print("\n" + "=" * 60)
    print("PHASE 2: CLIP TAB - CLICK EVERYTHING")
    print("=" * 60)

    # Click a clip on the timeline
    # Find clip elements
    clips = await browser.evaluate("""() => {
        return [...document.querySelectorAll('[class*=clip], [class*=Clip], [data-testid*=clip]')]
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.x > 150 && r.y > 60 && r.width > 50 && el.offsetParent !== null;
            })
            .map(el => ({
                x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
                cls: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
            }))
            .slice(0, 5);
    }""")

    if clips:
        print(f"  Found {len(clips)} clip elements")
        await click_xy(browser, clips[0]['x'], clips[0]['y'], "click_clip_element")
    else:
        # Fallback: click in the timeline waveform area
        print("  No clip elements found, clicking timeline area...")
        await click_xy(browser, 400, 130, "click_timeline_area")

    # Verify Clip tab is visible
    right_btns = await get_buttons(browser, {"minX": 500})
    btn_texts = [b['text'] for b in right_btns]
    print(f"  Right panel buttons: {btn_texts[:15]}")

    if "Clip" not in btn_texts and "Track" not in btn_texts:
        print("  No Clip/Track tabs! Trying different click positions...")
        for y in [100, 120, 140, 160]:
            await click_xy(browser, 400, y, f"retry_click_y{y}")
            right_btns = await get_buttons(browser, {"minX": 500})
            if any(b['text'] in ('Clip', 'Track') for b in right_btns):
                print(f"  Found tabs after clicking y={y}")
                break

    # Make sure Clip tab is active
    await click_text(browser, "Clip", "activate_clip_tab")

    # Now test each control on the Clip tab
    # 1. Clip Settings toggle
    await click_text(browser, "Clip Settings", "click_clip_settings")

    # 2. Tempo - On Beat dropdown
    await click_text(browser, "On Beat", "click_on_beat")
    menus = await get_menus(browser)
    for m in menus:
        print(f"  Tempo menu: {m['text'][:200]}")
    await snap(browser, "tempo_menu")
    await dismiss(browser)

    # 3. Transpose buttons
    for label in ["-", "+", "0"]:
        # Find transpose buttons in right panel
        pass  # These are tiny, skip for now

    # 4. Speed buttons
    await click_text(browser, "½", "speed_half")
    await asyncio.sleep(1)
    await click_text(browser, "×2", "speed_double")
    await asyncio.sleep(1)

    # 5. Clip Volume slider
    sliders = await get_sliders(browser)
    print(f"  Sliders found: {len(sliders)}")
    for s in sliders:
        print(f"    {s.get('ariaLabel', s.get('className', '')[:30])} at ({s['x']},{s['y']})")

    # 6. Extract Stems
    await click_text(browser, "Extract Stems", "click_extract_stems")
    menus = await get_menus(browser)
    for m in menus:
        print(f"  Stems menu: {m['text'][:200]}")
    await snap(browser, "stems_menu")
    await dismiss(browser)

    # 7. Remix button
    await click_text(browser, "Remix", "click_remix")
    menus = await get_menus(browser)
    for m in menus:
        print(f"  Remix menu: {m['text'][:200]}")
    await snap(browser, "remix_menu")
    await dismiss(browser)

    # 8. Show More
    await click_text(browser, "Show More", "click_show_more")

    # 9. Export dropdown
    await click_text(browser, "Export", "click_export")
    menus = await get_menus(browser)
    for m in menus:
        print(f"  Export menu: {m['text'][:200]}")
    await snap(browser, "export_menu")
    await dismiss(browser)

    # 10. Right-click on clip for context menu
    print("  Right-clicking clip...")
    await browser.page.mouse.click(400, 130, button="right")
    await asyncio.sleep(2)
    menus = await get_menus(browser)
    for m in menus:
        print(f"  Context menu: {m['text'][:300]}")
    await snap(browser, "right_click_menu")
    await dismiss(browser)


async def phase3_track_tab(browser):
    """THE BIG ONE - Find and test Track tab with EQ."""
    print("\n" + "=" * 60)
    print("PHASE 3: TRACK TAB - FIND THE EQ")
    print("=" * 60)

    # First make sure a clip is selected
    await click_xy(browser, 400, 130, "select_clip_for_track")

    # Now click the Track tab
    success = await click_text(browser, "Track", "click_track_tab")

    if not success:
        print("  Track tab not clickable, trying to find it...")
        right_btns = await get_buttons(browser, {"minX": 500})
        for b in right_btns:
            if b['text'] == 'Track':
                await click_xy(browser, b['x'], b['y'], "click_track_btn_xy")
                success = True
                break

    if not success:
        # Try clicking track header on left side instead
        print("  Trying track headers on left...")
        for y in [100, 130, 160, 190, 220]:
            await click_xy(browser, 30, y, f"track_header_y{y}")
            right_btns = await get_buttons(browser, {"minX": 500})
            track_btns = [b for b in right_btns if b['text'] == 'Track']
            if track_btns:
                await click_xy(browser, track_btns[0]['x'], track_btns[0]['y'], "found_track_tab")
                success = True
                break

    # Capture what's in the right panel now
    right_text = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const texts = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            const r = walker.currentNode.parentElement?.getBoundingClientRect();
            if (r && r.left > vw * 0.5 && r.width > 0) {
                const t = walker.currentNode.textContent.trim();
                if (t && t.length > 0) texts.push(t);
            }
        }
        return [...new Set(texts)];
    }""")
    print(f"  Right panel text: {right_text[:20]}")

    # Look for EQ-specific elements
    eq_elements = await browser.evaluate("""() => {
        const results = [];
        // Canvas elements (spectrum analyzer, EQ graph)
        document.querySelectorAll('canvas').forEach(el => {
            if (el.offsetParent !== null) {
                const r = el.getBoundingClientRect();
                results.push({type: 'canvas', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
            }
        });
        // SVG elements
        document.querySelectorAll('svg').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 100 && r.x > window.innerWidth * 0.5) {
                results.push({type: 'svg', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
            }
        });
        // Switches/toggles
        document.querySelectorAll('[role=switch], [role=checkbox]').forEach(el => {
            if (el.offsetParent !== null) {
                const r = el.getBoundingClientRect();
                results.push({
                    type: 'switch',
                    ariaLabel: el.getAttribute('aria-label'),
                    checked: el.getAttribute('aria-checked'),
                    x: Math.round(r.x), y: Math.round(r.y),
                });
            }
        });
        return results;
    }""")
    print(f"  EQ-specific elements: {len(eq_elements)}")
    for el in eq_elements:
        print(f"    {json.dumps(el)}")

    # Get ALL right panel elements
    all_right = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        return [...document.querySelectorAll('button, [role=slider], input, select, canvas, svg, [role=switch], [role=checkbox], [role=tab], label')]
            .filter(el => {
                const r = el.getBoundingClientRect();
                return r.left > vw * 0.5 && el.offsetParent !== null && r.width > 0;
            })
            .map(el => ({
                tag: el.tagName,
                text: (el.textContent || '').trim().substring(0, 40),
                ariaLabel: el.getAttribute('aria-label'),
                role: el.getAttribute('role'),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
            }));
    }""")
    print(f"  All right panel interactive elements: {len(all_right)}")
    for el in all_right:
        label = el['text'] or el['ariaLabel'] or ''
        print(f"    <{el['tag']}> '{label}' ({el['x']},{el['y']}) {el['w']}x{el['h']}")

    # Check for any EQ keywords in entire page
    kw_check = await browser.evaluate("""() => {
        const text = document.body.innerText.toLowerCase();
        const found = [];
        for (const kw of ['eq', 'equalizer', 'frequency', 'gain', 'resonance',
                          'spectrum', 'preset', 'flat', 'vocal', 'warm',
                          'bass boost', 'air', 'clarity', 'band 1', 'band 2']) {
            if (text.includes(kw)) found.push(kw);
        }
        return found;
    }""")
    print(f"  EQ keywords found on page: {kw_check}")

    sliders = await get_sliders(browser)
    print(f"  All sliders: {len(sliders)}")
    for s in sliders:
        print(f"    {s.get('ariaLabel', s.get('className', '')[:40])} ({s['x']},{s['y']}) {s['w']}x{s['h']}")


async def phase4_track_faders(browser):
    """Test the volume faders and track controls on the left."""
    print("\n" + "=" * 60)
    print("PHASE 4: TRACK FADERS & LEFT CONTROLS")
    print("=" * 60)

    # Find fader knobs
    faders = await browser.evaluate("""() => {
        return [...document.querySelectorAll('[class*=fader], [class*=Fader]')]
            .filter(el => el.offsetParent !== null)
            .map(el => ({
                className: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
            }));
    }""")
    print(f"  Fader elements: {len(faders)}")
    for f in faders:
        print(f"    {f['className'][:40]} ({f['x']},{f['y']}) {f['w']}x{f['h']}")

    # Try dragging a fader
    if faders:
        f = faders[0]
        cx = f['x'] + f['w'] // 2
        cy = f['y'] + f['h'] // 2
        print(f"  Dragging fader at ({cx},{cy})")
        await browser.page.mouse.move(cx, cy)
        await browser.page.mouse.down()
        await browser.page.mouse.move(cx + 20, cy)  # Drag right = louder
        await browser.page.mouse.up()
        await asyncio.sleep(1)
        await snap(browser, "fader_dragged")

    # Find and test Solo buttons
    solo_btns = await browser.evaluate("""() => {
        return [...document.querySelectorAll('button')]
            .filter(el => {
                const t = (el.textContent || '').trim();
                return t === 'S' && el.offsetParent !== null && el.getBoundingClientRect().x < 300;
            })
            .map(el => ({
                x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width/2),
                y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height/2),
            }));
    }""")
    print(f"  Solo buttons: {len(solo_btns)}")
    if solo_btns:
        await click_xy(browser, solo_btns[0]['x'], solo_btns[0]['y'], "solo_track1")
        await asyncio.sleep(1)
        # Un-solo
        await click_xy(browser, solo_btns[0]['x'], solo_btns[0]['y'], "unsolo_track1")


async def phase5_create_song(browser):
    """Test creating a song."""
    print("\n" + "=" * 60)
    print("PHASE 5: CREATE A SONG")
    print("=" * 60)

    await browser.navigate("https://suno.com/create")
    await asyncio.sleep(5)
    await snap(browser, "create_page")

    # Click Custom tab
    await click_text(browser, "Custom", "custom_tab")

    # Fill in lyrics
    try:
        textarea = await browser.page.query_selector('textarea')
        if textarea:
            await textarea.fill("Testing automation\nThis is a test song\nGenerated by the Suno agent")
            await asyncio.sleep(1)
            await snap(browser, "lyrics_filled")
    except Exception as e:
        print(f"  Error filling lyrics: {e}")

    # Fill in styles
    try:
        style_input = await browser.page.query_selector('input[placeholder*=""]')
        # Find the styles input more carefully
        inputs = await browser.page.query_selector_all('input')
        for inp in inputs:
            ph = await inp.get_attribute('placeholder')
            box = await inp.bounding_box()
            if box and box['x'] < 400 and box['y'] > 200:
                print(f"  Input: placeholder='{ph}' at ({box['x']},{box['y']})")
    except Exception as e:
        print(f"  Error: {e}")

    # Click Advanced Options
    await click_text(browser, "Advanced Options", "advanced_options")

    # Find Weirdness and Style Influence sliders
    sliders = await get_sliders(browser)
    print(f"  Sliders after Advanced: {len(sliders)}")
    for s in sliders:
        print(f"    {s.get('ariaLabel', '?')} = {s.get('ariaValueNow', '?')} ({s['x']},{s['y']})")

    # Drag Weirdness slider
    for s in sliders:
        if s.get('ariaLabel') == 'Weirdness':
            print(f"  Dragging Weirdness slider...")
            await browser.page.mouse.move(s['x'], s['y'])
            await browser.page.mouse.down()
            await browser.page.mouse.move(s['x'] + 30, s['y'])
            await browser.page.mouse.up()
            await asyncio.sleep(1)
            await snap(browser, "weirdness_dragged")

    # DON'T actually click Create (costs credits)
    print("  Skipping actual creation to save credits")


async def phase6_navigate_library(browser):
    """Test library navigation."""
    print("\n" + "=" * 60)
    print("PHASE 6: LIBRARY")
    print("=" * 60)

    await browser.navigate("https://suno.com/me")
    await asyncio.sleep(5)
    await snap(browser, "library_songs")

    # Click through tabs
    for tab in ["Playlists", "Workspaces", "Studio Projects", "Personas", "Cover Art"]:
        try:
            await browser.page.click(f'text="{tab}"', timeout=3000)
            await asyncio.sleep(2)
            await snap(browser, f"library_{tab.lower().replace(' ', '_')}")
        except Exception:
            # Try without quotes
            try:
                await browser.page.click(f'button:has-text("{tab}")', timeout=2000)
                await asyncio.sleep(2)
                await snap(browser, f"library_{tab.lower().replace(' ', '_')}")
            except Exception:
                print(f"  Could not click tab: {tab}")


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    try:
        if await phase1_setup_studio(browser):
            await phase2_clip_tab(browser)
            await phase3_track_tab(browser)
            await phase4_track_faders(browser)

        await phase5_create_song(browser)
        await phase6_navigate_library(browser)

        print("\n" + "=" * 60)
        print(f"DONE - {step} screenshots saved to {OUTPUT}")
        print("=" * 60)

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        await snap(browser, "error_state")
    finally:
        await browser.close()


asyncio.run(main())
