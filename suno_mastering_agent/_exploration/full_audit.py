#!/usr/bin/env python3
"""Full UI audit of Suno - visits every page, clicks every button, screenshots everything."""
import asyncio
import json
import os
from src.browser import BrowserController

SCREENSHOT_DIR = "/tmp/suno_audit"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

JS_GET_BUTTONS = """() => {
    return [...document.querySelectorAll('button')]
        .filter(b => b.offsetParent !== null)
        .map(b => {
            const rect = b.getBoundingClientRect();
            return {
                text: b.textContent.trim().substring(0, 80),
                ariaLabel: b.getAttribute('aria-label'),
                disabled: b.disabled,
                x: Math.round(rect.x + rect.width/2),
                y: Math.round(rect.y + rect.height/2),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
            };
        })
        .filter(b => (b.text || b.ariaLabel) && b.w > 0 && b.h > 0);
}"""

JS_GET_LINKS = """() => {
    return [...document.querySelectorAll('a[href]')]
        .filter(a => a.offsetParent !== null)
        .map(a => {
            const rect = a.getBoundingClientRect();
            return {
                text: a.textContent.trim().substring(0, 60),
                href: a.getAttribute('href'),
                x: Math.round(rect.x + rect.width/2),
                y: Math.round(rect.y + rect.height/2),
            };
        })
        .filter(a => a.text && a.href && a.href.startsWith('/'));
}"""

JS_GET_INPUTS = """() => {
    return [...document.querySelectorAll('input, textarea, select, [role=slider]')]
        .filter(el => el.offsetParent !== null)
        .map(el => {
            const rect = el.getBoundingClientRect();
            return {
                tag: el.tagName,
                type: el.getAttribute('type'),
                placeholder: el.getAttribute('placeholder'),
                role: el.getAttribute('role'),
                ariaLabel: el.getAttribute('aria-label'),
                value: (el.value || '').substring(0, 50),
                x: Math.round(rect.x),
                y: Math.round(rect.y),
                w: Math.round(rect.width),
                h: Math.round(rect.height),
            };
        });
}"""

JS_GET_MENUS = """() => {
    const selectors = [
        '[role=menu]', '[role=dialog]', '[role=listbox]',
        '[data-state=open]', '[data-radix-popper-content-wrapper]'
    ];
    const found = [];
    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
            const text = el.textContent.trim();
            if (text.length > 0 && text.length < 2000) {
                found.push({
                    selector: sel,
                    text: text.substring(0, 500),
                    tag: el.tagName,
                });
            }
        }
    }
    // Also check high z-index overlays
    for (const el of document.querySelectorAll('*')) {
        const z = parseInt(window.getComputedStyle(el).zIndex);
        if (z > 10000 && el.textContent.trim().length > 0 && el.textContent.trim().length < 1000) {
            found.push({
                selector: 'high-z:' + z,
                text: el.textContent.trim().substring(0, 500),
                tag: el.tagName,
            });
        }
    }
    return found;
}"""

JS_GET_PAGE_TEXT = """() => document.body.innerText.substring(0, 3000)"""


async def screenshot(browser, name):
    path = f"{SCREENSHOT_DIR}/{name}.png"
    await browser.page.screenshot(path=path)
    print(f"  [screenshot] {path}")
    return path


async def audit_page(browser, name):
    """Get full inventory of a page."""
    print(f"\n{'='*60}")
    print(f"PAGE: {name}")
    print(f"URL: {browser.page.url}")
    print(f"{'='*60}")

    await screenshot(browser, name)

    buttons = await browser.evaluate(JS_GET_BUTTONS)
    print(f"\n  BUTTONS ({len(buttons)}):")
    for b in buttons:
        label = b.get('text') or b.get('ariaLabel') or '???'
        disabled = ' [DISABLED]' if b.get('disabled') else ''
        print(f"    - {label}{disabled}  ({b['x']},{b['y']})")

    links = await browser.evaluate(JS_GET_LINKS)
    print(f"\n  NAV LINKS ({len(links)}):")
    for l in links:
        print(f"    - {l['text']} -> {l['href']}")

    inputs = await browser.evaluate(JS_GET_INPUTS)
    print(f"\n  INPUTS ({len(inputs)}):")
    for i in inputs:
        desc = i.get('placeholder') or i.get('ariaLabel') or i.get('type') or i['tag']
        print(f"    - {desc} (value={i.get('value','')!r})")

    return buttons, links, inputs


async def click_and_check(browser, x, y, label, screenshot_name, button='left', close_after=True):
    """Click a position, screenshot, capture any menus, then close."""
    print(f"\n  >> Clicking: {label} at ({x},{y})")
    try:
        await browser.page.mouse.click(x, y, button=button)
        await asyncio.sleep(2)
        await screenshot(browser, screenshot_name)

        menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
        if menus:
            print(f"     Menu/dialog appeared:")
            for m in menus:
                lines = m['text'].split('\n')
                for line in lines[:15]:
                    line = line.strip()
                    if line:
                        print(f"       - {line}")

        if close_after:
            await browser.page.keyboard.press('Escape')
            await asyncio.sleep(1)

        return menus
    except Exception as e:
        print(f"     Error: {e}")
        return []


# Safe version that won't crash on z-index parsing
JS_MENU_CHECK_SAFE = """() => {
    const found = [];
    const selectors = [
        '[role=menu]', '[role=dialog]', '[role=listbox]',
        '[data-radix-popper-content-wrapper]'
    ];
    for (const sel of selectors) {
        for (const el of document.querySelectorAll(sel)) {
            const text = el.textContent.trim();
            if (text.length > 0 && text.length < 2000) {
                found.push({ text: text.substring(0, 500), tag: el.tagName });
            }
        }
    }
    // Check body direct children (React portals)
    for (const el of document.body.children) {
        if (el.id === '__next' || el.tagName === 'SCRIPT') continue;
        try {
            const z = parseInt(window.getComputedStyle(el).zIndex);
            if (z > 10000) {
                found.push({ text: el.textContent.trim().substring(0, 500), tag: 'PORTAL' });
            }
        } catch(e) {}
    }
    return found;
}"""


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    report = {}

    # ============================================================
    # 1. HOME PAGE
    # ============================================================
    await browser.navigate('https://suno.com')
    await asyncio.sleep(4)
    buttons, links, inputs = await audit_page(browser, '01_home')
    report['home'] = {'buttons': len(buttons), 'links': len(links), 'inputs': len(inputs)}

    # ============================================================
    # 2. CREATE PAGE
    # ============================================================
    await browser.navigate('https://suno.com/create')
    await asyncio.sleep(4)
    buttons, links, inputs = await audit_page(browser, '02_create')
    report['create'] = {'buttons': len(buttons), 'links': len(links), 'inputs': len(inputs)}

    # Click the Simple/Custom/Sounds tabs
    for tab_text in ['Custom', 'Sounds']:
        try:
            tab = browser.page.get_by_text(tab_text, exact=True)
            if await tab.count() > 0:
                await tab.first.click()
                await asyncio.sleep(2)
                await screenshot(browser, f'02_create_{tab_text.lower()}')
                print(f"  Clicked tab: {tab_text}")
                text = await browser.evaluate(JS_GET_PAGE_TEXT)
                # Print just the create panel area
                print(f"  Create panel text: {text[:500]}")
        except Exception as e:
            print(f"  Tab {tab_text} error: {e}")

    # Switch back to Simple
    try:
        tab = browser.page.get_by_text('Simple', exact=True)
        if await tab.count() > 0:
            await tab.first.click()
            await asyncio.sleep(1)
    except:
        pass

    # ============================================================
    # 3. LIBRARY PAGE
    # ============================================================
    await browser.navigate('https://suno.com/me')
    await asyncio.sleep(4)
    buttons, links, inputs = await audit_page(browser, '03_library')
    report['library'] = {'buttons': len(buttons), 'links': len(links), 'inputs': len(inputs)}

    # Check sub-tabs: Songs, Playlists, Workspaces
    for tab_text in ['Playlists', 'Workspaces']:
        try:
            tab = browser.page.get_by_text(tab_text, exact=True)
            if await tab.count() > 0:
                await tab.first.click()
                await asyncio.sleep(2)
                await screenshot(browser, f'03_library_{tab_text.lower()}')
                print(f"  Clicked tab: {tab_text}")
        except Exception as e:
            print(f"  Tab {tab_text} error: {e}")

    # ============================================================
    # 4. SEARCH PAGE
    # ============================================================
    await browser.navigate('https://suno.com/search')
    await asyncio.sleep(4)
    buttons, links, inputs = await audit_page(browser, '04_search')
    report['search'] = {'buttons': len(buttons), 'links': len(links), 'inputs': len(inputs)}

    # ============================================================
    # 5. HOOKS PAGE
    # ============================================================
    await browser.navigate('https://suno.com/hooks')
    await asyncio.sleep(4)
    buttons, links, inputs = await audit_page(browser, '05_hooks')
    report['hooks'] = {'buttons': len(buttons), 'links': len(links), 'inputs': len(inputs)}

    # ============================================================
    # 6. LABS PAGE
    # ============================================================
    await browser.navigate('https://suno.com/labs')
    await asyncio.sleep(4)
    buttons, links, inputs = await audit_page(browser, '06_labs')
    report['labs'] = {'buttons': len(buttons), 'links': len(links), 'inputs': len(inputs)}

    # ============================================================
    # 7. STUDIO PAGE (the big one)
    # ============================================================
    await browser.navigate('https://suno.com/studio')
    await asyncio.sleep(6)
    buttons, links, inputs = await audit_page(browser, '07_studio_empty')
    report['studio'] = {'buttons': len(buttons), 'links': len(links), 'inputs': len(inputs)}

    # Drag a clip to timeline
    print("\n  Dragging clip to timeline...")
    await browser.page.mouse.click(75, 145)
    await asyncio.sleep(1)
    await browser.page.mouse.move(75, 150)
    await browser.page.mouse.down()
    for i in range(10):
        x = 75 + (500 - 75) * (i + 1) / 10
        y = 150 + (300 - 150) * (i + 1) / 10
        await browser.page.mouse.move(x, y)
        await asyncio.sleep(0.05)
    await browser.page.mouse.up()
    await asyncio.sleep(2)

    # Handle tempo dialog
    try:
        await browser.page.click('text=Confirm', timeout=3000)
        await asyncio.sleep(3)
        print("  Confirmed tempo dialog")
    except:
        pass

    await screenshot(browser, '07_studio_with_clip')

    # Click clip on timeline to select it
    await browser.page.mouse.click(350, 120)
    await asyncio.sleep(2)
    await screenshot(browser, '07_studio_clip_selected')
    buttons2, _, _ = await audit_page(browser, '07_studio_clip_detail')

    # --- Studio: Export dropdown ---
    print("\n  --- EXPORT DROPDOWN ---")
    export_btn = await browser.page.query_selector('text=Export')
    if export_btn:
        await export_btn.click(force=True)
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_export')
        menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
        for m in menus:
            print(f"    {m['text'][:200]}")
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # --- Studio: Right-click clip ---
    print("\n  --- RIGHT-CLICK CONTEXT MENU ---")
    await browser.page.mouse.click(350, 120, button='right')
    await asyncio.sleep(2)
    await screenshot(browser, '07_studio_rightclick')
    menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
    for m in menus:
        print(f"    Context menu: {m['text'][:300]}")
    await browser.page.keyboard.press('Escape')
    await asyncio.sleep(1)

    # --- Studio: Click Learn button ---
    print("\n  --- LEARN BUTTON ---")
    await click_and_check(browser, 0, 0, 'Learn', '07_studio_learn')
    learn_btn = browser.page.get_by_text('Learn', exact=True)
    if await learn_btn.count() > 0:
        box = await learn_btn.first.bounding_box()
        if box:
            await click_and_check(browser, box['x']+box['width']/2, box['y']+box['height']/2,
                                 'Learn', '07_studio_learn')

    # --- Studio: Click Layout button ---
    print("\n  --- LAYOUT BUTTON ---")
    layout_btn = browser.page.get_by_text('Layout', exact=True)
    if await layout_btn.count() > 0:
        box = await layout_btn.first.bounding_box()
        if box:
            await click_and_check(browser, box['x']+box['width']/2, box['y']+box['height']/2,
                                 'Layout', '07_studio_layout')

    # --- Studio: Click song link to see song detail ---
    print("\n  --- SONG DETAIL PAGE ---")
    song_links = await browser.evaluate("""() => {
        return [...document.querySelectorAll('a[href*="/song/"]')]
            .filter(a => a.offsetParent !== null)
            .slice(0, 1)
            .map(a => ({text: a.textContent.trim(), href: a.getAttribute('href')}));
    }""")
    if song_links:
        href = song_links[0]['href']
        print(f"    Navigating to song: {song_links[0]['text']} -> {href}")
        await browser.navigate(f'https://suno.com{href}')
        await asyncio.sleep(4)
        await audit_page(browser, '08_song_detail')

        # Go back to studio
        await browser.navigate('https://suno.com/studio')
        await asyncio.sleep(5)

    # --- Studio: Click Remix/Edit ---
    print("\n  --- REMIX/EDIT BUTTON ---")
    # Need to select clip first
    await browser.page.mouse.click(350, 120)
    await asyncio.sleep(2)
    remix_btn = browser.page.get_by_text('Remix/Edit', exact=True)
    if await remix_btn.count() > 0:
        await remix_btn.first.click()
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_remix_menu')
        menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
        for m in menus:
            print(f"    Remix menu: {m['text'][:300]}")
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # --- Studio: Click Extract Stems ---
    print("\n  --- EXTRACT STEMS ---")
    stems_btn = browser.page.get_by_text('Extract Stems', exact=True)
    if await stems_btn.count() > 0:
        await stems_btn.first.click()
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_stems')
        # Check what options appeared
        text = await browser.evaluate(JS_GET_PAGE_TEXT)
        if 'All Detected' in text or 'Vocals' in text:
            print(f"    Stems options visible in page")
        menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
        for m in menus:
            print(f"    Stems menu: {m['text'][:200]}")
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # --- Studio: Click Cover button ---
    print("\n  --- COVER BUTTON ---")
    cover_btn = browser.page.get_by_text('Cover', exact=True)
    if await cover_btn.count() > 0:
        await cover_btn.first.click()
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_cover')
        menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
        for m in menus:
            print(f"    Cover dialog: {m['text'][:200]}")
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # --- Studio: Click Song button (bottom bar) ---
    print("\n  --- SONG DROPDOWN (bottom bar) ---")
    song_btn = browser.page.get_by_text('Song', exact=True)
    if await song_btn.count() > 0:
        box = await song_btn.first.bounding_box()
        if box and box['y'] > 400:  # Only the bottom bar one
            await song_btn.first.click()
            await asyncio.sleep(2)
            await screenshot(browser, '07_studio_song_dropdown')
            menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
            for m in menus:
                print(f"    Song dropdown: {m['text'][:200]}")
            await browser.page.keyboard.press('Escape')
            await asyncio.sleep(1)

    # --- Studio: Click BPM button ---
    print("\n  --- BPM BUTTON ---")
    bpm_btn = browser.page.get_by_text('68 BPM', exact=False)
    if await bpm_btn.count() > 0:
        await bpm_btn.first.click()
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_bpm')
        menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
        for m in menus:
            print(f"    BPM dialog: {m['text'][:200]}")
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # --- Studio: Click Add Track ---
    print("\n  --- ADD TRACK ---")
    add_track = browser.page.get_by_text('Add Track', exact=True)
    if await add_track.count() > 0:
        await add_track.first.click()
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_add_track')
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # --- Studio: Click No Input dropdown ---
    print("\n  --- NO INPUT DROPDOWN ---")
    no_input = browser.page.get_by_text('No Input', exact=True)
    if await no_input.count() > 0:
        await no_input.first.click()
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_no_input')
        menus = await browser.evaluate(JS_MENU_CHECK_SAFE)
        for m in menus:
            print(f"    Input options: {m['text'][:200]}")
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # --- Studio: Show More (clip details) ---
    print("\n  --- SHOW MORE (clip details) ---")
    await browser.page.mouse.click(350, 120)
    await asyncio.sleep(1)
    show_more = browser.page.get_by_text('Show More', exact=True)
    if await show_more.count() > 0:
        await show_more.first.click()
        await asyncio.sleep(2)
        await screenshot(browser, '07_studio_show_more')
        text = await browser.evaluate(JS_GET_PAGE_TEXT)
        print(f"    Expanded text: {text[:800]}")

    # ============================================================
    # 8. NOTIFICATIONS PAGE
    # ============================================================
    await browser.navigate('https://suno.com/notifications')
    await asyncio.sleep(4)
    await audit_page(browser, '09_notifications')

    # ============================================================
    # SUMMARY
    # ============================================================
    print("\n" + "="*60)
    print("AUDIT COMPLETE")
    print("="*60)
    print(f"Screenshots saved to: {SCREENSHOT_DIR}/")
    total = len([f for f in os.listdir(SCREENSHOT_DIR) if f.endswith('.png')])
    print(f"Total screenshots: {total}")
    for page, counts in report.items():
        print(f"  {page}: {counts['buttons']} buttons, {counts['links']} links, {counts['inputs']} inputs")

    await browser.close()

asyncio.run(main())
