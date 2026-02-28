#!/usr/bin/env python3
"""UI calibration script - maps all current Suno Studio element positions.

Launches browser, navigates to Studio, and uses DOM queries to find
the actual positions of all interactive elements. Outputs a JSON report
and takes annotated screenshots.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill


async def calibrate():
    browser = BrowserController()
    if not await browser.connect():
        print("Failed to connect browser")
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)

    # Navigate to Studio
    print("Navigating to Studio...")
    await nav.to_studio()
    await asyncio.sleep(3)
    await modal.dismiss_all()
    await asyncio.sleep(1)

    os.makedirs("/tmp/suno_skills", exist_ok=True)

    # Take baseline screenshot
    await browser.screenshot("/tmp/suno_skills/calibrate_01_studio.png")
    print("Screenshot: /tmp/suno_skills/calibrate_01_studio.png")

    # --- Map all visible elements ---
    report = {}

    # 1. Viewport info
    viewport = await browser.evaluate("""() => ({
        width: window.innerWidth,
        height: window.innerHeight,
    })""")
    report["viewport"] = viewport
    print(f"Viewport: {viewport}")

    # 2. All buttons with positions
    buttons = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('button').forEach(btn => {
            const r = btn.getBoundingClientRect();
            if (r.width > 0 && btn.offsetParent !== null) {
                const text = btn.textContent.trim().substring(0, 50);
                const ariaLabel = btn.getAttribute('aria-label') || '';
                results.push({
                    text, ariaLabel,
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                });
            }
        });
        return results;
    }""") or []
    report["buttons"] = buttons
    print(f"\n--- BUTTONS ({len(buttons)}) ---")
    for b in buttons:
        print(f"  [{b['cx']:4d},{b['cy']:4d}] {b['w']:3d}x{b['h']:3d}  text='{b['text'][:30]}'  aria='{b['ariaLabel'][:30]}'")

    # 3. All input fields
    inputs = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('input, textarea').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && el.offsetParent !== null) {
                results.push({
                    type: el.type || el.tagName.toLowerCase(),
                    placeholder: el.placeholder || '',
                    value: el.value || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        });
        return results;
    }""") or []
    report["inputs"] = inputs
    print(f"\n--- INPUTS ({len(inputs)}) ---")
    for i in inputs:
        print(f"  [{i['x']:4d},{i['y']:4d}] {i['w']:3d}x{i['h']:3d}  type={i['type']}  ph='{i['placeholder'][:30]}'  val='{i['value'][:20]}'")

    # 4. Track list items (look for track numbers, names, controls)
    tracks = await browser.evaluate("""() => {
        const results = [];
        // Track numbers are usually buttons with just a digit
        document.querySelectorAll('button').forEach(btn => {
            const text = btn.textContent.trim();
            const r = btn.getBoundingClientRect();
            if (/^\\d+$/.test(text) && r.y > 60 && r.y < 800 && r.width < 50) {
                results.push({
                    trackNum: parseInt(text),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                });
            }
        });
        return results.sort((a, b) => a.trackNum - b.trackNum);
    }""") or []
    report["track_numbers"] = tracks
    print(f"\n--- TRACK NUMBERS ({len(tracks)}) ---")
    for t in tracks:
        print(f"  Track {t['trackNum']}: [{t['cx']:4d},{t['cy']:4d}] {t['w']}x{t['h']}")

    # 5. Waveform/canvas elements
    canvases = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('canvas').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && el.offsetParent !== null) {
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    id: el.id || '',
                    className: (el.className || '').substring(0, 60),
                });
            }
        });
        return results;
    }""") or []
    report["canvases"] = canvases
    print(f"\n--- CANVASES ({len(canvases)}) ---")
    for c in canvases:
        print(f"  [{c['x']:4d},{c['y']:4d}] {c['w']:4d}x{c['h']:4d}  id='{c['id']}'  class='{c['className'][:40]}'")

    # 6. SVG elements (for faders, knobs, etc.)
    svgs = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('svg').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 20 && r.height > 20 && el.offsetParent !== null) {
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    ariaLabel: el.getAttribute('aria-label') || '',
                    role: el.getAttribute('role') || '',
                });
            }
        });
        return results;
    }""") or []
    report["svgs"] = svgs
    print(f"\n--- SVGs ({len(svgs)}) ---")
    for s in svgs:
        if s['ariaLabel'] or s['role']:
            print(f"  [{s['x']:4d},{s['y']:4d}] {s['w']:3d}x{s['h']:3d}  aria='{s['ariaLabel'][:30]}'  role='{s['role']}'")

    # 7. Images (sidebar thumbnails)
    images = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('img').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 20 && r.height > 20 && el.offsetParent !== null) {
                const src = el.src || '';
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    alt: el.alt || '',
                    src: src.substring(src.lastIndexOf('/') + 1, src.lastIndexOf('/') + 31),
                });
            }
        });
        return results;
    }""") or []
    report["images"] = images
    print(f"\n--- IMAGES ({len(images)}) ---")
    for img in images:
        print(f"  [{img['x']:4d},{img['y']:4d}] {img['w']:3d}x{img['h']:3d}  alt='{img['alt'][:30]}'")

    # 8. Fader-knob elements
    faders = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('[class*=fader], [class*=knob], [role=slider]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && el.offsetParent !== null) {
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    className: (el.className || '').substring(0, 60),
                    ariaLabel: el.getAttribute('aria-label') || '',
                    ariaValue: el.getAttribute('aria-valuenow') || '',
                });
            }
        });
        return results;
    }""") or []
    report["faders"] = faders
    print(f"\n--- FADERS/SLIDERS ({len(faders)}) ---")
    for f in faders:
        print(f"  [{f['x']:4d},{f['y']:4d}] {f['w']:3d}x{f['h']:3d}  class='{f['className'][:40]}'  val='{f['ariaValue']}'")

    # 9. Right panel contents (if a clip is selected)
    right_panel = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const items = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            const r = walker.currentNode.parentElement?.getBoundingClientRect();
            if (r && r.left > vw * 0.7 && r.width > 0) {
                const t = walker.currentNode.textContent.trim();
                if (t && t.length > 0) {
                    items.push({
                        text: t.substring(0, 60),
                        x: Math.round(r.left), y: Math.round(r.top),
                    });
                }
            }
        }
        return items;
    }""") or []
    report["right_panel_text"] = right_panel
    print(f"\n--- RIGHT PANEL TEXT ({len(right_panel)}) ---")
    for item in right_panel[:30]:
        print(f"  [{item['x']:4d},{item['y']:4d}] '{item['text'][:50]}'")

    # 10. Export button area
    export_info = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('button, [role=menuitem], [role=button]').forEach(el => {
            const text = el.textContent.trim().toLowerCase();
            const r = el.getBoundingClientRect();
            if (r.width > 0 && el.offsetParent !== null &&
                (text.includes('export') || text.includes('download') || text.includes('share'))) {
                results.push({
                    text: el.textContent.trim(),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                    tag: el.tagName,
                });
            }
        });
        return results;
    }""") or []
    report["export_buttons"] = export_info
    print(f"\n--- EXPORT/DOWNLOAD BUTTONS ({len(export_info)}) ---")
    for e in export_info:
        print(f"  [{e['cx']:4d},{e['cy']:4d}] {e['w']:3d}x{e['h']:3d}  text='{e['text'][:40]}'")

    # 11. Switch/toggle elements
    switches = await browser.evaluate("""() => {
        const results = [];
        document.querySelectorAll('[role=switch], [type=checkbox]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && el.offsetParent !== null) {
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    checked: el.getAttribute('aria-checked') || el.checked || false,
                    ariaLabel: el.getAttribute('aria-label') || '',
                });
            }
        });
        return results;
    }""") or []
    report["switches"] = switches
    print(f"\n--- SWITCHES ({len(switches)}) ---")
    for s in switches:
        print(f"  [{s['x']:4d},{s['y']:4d}] {s['w']:3d}x{s['h']:3d}  checked={s['checked']}  aria='{s['ariaLabel']}'")

    # Now try to click a clip to see right panel with EQ
    # First find clickable waveform areas
    print("\n\n=== ATTEMPTING CLIP SELECTION ===")

    # Find clip elements on timeline
    clips = await browser.evaluate("""() => {
        const results = [];
        // Look for clip containers in the timeline area
        document.querySelectorAll('[class*=clip], [class*=wave], [data-testid*=clip]').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 50 && r.height > 20 && r.x > 300 && r.y > 60 && el.offsetParent !== null) {
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                    tag: el.tagName,
                    className: (el.className || '').substring(0, 80),
                });
            }
        });
        return results;
    }""") or []
    report["clip_elements"] = clips
    print(f"Found {len(clips)} clip-like elements")
    for c in clips:
        print(f"  [{c['x']:4d},{c['y']:4d}] {c['w']:4d}x{c['h']:3d}  tag={c['tag']}  class='{c['className'][:60]}'")

    # Try clicking first canvas/waveform area that's likely a clip
    # Look for canvases in the timeline zone (middle of screen)
    timeline_canvases = [c for c in canvases if c['x'] > 300 and c['y'] > 80 and c['w'] > 50]
    if timeline_canvases:
        tc = timeline_canvases[0]
        click_x = tc['x'] + tc['w'] // 2
        click_y = tc['y'] + tc['h'] // 2
        print(f"\nClicking timeline canvas at ({click_x}, {click_y})...")
        await browser.page.mouse.click(click_x, click_y)
        await asyncio.sleep(2)

        await browser.screenshot("/tmp/suno_skills/calibrate_02_clip_selected.png")
        print("Screenshot: /tmp/suno_skills/calibrate_02_clip_selected.png")

        # Re-read right panel
        right_panel2 = await browser.evaluate("""() => {
            const vw = window.innerWidth;
            const items = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const r = walker.currentNode.parentElement?.getBoundingClientRect();
                if (r && r.left > vw * 0.7 && r.width > 0) {
                    const t = walker.currentNode.textContent.trim();
                    if (t && t.length > 0) {
                        items.push({
                            text: t.substring(0, 60),
                            x: Math.round(r.left), y: Math.round(r.top),
                        });
                    }
                }
            }
            return items;
        }""") or []
        report["right_panel_after_click"] = right_panel2
        print(f"\n--- RIGHT PANEL AFTER CLICK ({len(right_panel2)}) ---")
        for item in right_panel2[:30]:
            print(f"  [{item['x']:4d},{item['y']:4d}] '{item['text'][:50]}'")

        # Check if we got Clip/Track tabs
        has_clip_track = any('Clip' in item['text'] or 'Track' in item['text'] for item in right_panel2)
        print(f"\nClip/Track tabs visible: {has_clip_track}")

        if has_clip_track:
            # Click on Track tab to see EQ
            track_tab = await browser.evaluate("""() => {
                const buttons = document.querySelectorAll('button');
                for (const btn of buttons) {
                    if (btn.textContent.trim() === 'Track') {
                        const r = btn.getBoundingClientRect();
                        if (r.x > window.innerWidth * 0.7) {
                            return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                        }
                    }
                }
                return null;
            }""")

            if track_tab:
                print(f"\nClicking Track tab at ({track_tab['x']}, {track_tab['y']})...")
                await browser.page.mouse.click(track_tab['x'], track_tab['y'])
                await asyncio.sleep(2)

                await browser.screenshot("/tmp/suno_skills/calibrate_03_track_tab.png")
                print("Screenshot: /tmp/suno_skills/calibrate_03_track_tab.png")

                # Map EQ elements
                eq_elements = await browser.evaluate("""() => {
                    const vw = window.innerWidth;
                    const results = {buttons: [], inputs: [], switches: [], canvases: []};

                    // Buttons in right panel
                    document.querySelectorAll('button').forEach(btn => {
                        const r = btn.getBoundingClientRect();
                        if (r.x > vw * 0.7 && r.width > 0 && btn.offsetParent !== null) {
                            results.buttons.push({
                                text: btn.textContent.trim().substring(0, 40),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                                cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                            });
                        }
                    });

                    // Inputs in right panel
                    document.querySelectorAll('input').forEach(inp => {
                        const r = inp.getBoundingClientRect();
                        if (r.x > vw * 0.7 && r.width > 0 && inp.offsetParent !== null) {
                            results.inputs.push({
                                type: inp.type,
                                value: inp.value || '',
                                placeholder: inp.placeholder || '',
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                            });
                        }
                    });

                    // Switches
                    document.querySelectorAll('[role=switch]').forEach(sw => {
                        const r = sw.getBoundingClientRect();
                        if (r.x > vw * 0.7 && r.width > 0) {
                            results.switches.push({
                                checked: sw.getAttribute('aria-checked'),
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                            });
                        }
                    });

                    // Canvases in right panel
                    document.querySelectorAll('canvas').forEach(el => {
                        const r = el.getBoundingClientRect();
                        if (r.x > vw * 0.7 && r.width > 0 && el.offsetParent !== null) {
                            results.canvases.push({
                                x: Math.round(r.x), y: Math.round(r.y),
                                w: Math.round(r.width), h: Math.round(r.height),
                            });
                        }
                    });

                    return results;
                }""") or {}

                report["eq_panel"] = eq_elements
                print(f"\n--- EQ PANEL ELEMENTS ---")
                print(f"Buttons: {len(eq_elements.get('buttons', []))}")
                for b in eq_elements.get('buttons', []):
                    print(f"  [{b['cx']:4d},{b['cy']:4d}] {b['w']:3d}x{b['h']:3d}  text='{b['text'][:30]}'")
                print(f"Inputs: {len(eq_elements.get('inputs', []))}")
                for i in eq_elements.get('inputs', []):
                    print(f"  [{i['x']:4d},{i['y']:4d}] {i['w']:3d}x{i['h']:3d}  val='{i['value']}'")
                print(f"Switches: {len(eq_elements.get('switches', []))}")
                for s in eq_elements.get('switches', []):
                    print(f"  [{s['x']:4d},{s['y']:4d}] {s['w']:3d}x{s['h']:3d}  checked={s['checked']}")
                print(f"Canvases: {len(eq_elements.get('canvases', []))}")
                for c in eq_elements.get('canvases', []):
                    print(f"  [{c['x']:4d},{c['y']:4d}] {c['w']:4d}x{c['h']:3d}")

    # Save full report
    report_path = "/tmp/suno_skills/calibrate_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nFull report saved: {report_path}")

    await browser.close()
    print("\nDone!")


if __name__ == "__main__":
    asyncio.run(calibrate())
