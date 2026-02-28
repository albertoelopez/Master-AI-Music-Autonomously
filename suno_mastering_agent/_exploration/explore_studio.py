#!/usr/bin/env python3
"""Thorough exploration of Suno Studio to discover all features."""
import asyncio
import json
from src.browser import BrowserController

JS_EXPLORE = """() => {
    function cls(el) {
        return typeof el.className === 'string' ? el.className.substring(0, 120) : '';
    }
    const results = {};

    // Every visible button
    results.buttons = [...document.querySelectorAll('button')]
        .filter(b => b.offsetParent !== null)
        .map(b => ({
            text: b.textContent.trim().substring(0, 80),
            ariaLabel: b.getAttribute('aria-label'),
            disabled: b.disabled,
        }))
        .filter(b => b.text || b.ariaLabel);

    // Every visible link
    results.links = [...document.querySelectorAll('a[href]')]
        .filter(a => a.offsetParent !== null && a.textContent.trim())
        .map(a => ({
            text: a.textContent.trim().substring(0, 60),
            href: a.getAttribute('href'),
        }));

    // Every visible input
    results.inputs = [...document.querySelectorAll('input, textarea, select, [role=slider]')]
        .filter(el => el.offsetParent !== null)
        .map(el => ({
            tag: el.tagName,
            type: el.getAttribute('type'),
            placeholder: el.getAttribute('placeholder'),
            role: el.getAttribute('role'),
            ariaLabel: el.getAttribute('aria-label'),
            value: (el.value || '').substring(0, 50),
        }));

    // Full visible text
    results.fullText = document.body.innerText.substring(0, 5000);

    return results;
}"""

JS_MENU_CHECK = """() => {
    // Check for any popups, menus, dialogs that appeared
    const selectors = [
        '[role=menu]', '[role=dialog]', '[role=listbox]',
        '[data-state=open]', '[data-radix-popper-content-wrapper]',
        '.popover', '.dropdown-menu'
    ];
    const found = [];
    for (const sel of selectors) {
        const els = document.querySelectorAll(sel);
        for (const el of els) {
            if (el.offsetParent !== null || el.getAttribute('data-state') === 'open') {
                found.push({
                    selector: sel,
                    text: el.textContent.trim().substring(0, 500),
                    tag: el.tagName,
                });
            }
        }
    }
    return found;
}"""


async def setup_timeline(browser):
    """Ensure a clip is on the timeline."""
    text = await browser.evaluate('() => document.body.innerText.substring(0, 1000)')
    if 'Remix/Edit' in text:
        print('Clip already on timeline')
        return True

    print('Dragging clip to timeline...')
    await browser.page.mouse.click(75, 145)
    await asyncio.sleep(1)
    await browser.page.mouse.move(75, 150)
    await browser.page.mouse.down()
    for i in range(10):
        x = 75 + (500 - 75) * (i + 1) / 10
        y = 150 + (400 - 150) * (i + 1) / 10
        await browser.page.mouse.move(x, y)
        await asyncio.sleep(0.05)
    await browser.page.mouse.up()
    await asyncio.sleep(2)
    try:
        await browser.page.click('text=Confirm', timeout=3000)
        await asyncio.sleep(3)
        print('Confirmed tempo dialog')
    except:
        pass
    return True


async def explore_main(browser):
    """Explore the main Studio interface."""
    print('\n' + '='*60)
    print('MAIN STUDIO INTERFACE')
    print('='*60)
    info = await browser.evaluate(JS_EXPLORE)
    for key, val in info.items():
        if isinstance(val, list):
            print(f'\n--- {key} ({len(val)} items) ---')
            for item in val:
                print(f'  {json.dumps(item)}')
        elif key == 'fullText':
            print(f'\n--- visible text ---')
            print(val[:2000])


async def explore_export(browser):
    """Check the Export dropdown."""
    print('\n' + '='*60)
    print('EXPORT DROPDOWN')
    print('='*60)
    try:
        export_btn = await browser.page.query_selector('text=Export')
        if export_btn:
            await export_btn.click(force=True)
            await asyncio.sleep(2)
            menus = await browser.evaluate(JS_MENU_CHECK)
            for m in menus:
                print(f'  {json.dumps(m)}')
            await browser.screenshot('/tmp/suno_export2.png')
            await browser.page.keyboard.press('Escape')
            await asyncio.sleep(1)
    except Exception as e:
        print(f'  Error: {e}')


async def explore_right_click_clip(browser):
    """Right-click a clip on the timeline for context menu."""
    print('\n' + '='*60)
    print('RIGHT-CLICK CONTEXT MENU ON CLIP')
    print('='*60)
    try:
        await browser.page.mouse.click(350, 120, button='right')
        await asyncio.sleep(2)
        menus = await browser.evaluate(JS_MENU_CHECK)
        for m in menus:
            print(f'  {json.dumps(m)}')
        await browser.screenshot('/tmp/suno_rightclick.png')
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)
    except Exception as e:
        print(f'  Error: {e}')


async def explore_more_options(browser):
    """Click the '...' (More options) near the project title."""
    print('\n' + '='*60)
    print('PROJECT MORE OPTIONS (...)')
    print('='*60)
    try:
        dots = await browser.page.query_selector('button:has-text("...")')
        if dots:
            await dots.click(force=True)
            await asyncio.sleep(2)
            menus = await browser.evaluate(JS_MENU_CHECK)
            for m in menus:
                print(f'  {json.dumps(m)}')
            await browser.screenshot('/tmp/suno_dots.png')
            await browser.page.keyboard.press('Escape')
            await asyncio.sleep(1)
        else:
            print('  ... button not found')
    except Exception as e:
        print(f'  Error: {e}')


async def explore_track_more_options(browser):
    """Hover over track and click More options."""
    print('\n' + '='*60)
    print('TRACK MORE OPTIONS (hover menu)')
    print('='*60)
    try:
        # Hover over the track area on timeline
        await browser.page.mouse.move(350, 120)
        await asyncio.sleep(1)
        # Force click the first visible More options
        btns = await browser.page.query_selector_all("button[aria-label='More options']")
        for btn in btns:
            box = await btn.bounding_box()
            if box:
                await btn.click(force=True)
                await asyncio.sleep(2)
                menus = await browser.evaluate(JS_MENU_CHECK)
                for m in menus:
                    print(f'  {json.dumps(m)}')
                await browser.screenshot('/tmp/suno_track_more.png')
                await browser.page.keyboard.press('Escape')
                await asyncio.sleep(1)
                break
    except Exception as e:
        print(f'  Error: {e}')


async def explore_remix_edit(browser):
    """Check the Remix/Edit button."""
    print('\n' + '='*60)
    print('REMIX/EDIT BUTTON')
    print('='*60)
    try:
        btn = await browser.page.query_selector('button:has-text("Remix/Edit")')
        if btn:
            await btn.click(force=True)
            await asyncio.sleep(3)
            await browser.screenshot('/tmp/suno_remix.png')
            menus = await browser.evaluate(JS_MENU_CHECK)
            for m in menus:
                print(f'  {json.dumps(m)}')
            # Get new page text
            text = await browser.evaluate('() => document.body.innerText.substring(0, 3000)')
            print(f'\n  Page text after Remix/Edit:')
            print(f'  {text[:1000]}')
            # Go back if we navigated
            await browser.page.keyboard.press('Escape')
            await asyncio.sleep(1)
        else:
            print('  Remix/Edit button not found')
    except Exception as e:
        print(f'  Error: {e}')


async def explore_extract_stems(browser):
    """Check the Extract Stems button."""
    print('\n' + '='*60)
    print('EXTRACT STEMS BUTTON')
    print('='*60)
    try:
        btn = await browser.page.query_selector('button:has-text("Extract Stems")')
        if btn:
            await btn.click(force=True)
            await asyncio.sleep(3)
            await browser.screenshot('/tmp/suno_stems.png')
            menus = await browser.evaluate(JS_MENU_CHECK)
            for m in menus:
                print(f'  {json.dumps(m)}')
            text = await browser.evaluate('() => document.body.innerText.substring(0, 3000)')
            print(f'\n  Page text after Extract Stems:')
            print(f'  {text[:1000]}')
            await browser.page.keyboard.press('Escape')
            await asyncio.sleep(1)
        else:
            print('  Extract Stems button not found')
    except Exception as e:
        print(f'  Error: {e}')


async def explore_bottom_bar(browser):
    """Check the bottom bar icons (the + and upload icons)."""
    print('\n' + '='*60)
    print('BOTTOM BAR CONTROLS')
    print('='*60)
    info = await browser.evaluate("""() => {
        // Get all elements in the bottom 100px of the page
        const h = window.innerHeight;
        const bottomEls = [...document.querySelectorAll('button, a, input, [role=slider]')]
            .filter(el => {
                const rect = el.getBoundingClientRect();
                return rect.top > h - 120 && el.offsetParent !== null;
            })
            .map(el => ({
                tag: el.tagName,
                text: el.textContent?.trim().substring(0, 40),
                ariaLabel: el.getAttribute('aria-label'),
                type: el.getAttribute('type'),
                role: el.getAttribute('role'),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
            }));
        return bottomEls;
    }""")
    for item in info:
        print(f'  {json.dumps(item)}')


async def search_for_mastering(browser):
    """Search the entire page for anything mastering-related."""
    print('\n' + '='*60)
    print('SEARCHING FOR MASTERING FEATURES')
    print('='*60)
    result = await browser.evaluate("""() => {
        const keywords = ['master', 'mastering', 'loudness', 'lufs', 'limiter',
                          'compressor', 'eq', 'equalizer', 'reverb', 'effect',
                          'fx', 'normalize', 'gain', 'volume', 'pan', 'mix',
                          'bus', 'send', 'plugin'];
        const allText = document.body.innerText.toLowerCase();
        const found = {};
        for (const kw of keywords) {
            if (allText.includes(kw)) {
                // Find the context around it
                const idx = allText.indexOf(kw);
                found[kw] = allText.substring(Math.max(0, idx - 30), idx + 50).trim();
            }
        }
        return found;
    }""")
    if result:
        for kw, context in result.items():
            print(f'  "{kw}" found: ...{context}...')
    else:
        print('  No mastering-related keywords found on main page')


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    await browser.navigate('https://suno.com/studio')
    await asyncio.sleep(6)

    await setup_timeline(browser)
    await asyncio.sleep(2)

    # Select the clip on timeline
    await browser.page.mouse.click(350, 120)
    await asyncio.sleep(2)

    await explore_main(browser)
    await search_for_mastering(browser)
    await explore_export(browser)
    await explore_right_click_clip(browser)
    await explore_more_options(browser)
    await explore_track_more_options(browser)
    await explore_bottom_bar(browser)
    await explore_extract_stems(browser)
    await explore_remix_edit(browser)

    await browser.close()

asyncio.run(main())
