#!/usr/bin/env python3
"""Exhaustively find every control in Suno Studio.
Specifically hunts for EQ, mixing, mastering controls.
Resilient - retries on failure, loops through everything."""
import asyncio
import json
import os
import time
from src.browser import BrowserController

OUTPUT = "/tmp/suno_controls"
os.makedirs(OUTPUT, exist_ok=True)

# Remove stale lock
lock = os.path.join(os.path.dirname(__file__), "browser_data", "SingletonLock")
if os.path.exists(lock):
    os.remove(lock)


async def screenshot(browser, name):
    path = os.path.join(OUTPUT, f"{name}.png")
    await browser.screenshot(path)
    return path


async def get_all_elements(browser):
    """Get every interactive element on the page."""
    return await browser.evaluate("""() => {
        const els = [];
        document.querySelectorAll('button, [role=slider], input, textarea, select, canvas, svg, [role=switch], [role=checkbox], [role=tab], [role=tabpanel]').forEach(el => {
            if (el.offsetParent === null) return;
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) return;
            els.push({
                tag: el.tagName,
                text: (el.textContent || '').trim().substring(0, 50),
                ariaLabel: el.getAttribute('aria-label'),
                role: el.getAttribute('role'),
                type: el.getAttribute('type'),
                className: typeof el.className === 'string' ? el.className.substring(0, 80) : '',
                id: el.id || '',
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        });
        return els;
    }""")


async def get_right_panel_text(browser):
    """Get all text from right panel."""
    return await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const texts = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            const r = walker.currentNode.parentElement?.getBoundingClientRect();
            if (r && r.left > vw * 0.55 && r.width > 0) {
                const t = walker.currentNode.textContent.trim();
                if (t) texts.push(t);
            }
        }
        return texts.join(' | ');
    }""")


async def search_keywords(browser):
    """Search for EQ/mastering keywords anywhere on page."""
    return await browser.evaluate("""() => {
        const text = document.body.innerText.toLowerCase();
        const keywords = ['eq', 'equalizer', 'frequency', 'gain', 'resonance',
                          'pan', 'panning', 'mute', 'solo', 'bus', 'send',
                          'master', 'mastering', 'preset', 'flat', 'vocal',
                          'warm', 'presence', 'bass boost', 'air', 'clarity',
                          'fullness', 'lo-fi', 'modern', 'high-pass',
                          'low-pass', 'high-shelf', 'low-shelf', 'notch',
                          'bell', 'spectrum', 'analyzer', 'band'];
        const found = {};
        for (const kw of keywords) {
            const idx = text.indexOf(kw);
            if (idx >= 0) {
                found[kw] = text.substring(Math.max(0, idx - 30), idx + 50);
            }
        }
        return found;
    }""")


async def setup_studio(browser):
    """Navigate to studio and ensure clips are on timeline."""
    await browser.navigate("https://suno.com/studio")
    await asyncio.sleep(6)

    text = await browser.evaluate("() => document.body.innerText.substring(0, 2000)")

    # Check if clip already on timeline
    if "Remix" in text and "Sunday" in text:
        print("  Clips already on timeline")
        return True

    # Need to drag a clip
    print("  Dragging clip to timeline...")
    await browser.page.mouse.click(75, 145)
    await asyncio.sleep(1)
    await browser.page.mouse.move(75, 150)
    await browser.page.mouse.down()
    for i in range(15):
        x = 75 + (500 - 75) * (i + 1) / 15
        y = 150 + (350 - 150) * (i + 1) / 15
        await browser.page.mouse.move(x, y)
        await asyncio.sleep(0.03)
    await browser.page.mouse.up()
    await asyncio.sleep(3)

    try:
        await browser.page.click("text=Confirm", timeout=3000)
        await asyncio.sleep(3)
    except Exception:
        pass

    return True


async def explore_clip_tab(browser):
    """Select clip and explore Clip tab."""
    print("\n" + "=" * 60)
    print("CLIP TAB EXPLORATION")
    print("=" * 60)

    # Click a clip on the timeline
    await browser.page.mouse.click(350, 120)
    await asyncio.sleep(2)

    # Make sure Clip tab is active
    try:
        clip_btn = await browser.page.query_selector('button:has-text("Clip")')
        if clip_btn:
            box = await clip_btn.bounding_box()
            if box and box['x'] > 500:
                await clip_btn.click()
                await asyncio.sleep(1)
    except Exception:
        pass

    await screenshot(browser, "clip_tab")

    text = await get_right_panel_text(browser)
    print(f"  Clip tab text: {text[:600]}")

    kw = await search_keywords(browser)
    if kw:
        print(f"  Keywords found: {list(kw.keys())}")
        for k, v in kw.items():
            print(f"    {k}: {v}")

    elements = await get_all_elements(browser)
    right_els = [e for e in elements if e['x'] > 500]
    print(f"  Right panel elements: {len(right_els)}")
    for el in right_els:
        label = el['text'] or el['ariaLabel'] or el['className'][:30]
        print(f"    <{el['tag']}> {label} ({el['x']},{el['y']}) {el['w']}x{el['h']}")

    return elements


async def explore_track_tab(browser):
    """Select clip/track and explore Track tab - THIS IS WHERE EQ LIVES."""
    print("\n" + "=" * 60)
    print("TRACK TAB EXPLORATION (looking for EQ)")
    print("=" * 60)

    # First click a clip to select something
    await browser.page.mouse.click(350, 120)
    await asyncio.sleep(2)

    # Now click the Track tab
    track_btn = None
    btns = await browser.page.query_selector_all('button')
    for btn in btns:
        tc = await btn.text_content()
        box = await btn.bounding_box()
        if tc and tc.strip() == 'Track' and box and box['x'] > 500:
            track_btn = btn
            print(f"  Found Track tab at ({box['x']}, {box['y']})")
            break

    if not track_btn:
        print("  Track tab not found! Trying to find it...")
        # Maybe need to select a track differently
        # Try clicking the track number on the left
        for y in [100, 160, 230]:
            await browser.page.mouse.click(30, y)
            await asyncio.sleep(1)
            btns = await browser.page.query_selector_all('button')
            for btn in btns:
                tc = await btn.text_content()
                box = await btn.bounding_box()
                if tc and tc.strip() == 'Track' and box and box['x'] > 500:
                    track_btn = btn
                    print(f"  Found Track tab after clicking track at y={y}")
                    break
            if track_btn:
                break

    if track_btn:
        await track_btn.click()
        await asyncio.sleep(2)
        await screenshot(browser, "track_tab")

        text = await get_right_panel_text(browser)
        print(f"  Track tab text: {text[:600]}")

        kw = await search_keywords(browser)
        if kw:
            print(f"  Keywords found: {list(kw.keys())}")
            for k, v in kw.items():
                print(f"    {k}: {v}")

        elements = await get_all_elements(browser)
        right_els = [e for e in elements if e['x'] > 500]
        print(f"  Right panel elements: {len(right_els)}")
        for el in right_els:
            label = el['text'] or el['ariaLabel'] or el['className'][:30]
            print(f"    <{el['tag']}> {label} ({el['x']},{el['y']}) {el['w']}x{el['h']}")

        # Look specifically for EQ toggle, presets, frequency graph
        canvases = [e for e in right_els if e['tag'] == 'CANVAS' or e['tag'] == 'SVG']
        sliders = [e for e in elements if e.get('role') == 'slider' or 'slider' in (e.get('className') or '').lower() or 'fader' in (e.get('className') or '').lower()]
        switches = [e for e in right_els if e.get('role') in ('switch', 'checkbox')]

        print(f"\n  Canvases (spectrum analyzer?): {len(canvases)}")
        for c in canvases:
            print(f"    {c['tag']} ({c['x']},{c['y']}) {c['w']}x{c['h']}")
        print(f"  All sliders: {len(sliders)}")
        for s in sliders:
            print(f"    {s.get('ariaLabel', s.get('className', '')[:40])} ({s['x']},{s['y']})")
        print(f"  Switches: {len(switches)}")
        for sw in switches:
            print(f"    {sw.get('ariaLabel', sw.get('text', ''))} ({sw['x']},{sw['y']})")

        return True
    else:
        print("  COULD NOT FIND Track tab anywhere!")
        return False


async def explore_track_header_click(browser):
    """Try clicking different parts of the track header to select a track."""
    print("\n" + "=" * 60)
    print("TRACK HEADER EXPLORATION")
    print("=" * 60)

    # Get all left-side elements
    left_els = await browser.evaluate("""() => {
        const els = [];
        document.querySelectorAll('*').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x < 250 && r.x > 0 && r.y > 60 && r.y < 400 &&
                r.width > 5 && r.height > 5 && el.offsetParent !== null) {
                const text = (el.textContent || '').trim();
                const cls = typeof el.className === 'string' ? el.className : '';
                if (text.length < 50 && (text || cls.includes('track') || cls.includes('fader'))) {
                    els.push({
                        tag: el.tagName,
                        text: text.substring(0, 30),
                        className: cls.substring(0, 60),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
        });
        return els;
    }""")

    print(f"  Left-side elements: {len(left_els)}")
    for el in left_els[:30]:
        print(f"    <{el['tag']}> '{el['text']}' class='{el['className'][:40]}' ({el['x']},{el['y']})")

    # Try clicking on the track name area
    for track_y in [100, 115, 130, 155, 170, 185, 210, 225, 240]:
        await browser.page.mouse.click(120, track_y)
        await asyncio.sleep(1)

        # Check if Track tab appeared in right panel
        right_text = await get_right_panel_text(browser)
        if 'EQ' in right_text or 'Gain' in right_text or 'Pan' in right_text or 'Volume' in right_text:
            print(f"  FOUND mixing controls at y={track_y}!")
            print(f"  Text: {right_text[:300]}")
            await screenshot(browser, f"track_header_y{track_y}")
            return True

        kw = await search_keywords(browser)
        if any(k in kw for k in ['eq', 'gain', 'pan', 'spectrum']):
            print(f"  FOUND EQ keywords at y={track_y}!")
            print(f"  Keywords: {kw}")
            await screenshot(browser, f"eq_found_y{track_y}")
            return True

    return False


async def explore_input_selector(browser):
    """Check the 'No Input' dropdown on each track."""
    print("\n" + "=" * 60)
    print("INPUT SELECTOR / NO INPUT DROPDOWN")
    print("=" * 60)

    try:
        no_input_btns = await browser.page.query_selector_all('button:has-text("No Input")')
        for i, btn in enumerate(no_input_btns):
            box = await btn.bounding_box()
            if box:
                print(f"  No Input button {i} at ({box['x']}, {box['y']})")
                await btn.click()
                await asyncio.sleep(2)
                await screenshot(browser, f"no_input_{i}")

                menus = await browser.evaluate("""() => {
                    const sels = ['[role=menu]', '[role=listbox]', '[data-state=open]',
                                  '[data-radix-popper-content-wrapper]'];
                    const found = [];
                    for (const sel of sels) {
                        document.querySelectorAll(sel).forEach(el => {
                            if (el.offsetParent !== null || el.getAttribute('data-state') === 'open') {
                                found.push(el.textContent.trim().substring(0, 300));
                            }
                        });
                    }
                    return found;
                }""")
                for m in menus:
                    print(f"    Menu: {m}")

                await browser.page.keyboard.press("Escape")
                await asyncio.sleep(1)
                break
    except Exception as e:
        print(f"  Error: {e}")


async def explore_create_page(browser):
    """Explore the Create page controls."""
    print("\n" + "=" * 60)
    print("CREATE PAGE EXPLORATION")
    print("=" * 60)

    await browser.navigate("https://suno.com/create")
    await asyncio.sleep(5)
    await screenshot(browser, "create_simple")

    # Click Custom tab
    try:
        await browser.page.click("text=Custom", timeout=3000)
        await asyncio.sleep(2)
        await screenshot(browser, "create_custom")
    except Exception:
        pass

    # Get all controls
    elements = await get_all_elements(browser)
    print(f"  Total elements: {len(elements)}")

    # Focus on inputs, sliders, textareas
    inputs = [e for e in elements if e['tag'] in ('INPUT', 'TEXTAREA', 'SELECT') or e.get('role') == 'slider']
    print(f"  Input controls: {len(inputs)}")
    for inp in inputs:
        label = inp.get('ariaLabel') or inp.get('text') or inp.get('type') or inp.get('className', '')[:30]
        print(f"    <{inp['tag']}> {label} ({inp['x']},{inp['y']}) {inp['w']}x{inp['h']}")

    # Click Advanced Options
    try:
        adv = await browser.page.query_selector('button:has-text("Advanced")')
        if adv:
            await adv.click()
            await asyncio.sleep(2)
            await screenshot(browser, "create_advanced")

            elements2 = await get_all_elements(browser)
            inputs2 = [e for e in elements2 if e['tag'] in ('INPUT', 'TEXTAREA', 'SELECT') or e.get('role') == 'slider']
            new_inputs = [i for i in inputs2 if i not in inputs]
            print(f"  After Advanced Options - new inputs: {len(new_inputs)}")
            for inp in new_inputs:
                label = inp.get('ariaLabel') or inp.get('text') or inp.get('type') or ''
                print(f"    <{inp['tag']}> {label} ({inp['x']},{inp['y']})")
    except Exception:
        pass

    # Click Sounds tab
    try:
        await browser.page.click("text=Sounds", timeout=3000)
        await asyncio.sleep(2)
        await screenshot(browser, "create_sounds")
    except Exception:
        pass

    await browser.navigate("https://suno.com/studio")
    await asyncio.sleep(5)


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    try:
        await setup_studio(browser)
        await screenshot(browser, "00_studio_ready")

        # Explore everything
        await explore_clip_tab(browser)
        await explore_track_tab(browser)
        await explore_track_header_click(browser)
        await explore_input_selector(browser)
        await explore_create_page(browser)

        # Final: dump all found controls to JSON
        print("\n" + "=" * 60)
        print("SAVING COMPLETE CONTROL MAP")
        print("=" * 60)

        await browser.navigate("https://suno.com/studio")
        await asyncio.sleep(5)

        # Click clip to ensure detail panel is visible
        await browser.page.mouse.click(350, 120)
        await asyncio.sleep(2)

        all_elements = await get_all_elements(browser)
        with open(os.path.join(OUTPUT, "all_controls.json"), "w") as f:
            json.dump(all_elements, f, indent=2)

        print(f"  Saved {len(all_elements)} elements to all_controls.json")
        print(f"  Screenshots saved to {OUTPUT}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await browser.close()


asyncio.run(main())
