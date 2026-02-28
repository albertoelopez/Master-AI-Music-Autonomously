#!/usr/bin/env python3
"""Map the Track tab EQ controls in Suno Studio.
Dismisses any modal overlay first, then clicks Track tab and maps every EQ element.
Retries aggressively - loops until successful."""
import asyncio
import json
import os
import time
from src.browser import BrowserController

OUTPUT = "/tmp/suno_eq"
os.makedirs(OUTPUT, exist_ok=True)

# Remove stale lock
lock = os.path.join(os.path.dirname(__file__), "browser_data", "SingletonLock")
if os.path.exists(lock):
    os.remove(lock)


async def screenshot(browser, name):
    path = os.path.join(OUTPUT, f"{name}.png")
    await browser.screenshot(path)
    return path


async def dismiss_modals(browser):
    """Aggressively dismiss any modal/overlay/dialog blocking the UI."""
    print("\n--- Dismissing modals ---")

    # Method 1: Press Escape multiple times
    for i in range(3):
        await browser.page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

    # Method 2: Click any close/X buttons on modals
    closed = await browser.evaluate("""() => {
        const results = [];

        // Find modals/overlays
        const modals = document.querySelectorAll('[class*=modal], [class*=overlay], [class*=dialog], [role=dialog], [data-state=open]');
        results.push('Found ' + modals.length + ' modal-like elements');

        // Try clicking close buttons inside modals
        for (const modal of modals) {
            const closeBtn = modal.querySelector('button[aria-label*=close], button[aria-label*=Close], button:has(svg), [class*=close]');
            if (closeBtn) {
                closeBtn.click();
                results.push('Clicked close button in: ' + modal.className.substring(0, 50));
            }
        }

        // Try removing high z-index overlays directly
        document.querySelectorAll('[style*="z-index"]').forEach(el => {
            const z = parseInt(window.getComputedStyle(el).zIndex);
            if (z > 9999 && el.offsetParent !== null) {
                results.push('Found high-z element: ' + el.className.substring(0, 50) + ' z=' + z);
            }
        });

        // Find and click any "backdrop" overlay
        document.querySelectorAll('[class*=backdrop], [class*=Backdrop]').forEach(el => {
            if (el.offsetParent !== null) {
                el.click();
                results.push('Clicked backdrop: ' + el.className.substring(0, 50));
            }
        });

        return results;
    }""")

    for msg in (closed or []):
        print(f"  {msg}")

    # Method 3: Force-remove any fixed overlays via DOM
    removed = await browser.evaluate("""() => {
        let removed = 0;
        document.querySelectorAll('*').forEach(el => {
            const style = window.getComputedStyle(el);
            const z = parseInt(style.zIndex);
            if (z > 50000 && style.position === 'fixed') {
                el.style.display = 'none';
                removed++;
            }
        });
        return removed;
    }""")
    print(f"  Force-hid {removed} high-z fixed elements")

    await asyncio.sleep(1)

    # Verify no blocking overlays remain
    blocking = await browser.evaluate("""() => {
        const center = document.elementFromPoint(640, 400);
        return center ? {
            tag: center.tagName,
            className: (typeof center.className === 'string' ? center.className : '').substring(0, 80),
            text: (center.textContent || '').trim().substring(0, 100)
        } : null;
    }""")
    print(f"  Center element after dismissal: {blocking}")
    return blocking


async def ensure_clip_on_timeline(browser):
    """Make sure at least one clip is on the timeline."""
    print("\n--- Ensuring clip on timeline ---")

    # Check if any clips exist on timeline
    has_clips = await browser.evaluate("""() => {
        // Look for waveform/clip elements in the timeline area
        const clips = document.querySelectorAll('[class*=clip], [class*=waveform], [class*=region]');
        const timelineClips = [];
        clips.forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > 200 && r.x < 900 && r.y > 60 && r.y < 500 && r.width > 50) {
                timelineClips.push({tag: el.tagName, x: r.x, y: r.y, w: r.width, cls: (typeof el.className === 'string' ? el.className : '').substring(0,50)});
            }
        });
        return timelineClips;
    }""")

    if has_clips and len(has_clips) > 0:
        print(f"  Found {len(has_clips)} clips on timeline")
        return True

    # Check for clips by looking for audio waveform canvases
    canvases = await browser.evaluate("""() => {
        const items = [];
        document.querySelectorAll('canvas').forEach(c => {
            const r = c.getBoundingClientRect();
            if (r.x > 200 && r.width > 100 && r.y > 60 && r.y < 500) {
                items.push({x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)});
            }
        });
        return items;
    }""")

    if canvases and len(canvases) > 0:
        print(f"  Found {len(canvases)} canvases in timeline area (clips likely present)")
        return True

    # Need to drag a clip from sidebar
    print("  No clips found - dragging from sidebar...")

    # Find sidebar thumbnails
    sidebar = await browser.evaluate("""() => {
        const items = [];
        document.querySelectorAll('img, [class*=thumbnail], [class*=artwork]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x < 150 && r.y > 60 && r.width > 20 && r.height > 20 && el.offsetParent !== null) {
                items.push({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), w: Math.round(r.width)});
            }
        });
        return items;
    }""")

    if sidebar and len(sidebar) > 0:
        src = sidebar[0]
        print(f"  Dragging from ({src['x']}, {src['y']}) to timeline...")
        await browser.page.mouse.move(src['x'], src['y'])
        await asyncio.sleep(0.5)
        await browser.page.mouse.down()
        for i in range(20):
            x = src['x'] + (500 - src['x']) * (i + 1) / 20
            y = src['y'] + (300 - src['y']) * (i + 1) / 20
            await browser.page.mouse.move(x, y)
            await asyncio.sleep(0.03)
        await browser.page.mouse.up()
        await asyncio.sleep(3)

        # Confirm tempo dialog if it appears
        try:
            await browser.page.click("text=Confirm", timeout=3000)
            print("  Clicked Confirm on tempo dialog")
            await asyncio.sleep(3)
        except Exception:
            pass

        return True

    print("  WARNING: No sidebar items to drag!")
    return False


async def click_clip_on_timeline(browser):
    """Click a clip on the timeline to select it."""
    print("\n--- Clicking clip on timeline ---")

    # Find clickable areas in the timeline (between track controls and right panel)
    # Timeline area is roughly x: 250-950, y: 80-500
    for y in [120, 180, 250, 330, 400]:
        for x in [400, 500, 600, 700]:
            await browser.page.mouse.click(x, y)
            await asyncio.sleep(1)

            # Check if right panel now shows clip info
            right_text = await browser.evaluate("""() => {
                const vw = window.innerWidth;
                const texts = [];
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                while (walker.nextNode()) {
                    const r = walker.currentNode.parentElement?.getBoundingClientRect();
                    if (r && r.left > vw * 0.7 && r.width > 0) {
                        const t = walker.currentNode.textContent.trim();
                        if (t) texts.push(t);
                    }
                }
                return texts.join(' | ');
            }""")

            if 'Clip' in right_text and 'Track' in right_text:
                print(f"  Selected clip at ({x}, {y})")
                print(f"  Right panel shows: {right_text[:200]}")
                return True

    print("  Could not select a clip")
    return False


async def click_track_tab(browser):
    """Click the Track tab in the right panel."""
    print("\n--- Clicking Track tab ---")

    # Find the Track tab button (should be in right panel, after Clip tab)
    track_btn = await browser.evaluate("""() => {
        const buttons = document.querySelectorAll('button');
        for (const btn of buttons) {
            const text = btn.textContent.trim();
            const r = btn.getBoundingClientRect();
            // Track tab should be in right panel area (x > 900) and near top (y < 100)
            if (text === 'Track' && r.x > 900 && r.y < 150 && r.width > 30) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), w: Math.round(r.width)};
            }
        }
        // Broader search
        for (const btn of buttons) {
            const text = btn.textContent.trim();
            const r = btn.getBoundingClientRect();
            if (text === 'Track' && r.x > 500 && r.width > 30) {
                return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), w: Math.round(r.width)};
            }
        }
        return null;
    }""")

    if not track_btn:
        print("  Track tab button not found!")
        # List all buttons for debugging
        buttons = await browser.evaluate("""() => {
            const bs = [];
            document.querySelectorAll('button').forEach(btn => {
                const r = btn.getBoundingClientRect();
                if (r.x > 500 && r.y < 200 && r.width > 20 && btn.offsetParent !== null) {
                    bs.push({text: btn.textContent.trim().substring(0, 30), x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width)});
                }
            });
            return bs;
        }""")
        print(f"  Right-side top buttons: {json.dumps(buttons, indent=2)}")
        return False

    print(f"  Found Track tab at ({track_btn['x']}, {track_btn['y']})")
    await browser.page.mouse.click(track_btn['x'], track_btn['y'])
    await asyncio.sleep(2)

    # Verify we're on the Track tab
    track_content = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const texts = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            const r = walker.currentNode.parentElement?.getBoundingClientRect();
            if (r && r.left > vw * 0.7 && r.width > 0) {
                const t = walker.currentNode.textContent.trim();
                if (t) texts.push(t);
            }
        }
        return texts.join(' | ');
    }""")

    print(f"  Track tab content: {track_content[:500]}")
    return True


async def map_eq_controls(browser):
    """Exhaustively map every EQ control on the Track tab."""
    print("\n" + "=" * 60)
    print("MAPPING EQ CONTROLS")
    print("=" * 60)

    await screenshot(browser, "track_tab_full")

    # Get ALL interactive elements in the right panel
    elements = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const els = [];
        document.querySelectorAll('button, [role=slider], input, select, canvas, svg, [role=switch], [role=checkbox], [role=tab], [role=tabpanel], [role=combobox], [role=listbox], [class*=knob], [class*=fader], [class*=slider]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > vw * 0.65 && r.width > 0 && r.height > 0 && el.offsetParent !== null) {
                els.push({
                    tag: el.tagName,
                    text: (el.textContent || '').trim().substring(0, 60),
                    ariaLabel: el.getAttribute('aria-label'),
                    role: el.getAttribute('role'),
                    type: el.getAttribute('type'),
                    className: typeof el.className === 'string' ? el.className.substring(0, 100) : '',
                    id: el.id || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    value: el.value || el.getAttribute('aria-valuenow') || '',
                    min: el.getAttribute('aria-valuemin') || el.min || '',
                    max: el.getAttribute('aria-valuemax') || el.max || '',
                });
            }
        });
        return els;
    }""")

    print(f"\nRight panel interactive elements: {len(elements)}")
    for el in elements:
        label = el['text'] or el['ariaLabel'] or el['className'][:40]
        vals = f" val={el['value']}" if el['value'] else ""
        rng = f" [{el['min']}-{el['max']}]" if el['min'] or el['max'] else ""
        print(f"  <{el['tag']}> {el['role'] or ''} {label} ({el['x']},{el['y']}) {el['w']}x{el['h']}{vals}{rng}")

    # Search for EQ-specific keywords
    eq_keywords = await browser.evaluate("""() => {
        const text = document.body.innerText.toLowerCase();
        const keywords = ['eq', 'equalizer', 'frequency', 'gain', 'resonance', 'q factor',
                          'spectrum', 'analyzer', 'band', 'preset', 'flat', 'vocal', 'warm',
                          'presence', 'bass boost', 'air', 'clarity', 'fullness', 'lo-fi',
                          'modern', 'high-pass', 'low-pass', 'high-shelf', 'low-shelf',
                          'notch', 'bell', 'peak', 'hz', 'khz', 'db'];
        const found = {};
        for (const kw of keywords) {
            const idx = text.indexOf(kw);
            if (idx >= 0) {
                found[kw] = text.substring(Math.max(0, idx - 20), idx + 40);
            }
        }
        return found;
    }""")

    print(f"\nEQ keywords found: {len(eq_keywords)}")
    for k, v in eq_keywords.items():
        print(f"  {k}: ...{v}...")

    # Look for canvases (spectrum analyzer, EQ curve graph)
    canvases = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        document.querySelectorAll('canvas').forEach(c => {
            const r = c.getBoundingClientRect();
            if (r.x > vw * 0.65 && r.width > 50) {
                items.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    id: c.id || '',
                    className: typeof c.className === 'string' ? c.className.substring(0, 80) : '',
                });
            }
        });
        return items;
    }""")

    print(f"\nCanvases in right panel (spectrum/EQ graph): {len(canvases)}")
    for c in canvases:
        print(f"  Canvas ({c['x']},{c['y']}) {c['w']}x{c['h']} id={c['id']} class={c['className']}")

    # Look for sliders/knobs specifically (EQ band controls)
    sliders = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        document.querySelectorAll('[role=slider], input[type=range], [class*=knob], [class*=slider], [class*=dial]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > vw * 0.5 && r.width > 0 && el.offsetParent !== null) {
                items.push({
                    tag: el.tagName,
                    ariaLabel: el.getAttribute('aria-label'),
                    value: el.value || el.getAttribute('aria-valuenow') || '',
                    min: el.getAttribute('aria-valuemin') || el.min || '',
                    max: el.getAttribute('aria-valuemax') || el.max || '',
                    className: typeof el.className === 'string' ? el.className.substring(0, 80) : '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        });
        return items;
    }""")

    print(f"\nSliders/knobs in right half: {len(sliders)}")
    for s in sliders:
        print(f"  {s['ariaLabel'] or s['className'][:40]} val={s['value']} [{s['min']}-{s['max']}] ({s['x']},{s['y']}) {s['w']}x{s['h']}")

    # Look for switches/toggles (EQ enable/disable)
    switches = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        document.querySelectorAll('[role=switch], [role=checkbox], [type=checkbox]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > vw * 0.5 && r.width > 0 && el.offsetParent !== null) {
                items.push({
                    tag: el.tagName,
                    ariaLabel: el.getAttribute('aria-label'),
                    checked: el.checked || el.getAttribute('aria-checked'),
                    className: typeof el.className === 'string' ? el.className.substring(0, 80) : '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        });
        return items;
    }""")

    print(f"\nSwitches/toggles: {len(switches)}")
    for sw in switches:
        print(f"  {sw['ariaLabel'] or sw['className'][:40]} checked={sw['checked']} ({sw['x']},{sw['y']})")

    # Look for dropdowns (EQ preset selector)
    dropdowns = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        document.querySelectorAll('select, [role=combobox], [role=listbox], button').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > vw * 0.65 && r.width > 60 && el.offsetParent !== null) {
                const text = el.textContent.trim();
                // Look for preset-like names
                if (['Flat', 'Vocal', 'Warm', 'Presence', 'Bass Boost', 'Air', 'Clarity',
                     'Fullness', 'Lo-fi', 'Modern', 'High-pass', 'Reset'].some(p => text.includes(p)) ||
                    el.getAttribute('role') === 'combobox' || el.tagName === 'SELECT') {
                    items.push({
                        tag: el.tagName,
                        text: text.substring(0, 50),
                        role: el.getAttribute('role'),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
        });
        return items;
    }""")

    print(f"\nPreset dropdowns: {len(dropdowns)}")
    for d in dropdowns:
        print(f"  <{d['tag']}> '{d['text']}' ({d['x']},{d['y']}) {d['w']}x{d['h']}")

    # Look for numbered buttons (EQ bands 1-6)
    band_buttons = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        document.querySelectorAll('button').forEach(btn => {
            const r = btn.getBoundingClientRect();
            if (r.x > vw * 0.65 && r.width > 0 && btn.offsetParent !== null) {
                const text = btn.textContent.trim();
                if (['1', '2', '3', '4', '5', '6'].includes(text) ||
                    text.match(/^Band\s*\d/) ||
                    (btn.getAttribute('aria-label') || '').match(/band/i)) {
                    items.push({
                        text: text,
                        ariaLabel: btn.getAttribute('aria-label'),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                    });
                }
            }
        });
        return items;
    }""")

    print(f"\nBand buttons (1-6): {len(band_buttons)}")
    for b in band_buttons:
        print(f"  '{b['text']}' {b.get('ariaLabel', '')} ({b['x']},{b['y']})")

    # Get FULL DOM tree of right panel for deep inspection
    right_panel_html = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        // Find the main right panel container
        let rightPanel = null;
        document.querySelectorAll('div, section, aside').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > vw * 0.7 && r.width > 200 && r.height > 400 && !rightPanel) {
                rightPanel = el;
            }
        });
        if (rightPanel) {
            return rightPanel.innerHTML.substring(0, 5000);
        }
        return 'No right panel found';
    }""")

    # Save raw HTML for analysis
    with open(os.path.join(OUTPUT, "right_panel.html"), "w") as f:
        f.write(right_panel_html)
    print(f"\nRight panel HTML saved ({len(right_panel_html)} chars)")

    # Try scrolling the right panel to reveal more controls
    await browser.evaluate("""() => {
        const vw = window.innerWidth;
        document.querySelectorAll('div').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > vw * 0.7 && r.height > 300 && el.scrollHeight > el.clientHeight) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }""")
    await asyncio.sleep(1)
    await screenshot(browser, "track_tab_scrolled")

    # Map elements after scroll
    after_scroll = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const els = [];
        document.querySelectorAll('button, [role=slider], input, canvas, [role=switch]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x > vw * 0.65 && r.width > 0 && r.height > 0 && el.offsetParent !== null) {
                els.push({
                    tag: el.tagName,
                    text: (el.textContent || '').trim().substring(0, 40),
                    ariaLabel: el.getAttribute('aria-label'),
                    role: el.getAttribute('role'),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        });
        return els;
    }""")

    new_els = [e for e in after_scroll if e['y'] > 600]
    if new_els:
        print(f"\nElements revealed by scrolling: {len(new_els)}")
        for el in new_els:
            print(f"  <{el['tag']}> {el['text'] or el['ariaLabel'] or ''} ({el['x']},{el['y']})")

    return {
        'elements': elements,
        'keywords': eq_keywords,
        'canvases': canvases,
        'sliders': sliders,
        'switches': switches,
        'dropdowns': dropdowns,
        'band_buttons': band_buttons,
    }


async def try_eq_preset_cycle(browser):
    """Try clicking through EQ presets to see them all."""
    print("\n--- Trying EQ preset navigation ---")

    # Look for arrow buttons near preset text (left/right arrows for cycling presets)
    arrows = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        document.querySelectorAll('button').forEach(btn => {
            const r = btn.getBoundingClientRect();
            if (r.x > vw * 0.65 && r.width < 50 && r.width > 10 && btn.offsetParent !== null) {
                const svg = btn.querySelector('svg');
                const text = btn.textContent.trim();
                if (svg || text === '<' || text === '>' || text === '←' || text === '→' ||
                    (btn.getAttribute('aria-label') || '').match(/prev|next|left|right|arrow/i)) {
                    items.push({
                        text: text.substring(0, 20),
                        ariaLabel: btn.getAttribute('aria-label'),
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        hasSvg: !!svg,
                    });
                }
            }
        });
        return items;
    }""")

    print(f"  Arrow buttons found: {len(arrows)}")
    for a in arrows:
        print(f"    '{a['text']}' svg={a['hasSvg']} ({a['x']},{a['y']}) {a['w']}x{a['h']}")

    # Try clicking right arrow to cycle presets
    for arrow in arrows:
        if arrow['x'] > 1100:  # Rightmost arrow likely "next preset"
            print(f"  Clicking arrow at ({arrow['x']}, {arrow['y']})...")
            for i in range(12):
                await browser.page.mouse.click(arrow['x'], arrow['y'])
                await asyncio.sleep(0.8)

                # Get current preset name
                preset_text = await browser.evaluate(f"""() => {{
                    const btns = document.querySelectorAll('button');
                    for (const btn of btns) {{
                        const r = btn.getBoundingClientRect();
                        if (r.x > {arrow['x'] - 150} && r.x < {arrow['x']} &&
                            Math.abs(r.y - {arrow['y']}) < 20 && r.width > 40) {{
                            return btn.textContent.trim();
                        }}
                    }}
                    return null;
                }}""")
                if preset_text:
                    print(f"    Preset {i+1}: {preset_text}")
            break


async def try_clicking_eq_bands(browser):
    """Try clicking each EQ band button to see band-specific controls."""
    print("\n--- Trying EQ band selection ---")

    # Find band buttons
    bands = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        document.querySelectorAll('button').forEach(btn => {
            const r = btn.getBoundingClientRect();
            const text = btn.textContent.trim();
            if (r.x > vw * 0.65 && ['1','2','3','4','5','6'].includes(text) &&
                r.width < 60 && r.height < 60 && btn.offsetParent !== null) {
                items.push({
                    text: text,
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                });
            }
        });
        return items.sort((a,b) => parseInt(a.text) - parseInt(b.text));
    }""")

    print(f"  Found {len(bands)} band buttons")

    for band in bands:
        print(f"\n  Clicking Band {band['text']}...")
        await browser.page.mouse.click(band['x'], band['y'])
        await asyncio.sleep(1)

        # Get the controls that appear for this band
        controls = await browser.evaluate("""() => {
            const vw = window.innerWidth;
            const items = [];
            document.querySelectorAll('[role=slider], input[type=number], input[type=range], [class*=knob]').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.x > vw * 0.65 && r.width > 0 && el.offsetParent !== null) {
                    items.push({
                        tag: el.tagName,
                        ariaLabel: el.getAttribute('aria-label'),
                        value: el.value || el.getAttribute('aria-valuenow') || '',
                        className: typeof el.className === 'string' ? el.className.substring(0, 60) : '',
                        x: Math.round(r.x), y: Math.round(r.y),
                    });
                }
            });
            return items;
        }""")

        for c in controls:
            print(f"    {c['ariaLabel'] or c['className'][:30]} = {c['value']} ({c['x']},{c['y']})")

        await screenshot(browser, f"eq_band_{band['text']}")


async def main():
    MAX_ATTEMPTS = 3

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"\n{'#' * 60}")
        print(f"ATTEMPT {attempt}/{MAX_ATTEMPTS}")
        print(f"{'#' * 60}")

        browser = BrowserController()
        if not await browser.connect():
            print("Failed to connect browser, retrying...")
            await asyncio.sleep(3)
            continue

        try:
            # Navigate to Studio
            await browser.navigate("https://suno.com/studio")
            await asyncio.sleep(8)
            await screenshot(browser, f"attempt{attempt}_00_loaded")

            # Step 1: Dismiss any modals
            await dismiss_modals(browser)
            await screenshot(browser, f"attempt{attempt}_01_modals_dismissed")

            # Step 2: Ensure clip on timeline
            await ensure_clip_on_timeline(browser)
            await asyncio.sleep(2)

            # Step 3: Click a clip to select it
            selected = await click_clip_on_timeline(browser)
            if not selected:
                print("  Failed to select clip, trying direct click...")
                # Try clicking directly in known clip area
                await browser.page.mouse.click(450, 120)
                await asyncio.sleep(2)

            await screenshot(browser, f"attempt{attempt}_02_clip_selected")

            # Step 4: Dismiss modals AGAIN (they can reappear)
            await dismiss_modals(browser)

            # Step 5: Click Track tab
            success = await click_track_tab(browser)
            await screenshot(browser, f"attempt{attempt}_03_track_tab")

            if success:
                # Step 6: Map ALL EQ controls
                eq_data = await map_eq_controls(browser)

                # Step 7: Try cycling presets
                await try_eq_preset_cycle(browser)

                # Step 8: Try clicking individual bands
                await try_clicking_eq_bands(browser)

                # Save complete data
                with open(os.path.join(OUTPUT, "eq_controls.json"), "w") as f:
                    json.dump(eq_data, f, indent=2, default=str)
                print(f"\nEQ control data saved to {OUTPUT}/eq_controls.json")

                await screenshot(browser, f"attempt{attempt}_final")
                print(f"\n{'=' * 60}")
                print("SUCCESS - EQ controls mapped!")
                print(f"Screenshots and data in {OUTPUT}")
                print(f"{'=' * 60}")
                break
            else:
                print(f"  Attempt {attempt} failed to reach Track tab")

        except Exception as e:
            print(f"ERROR in attempt {attempt}: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await browser.close()
            # Clean lock for next attempt
            if os.path.exists(lock):
                os.remove(lock)
            await asyncio.sleep(2)
    else:
        print(f"\nFailed after {MAX_ATTEMPTS} attempts")


asyncio.run(main())
