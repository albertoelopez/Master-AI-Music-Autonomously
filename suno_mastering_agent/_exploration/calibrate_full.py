#!/usr/bin/env python3
"""Full UI calibration - drag clips, map tracks, select clip, map EQ panel."""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController


async def calibrate():
    browser = BrowserController()
    if not await browser.connect():
        print("Failed to connect browser")
        return

    page = browser.page
    os.makedirs("/tmp/suno_skills", exist_ok=True)

    # Navigate to Studio
    print("Navigating to Studio...")
    await page.goto("https://suno.com/studio", wait_until="domcontentloaded", timeout=30000)
    await asyncio.sleep(5)

    # Dismiss modals
    for _ in range(3):
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

    await page.screenshot(path="/tmp/suno_skills/cal_01_empty.png")
    print("Screenshot 1: Empty studio")

    report = {}

    # Step 1: Find sidebar song thumbnails
    sidebar_imgs = await page.evaluate("""() => {
        const items = [];
        document.querySelectorAll('img').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.x < 150 && r.y > 60 && r.width > 20 && r.height > 20 && el.offsetParent !== null) {
                items.push({
                    x: Math.round(r.x + r.width/2),
                    y: Math.round(r.y + r.height/2),
                    alt: el.alt || '',
                    w: Math.round(r.width),
                    h: Math.round(r.height),
                });
            }
        });
        return items;
    }""") or []
    report["sidebar_images"] = sidebar_imgs
    print(f"\nSidebar images: {len(sidebar_imgs)}")
    for img in sidebar_imgs:
        print(f"  ({img['x']}, {img['y']}) {img['w']}x{img['h']} - {img['alt'][:40]}")

    if not sidebar_imgs:
        print("No sidebar images found!")
        await browser.close()
        return

    # Step 2: Drag first clip to timeline
    src = sidebar_imgs[0]
    target_x, target_y = 600, 300
    print(f"\nDragging clip from ({src['x']}, {src['y']}) to ({target_x}, {target_y})...")

    await page.mouse.move(src['x'], src['y'])
    await asyncio.sleep(0.3)
    await page.mouse.down()
    await asyncio.sleep(0.3)
    # Smooth drag
    steps = 20
    for i in range(steps):
        x = src['x'] + (target_x - src['x']) * (i + 1) / steps
        y = src['y'] + (target_y - src['y']) * (i + 1) / steps
        await page.mouse.move(x, y)
        await asyncio.sleep(0.03)
    await page.mouse.up()
    await asyncio.sleep(3)

    await page.screenshot(path="/tmp/suno_skills/cal_02_after_drag.png")
    print("Screenshot 2: After drag")

    # Handle tempo dialog if it appears
    try:
        confirm_btn = await page.query_selector("text=Confirm")
        if confirm_btn:
            await confirm_btn.click()
            print("Clicked Confirm on tempo dialog")
            await asyncio.sleep(5)
    except:
        pass

    await page.screenshot(path="/tmp/suno_skills/cal_03_after_confirm.png")
    print("Screenshot 3: After confirm")

    # Step 3: Map the current state with tracks
    print("\n=== MAPPING TRACKS ===")

    # Track numbers
    track_nums = await page.evaluate("""() => {
        const results = [];
        document.querySelectorAll('button').forEach(btn => {
            const text = btn.textContent.trim();
            const r = btn.getBoundingClientRect();
            if (/^\\d+$/.test(text) && r.y > 60 && r.y < 800 && r.width < 50) {
                results.push({
                    num: parseInt(text),
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                });
            }
        });
        return results.sort((a, b) => a.num - b.num);
    }""") or []
    report["track_numbers"] = track_nums
    print(f"Track numbers: {len(track_nums)}")
    for t in track_nums:
        print(f"  Track {t['num']}: pos=({t['cx']}, {t['cy']}) size={t['w']}x{t['h']}")

    # All buttons (to find track controls: S, mute, etc.)
    all_buttons = await page.evaluate("""() => {
        const results = [];
        document.querySelectorAll('button').forEach(btn => {
            const r = btn.getBoundingClientRect();
            if (r.width > 0 && btn.offsetParent !== null) {
                results.push({
                    text: btn.textContent.trim().substring(0, 50),
                    ariaLabel: btn.getAttribute('aria-label') || '',
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                });
            }
        });
        return results;
    }""") or []
    report["all_buttons"] = all_buttons

    # Find the Solo (S) and Mute buttons near track controls
    track_control_buttons = [b for b in all_buttons if b['x'] < 320 and b['y'] > 100 and b['y'] < 800]
    print(f"\nTrack control area buttons ({len(track_control_buttons)}):")
    for b in track_control_buttons:
        print(f"  ({b['cx']:4d},{b['cy']:4d}) {b['w']:3d}x{b['h']:3d} text='{b['text'][:20]}' aria='{b['ariaLabel'][:20]}'")

    # Faders
    faders = await page.evaluate("""() => {
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
    if faders:
        print(f"\nFaders/Sliders ({len(faders)}):")
        for f in faders:
            print(f"  ({f['x']},{f['y']}) {f['w']}x{f['h']} class='{f['className'][:40]}' val='{f['ariaValue']}'")

    # Canvases (to see where waveforms are)
    canvases = await page.evaluate("""() => {
        const results = [];
        document.querySelectorAll('canvas').forEach(el => {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && el.offsetParent !== null) {
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                });
            }
        });
        return results;
    }""") or []
    report["canvases"] = canvases
    print(f"\nCanvases ({len(canvases)}):")
    for c in canvases:
        print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']}")

    # Step 4: Try to click on a clip/waveform area to select it
    print("\n=== SELECTING CLIP ===")

    # Find any clickable elements in the timeline area that might be clips
    clip_elements = await page.evaluate("""() => {
        const results = [];
        // Look for divs in the timeline area that might be clip containers
        document.querySelectorAll('div').forEach(el => {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            if (r.x > 300 && r.y > 100 && r.y < 800 && r.width > 50 && r.height > 30 &&
                r.height < 200 && el.childElementCount > 0 &&
                (style.backgroundColor !== 'rgba(0, 0, 0, 0)' || el.querySelector('canvas'))) {
                results.push({
                    x: Math.round(r.x), y: Math.round(r.y),
                    w: Math.round(r.width), h: Math.round(r.height),
                    cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                    bg: style.backgroundColor,
                    tag: el.tagName,
                    children: el.childElementCount,
                    className: (el.className || '').substring(0, 80),
                });
            }
        });
        return results;
    }""") or []
    report["potential_clips"] = clip_elements
    print(f"Potential clip elements: {len(clip_elements)}")
    for c in clip_elements[:10]:
        print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']} bg={c['bg'][:30]} children={c['children']}")

    # Try clicking in the waveform area of the first track
    # Based on the layout: track controls are in left area, waveforms are in the canvas area starting at x≈316
    # Let's try clicking at various y positions within the canvas area
    right_panel_text = ""
    for try_y in [170, 200, 250, 300]:
        for try_x in [500, 600, 700]:
            await page.mouse.click(try_x, try_y)
            await asyncio.sleep(1)

            # Check right panel
            right_panel_text = await page.evaluate("""() => {
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
            }""") or ""

            if 'Clip' in right_panel_text and 'Track' in right_panel_text:
                print(f"  CLIP SELECTED at ({try_x}, {try_y})!")
                report["clip_select_position"] = {"x": try_x, "y": try_y}
                break
        if 'Clip' in right_panel_text and 'Track' in right_panel_text:
            break

    if 'Clip' not in right_panel_text:
        # Maybe we need to double-click
        print("  Single click didn't select clip, trying double-click...")
        for try_y in [170, 200, 250]:
            for try_x in [500, 600, 700]:
                await page.mouse.dblclick(try_x, try_y)
                await asyncio.sleep(1)

                right_panel_text = await page.evaluate("""() => {
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
                }""") or ""

                if 'Clip' in right_panel_text or 'Track' in right_panel_text:
                    print(f"  CLIP SELECTED at dblclick ({try_x}, {try_y})!")
                    report["clip_select_position"] = {"x": try_x, "y": try_y, "method": "dblclick"}
                    break
            if 'Clip' in right_panel_text or 'Track' in right_panel_text:
                break

    await page.screenshot(path="/tmp/suno_skills/cal_04_clip_selected.png")
    print(f"Screenshot 4: After clip selection attempt")
    print(f"Right panel: {right_panel_text[:200]}")

    # Step 5: If clip is selected, map the right panel with Clip/Track tabs
    if 'Clip' in right_panel_text or 'Track' in right_panel_text:
        # Map right panel elements
        right_buttons = await page.evaluate("""() => {
            const vw = window.innerWidth;
            const results = [];
            document.querySelectorAll('button').forEach(btn => {
                const r = btn.getBoundingClientRect();
                if (r.x > vw * 0.7 && r.width > 0 && btn.offsetParent !== null) {
                    results.push({
                        text: btn.textContent.trim().substring(0, 40),
                        ariaLabel: btn.getAttribute('aria-label') || '',
                        x: Math.round(r.x), y: Math.round(r.y),
                        w: Math.round(r.width), h: Math.round(r.height),
                        cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                    });
                }
            });
            return results;
        }""") or []
        report["right_panel_buttons"] = right_buttons
        print(f"\nRight panel buttons ({len(right_buttons)}):")
        for b in right_buttons:
            print(f"  ({b['cx']:4d},{b['cy']:4d}) {b['w']:3d}x{b['h']:3d} text='{b['text'][:30]}' aria='{b['ariaLabel'][:30]}'")

        # Right panel text items with positions
        right_items = await page.evaluate("""() => {
            const vw = window.innerWidth;
            const items = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const r = walker.currentNode.parentElement?.getBoundingClientRect();
                if (r && r.left > vw * 0.7 && r.width > 0) {
                    const t = walker.currentNode.textContent.trim();
                    if (t && t.length > 0) {
                        items.push({text: t.substring(0, 60), x: Math.round(r.left), y: Math.round(r.top)});
                    }
                }
            }
            return items;
        }""") or []
        report["right_panel_items"] = right_items
        print(f"\nRight panel text items ({len(right_items)}):")
        for item in right_items[:30]:
            print(f"  ({item['x']:4d},{item['y']:4d}) '{item['text'][:50]}'")

        # Now click on "Track" tab to see EQ
        track_tab_btn = next((b for b in right_buttons if b['text'] == 'Track'), None)
        if track_tab_btn:
            print(f"\nClicking Track tab at ({track_tab_btn['cx']}, {track_tab_btn['cy']})...")
            await page.mouse.click(track_tab_btn['cx'], track_tab_btn['cy'])
            await asyncio.sleep(2)

            await page.screenshot(path="/tmp/suno_skills/cal_05_track_tab.png")
            print("Screenshot 5: Track tab")

            # Map EQ elements
            eq_buttons = await page.evaluate("""() => {
                const vw = window.innerWidth;
                const results = [];
                document.querySelectorAll('button').forEach(btn => {
                    const r = btn.getBoundingClientRect();
                    if (r.x > vw * 0.7 && r.width > 0 && btn.offsetParent !== null) {
                        results.push({
                            text: btn.textContent.trim().substring(0, 40),
                            ariaLabel: btn.getAttribute('aria-label') || '',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                        });
                    }
                });
                return results;
            }""") or []
            report["eq_buttons"] = eq_buttons
            print(f"\nEQ panel buttons ({len(eq_buttons)}):")
            for b in eq_buttons:
                print(f"  ({b['cx']:4d},{b['cy']:4d}) {b['w']:3d}x{b['h']:3d} text='{b['text'][:30]}' aria='{b['ariaLabel'][:30]}'")

            # Switches (EQ toggle)
            eq_switches = await page.evaluate("""() => {
                const vw = window.innerWidth;
                const results = [];
                document.querySelectorAll('[role=switch]').forEach(sw => {
                    const r = sw.getBoundingClientRect();
                    if (r.x > vw * 0.7 && r.width > 0) {
                        results.push({
                            checked: sw.getAttribute('aria-checked'),
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                            cx: Math.round(r.x + r.width/2), cy: Math.round(r.y + r.height/2),
                        });
                    }
                });
                return results;
            }""") or []
            report["eq_switches"] = eq_switches
            print(f"\nEQ switches ({len(eq_switches)}):")
            for s in eq_switches:
                print(f"  ({s['cx']},{s['cy']}) {s['w']}x{s['h']} checked={s['checked']}")

            # Input fields (EQ values)
            eq_inputs = await page.evaluate("""() => {
                const vw = window.innerWidth;
                const results = [];
                document.querySelectorAll('input').forEach(inp => {
                    const r = inp.getBoundingClientRect();
                    if (r.x > vw * 0.7 && r.width > 0 && inp.offsetParent !== null) {
                        results.push({
                            type: inp.type,
                            value: inp.value || '',
                            placeholder: inp.placeholder || '',
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    }
                });
                return results;
            }""") or []
            report["eq_inputs"] = eq_inputs
            print(f"\nEQ inputs ({len(eq_inputs)}):")
            for i in eq_inputs:
                print(f"  ({i['x']},{i['y']}) {i['w']}x{i['h']} val='{i['value']}' ph='{i['placeholder']}'")

            # EQ canvas
            eq_canvases = await page.evaluate("""() => {
                const vw = window.innerWidth;
                const results = [];
                document.querySelectorAll('canvas').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.x > vw * 0.7 && r.width > 0 && el.offsetParent !== null) {
                        results.push({
                            x: Math.round(r.x), y: Math.round(r.y),
                            w: Math.round(r.width), h: Math.round(r.height),
                        });
                    }
                });
                return results;
            }""") or []
            report["eq_canvases"] = eq_canvases
            print(f"\nEQ canvases ({len(eq_canvases)}):")
            for c in eq_canvases:
                print(f"  ({c['x']},{c['y']}) {c['w']}x{c['h']}")

            # SVG elements (filter type icons, knobs)
            eq_svgs = await page.evaluate("""() => {
                const vw = window.innerWidth;
                const results = [];
                document.querySelectorAll('svg').forEach(el => {
                    const r = el.getBoundingClientRect();
                    if (r.x > vw * 0.7 && r.width > 10 && el.offsetParent !== null) {
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
            report["eq_svgs"] = eq_svgs
            print(f"\nEQ SVGs ({len(eq_svgs)}):")
            for s in eq_svgs:
                print(f"  ({s['x']},{s['y']}) {s['w']}x{s['h']} aria='{s['ariaLabel'][:30]}' role='{s['role']}'")

            # Right panel full text
            track_text = await page.evaluate("""() => {
                const vw = window.innerWidth;
                const items = [];
                const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                while (walker.nextNode()) {
                    const r = walker.currentNode.parentElement?.getBoundingClientRect();
                    if (r && r.left > vw * 0.7 && r.width > 0) {
                        const t = walker.currentNode.textContent.trim();
                        if (t) items.push({text: t.substring(0, 60), x: Math.round(r.left), y: Math.round(r.top)});
                    }
                }
                return items;
            }""") or []
            report["track_tab_text"] = track_text
            print(f"\nTrack tab text ({len(track_text)}):")
            for item in track_text[:40]:
                print(f"  ({item['x']:4d},{item['y']:4d}) '{item['text'][:50]}'")
    else:
        print("\nFailed to select a clip. Will try clicking track number instead...")
        # If no clips on timeline, try clicking a track number button
        if track_nums:
            tn = track_nums[0]
            print(f"Clicking track {tn['num']} at ({tn['cx']}, {tn['cy']})...")
            await page.mouse.click(tn['cx'], tn['cy'])
            await asyncio.sleep(2)
            await page.screenshot(path="/tmp/suno_skills/cal_04b_track_click.png")

            right_panel_text2 = await page.evaluate("""() => {
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
            }""") or ""
            print(f"Right panel after track click: {right_panel_text2[:200]}")

    # Save report
    report_path = "/tmp/suno_skills/calibrate_full_report.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nReport saved: {report_path}")

    await browser.close()
    print("Done!")


if __name__ == "__main__":
    asyncio.run(calibrate())
