#!/usr/bin/env python3
"""Deep exploration of the Studio right panel when a clip is selected.

Specifically looking for:
- Mastering controls
- EQ
- Sliders
- Every expandable section
- Every button and what it opens
"""
import asyncio
import json
import os
from src.browser import BrowserController

OUTPUT_DIR = "/tmp/suno_explore"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Capture API calls during exploration
api_calls = []


def on_request(request):
    url = request.url
    if 'studio-api' in url or ('suno' in url and '/api/' in url):
        try:
            pd = request.post_data
        except Exception:
            pd = None
        entry = {
            'method': request.method,
            'url': url,
        }
        if pd:
            try:
                entry['body'] = json.loads(pd)
            except Exception:
                entry['body'] = str(pd)[:200]
        api_calls.append(entry)
        print(f"  [API] {request.method} {url.split('?')[0]}")


async def dump_right_panel(browser, label):
    """Capture everything visible in the right panel."""
    data = await browser.evaluate("""() => {
        // Get the right panel (usually the rightmost column)
        const vw = window.innerWidth;
        const rightThreshold = vw * 0.6;

        // All interactive elements in right portion
        const elements = [...document.querySelectorAll('button, input, select, [role=slider], [role=checkbox], [role=switch], label, a, [data-testid], [class*=slider], [class*=knob], [class*=fader], [class*=eq], [class*=master]')]
            .filter(el => {
                const rect = el.getBoundingClientRect();
                return rect.left > rightThreshold && el.offsetParent !== null && rect.width > 0;
            })
            .map(el => ({
                tag: el.tagName,
                text: (el.textContent || '').trim().substring(0, 80),
                ariaLabel: el.getAttribute('aria-label'),
                role: el.getAttribute('role'),
                type: el.getAttribute('type'),
                className: typeof el.className === 'string' ? el.className.substring(0, 100) : '',
                dataState: el.getAttribute('data-state'),
                dataTestId: el.getAttribute('data-testid'),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
                disabled: el.disabled || false,
            }));

        // Also get all visible text in right panel
        const rightText = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
            const node = walker.currentNode;
            const rect = node.parentElement?.getBoundingClientRect();
            if (rect && rect.left > rightThreshold && rect.width > 0 && node.textContent.trim()) {
                rightText.push(node.textContent.trim());
            }
        }

        // Find sliders specifically
        const sliders = [...document.querySelectorAll('[role=slider], input[type=range], [class*=slider], [class*=Slider]')]
            .filter(el => el.offsetParent !== null)
            .map(el => ({
                tag: el.tagName,
                role: el.getAttribute('role'),
                ariaLabel: el.getAttribute('aria-label'),
                ariaValueNow: el.getAttribute('aria-valuenow'),
                ariaValueMin: el.getAttribute('aria-valuemin'),
                ariaValueMax: el.getAttribute('aria-valuemax'),
                value: el.value || '',
                className: typeof el.className === 'string' ? el.className.substring(0, 100) : '',
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
            }));

        return {
            elements: elements,
            rightText: [...new Set(rightText)].join(' | '),
            sliders: sliders,
            totalElements: elements.length,
        };
    }""")
    return data


async def find_and_click_show_more(browser):
    """Find and click all 'Show More' or expandable sections."""
    result = await browser.evaluate("""() => {
        const expandables = [...document.querySelectorAll('button, [role=button], [data-state]')]
            .filter(el => {
                const text = (el.textContent || '').trim().toLowerCase();
                return (text.includes('show more') || text.includes('more') ||
                        text.includes('expand') || text.includes('advanced') ||
                        el.getAttribute('data-state') === 'closed') &&
                       el.offsetParent !== null;
            })
            .map(el => ({
                text: (el.textContent || '').trim().substring(0, 60),
                ariaLabel: el.getAttribute('aria-label'),
                dataState: el.getAttribute('data-state'),
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
            }));
        return expandables;
    }""")
    return result


async def click_at(browser, x, y, label=""):
    """Click at coordinates and report what changed."""
    print(f"  Clicking at ({x}, {y}) - {label}")
    await browser.page.mouse.click(x, y)
    await asyncio.sleep(2)


async def main():
    browser = BrowserController()
    if not await browser.connect()                                                                                 :
        return

    # Attach API interceptor
    browser.page.on('request', on_request)

    # Navigate to Studio
    await browser.navigate('https://suno.com/studio')
    await asyncio.sleep(6)
    await browser.screenshot(os.path.join(OUTPUT_DIR, '00_studio_initial.png'))

    # Check if clip is already on timeline
    text = await browser.evaluate('() => document.body.innerText.substring(0, 2000)')

    # First, get the full page layout
    print("\n" + "=" * 60)
    print("STEP 1: INITIAL STATE")
    print("=" * 60)
    data = await dump_right_panel(browser, "initial")
    print(f"  Right panel elements: {data['totalElements']}")
    print(f"  Sliders: {len(data['sliders'])}")
    print(f"  Text: {data['rightText'][:500]}")

    # Check if we need to drag a clip to timeline
    if 'Remix/Edit' not in text and 'Clip Settings' not in text:
        print("\n  Need to set up clip on timeline...")
        # Click first thumbnail in sidebar
        await browser.page.mouse.click(75, 145)
        await asyncio.sleep(1)
        # Drag to timeline
        await browser.page.mouse.move(75, 150)
        await browser.page.mouse.down()
        for i in range(15):
            x = 75 + (500 - 75) * (i + 1) / 15
            y = 150 + (350 - 150) * (i + 1) / 15
            await browser.page.mouse.move(x, y)
            await asyncio.sleep(0.03)
        await browser.page.mouse.up()
        await asyncio.sleep(3)

        # Confirm tempo dialog if it appears
        try:
            await browser.page.click('text=Confirm', timeout=3000)
            await asyncio.sleep(3)
            print("  Confirmed tempo dialog")
        except Exception:
            pass

    # Click on the clip to select it
    print("\n" + "=" * 60)
    print("STEP 2: SELECT CLIP ON TIMELINE")
    print("=" * 60)

    # Click on a clip in the timeline area
    await browser.page.mouse.click(350, 120)
    await asyncio.sleep(2)
    await browser.screenshot(os.path.join(OUTPUT_DIR, '01_clip_selected.png'))

    data = await dump_right_panel(browser, "clip_selected")
    print(f"  Right panel elements: {data['totalElements']}")
    print(f"  Sliders: {len(data['sliders'])}")
    for s in data['sliders']:
        print(f"    Slider: {json.dumps(s)}")
    print(f"  Text: {data['rightText'][:500]}")
    print(f"\n  All elements:")
    for el in data['elements']:
        if el['text'] or el['ariaLabel']:
            print(f"    [{el['tag']}] {el['text'][:40]} | aria={el['ariaLabel']} | role={el['role']} | ({el['x']},{el['y']})")

    # Find "Show More" buttons
    print("\n" + "=" * 60)
    print("STEP 3: FIND AND CLICK 'SHOW MORE'")
    print("=" * 60)
    expandables = await find_and_click_show_more(browser)
    print(f"  Found {len(expandables)} expandable elements:")
    for exp in expandables:
        print(f"    {json.dumps(exp)}")

    # Click each "Show More"
    for exp in expandables:
        if 'show more' in exp['text'].lower():
            await click_at(browser, exp['x'] + 30, exp['y'] + 10, f"Show More: {exp['text']}")
            await browser.screenshot(os.path.join(OUTPUT_DIR, '02_show_more.png'))
            data = await dump_right_panel(browser, "after_show_more")
            print(f"  After Show More - elements: {data['totalElements']}, sliders: {len(data['sliders'])}")
            print(f"  Text: {data['rightText'][:500]}")
            for s in data['sliders']:
                print(f"    Slider: {json.dumps(s)}")
            for el in data['elements']:
                if el['text'] or el['ariaLabel']:
                    print(f"    [{el['tag']}] {el['text'][:40]} | aria={el['ariaLabel']} | role={el['role']} | ({el['x']},{el['y']})")

    # Now look for EVERY button on the right panel and click each one
    print("\n" + "=" * 60)
    print("STEP 4: CLICK EVERY BUTTON ON RIGHT PANEL")
    print("=" * 60)

    buttons = await browser.evaluate("""() => {
        const vw = window.innerWidth;
        const rightThreshold = vw * 0.6;
        return [...document.querySelectorAll('button')]
            .filter(el => {
                const rect = el.getBoundingClientRect();
                return rect.left > rightThreshold && el.offsetParent !== null && rect.width > 0;
            })
            .map(el => ({
                text: (el.textContent || '').trim().substring(0, 60),
                ariaLabel: el.getAttribute('aria-label'),
                x: Math.round(el.getBoundingClientRect().x + el.getBoundingClientRect().width / 2),
                y: Math.round(el.getBoundingClientRect().y + el.getBoundingClientRect().height / 2),
            }))
            .filter(b => b.text || b.ariaLabel);
    }""")

    print(f"  Found {len(buttons)} buttons on right panel:")
    for btn in buttons:
        label = btn['text'] or btn['ariaLabel']
        print(f"    '{label}' at ({btn['x']}, {btn['y']})")

    # Click each non-destructive button to see what happens
    safe_buttons = [b for b in buttons if not any(
        skip in (b['text'] + (b['ariaLabel'] or '')).lower()
        for skip in ['delete', 'remove', 'close']
    )]

    for btn in safe_buttons:
        label = btn['text'] or btn['ariaLabel']
        print(f"\n  --- Clicking: '{label}' ---")
        await click_at(browser, btn['x'], btn['y'], label)

        # Check for new menus/dialogs
        menus = await browser.evaluate("""() => {
            const selectors = [
                '[role=menu]', '[role=dialog]', '[role=listbox]',
                '[data-state=open]', '[data-radix-popper-content-wrapper]',
                '.popover', '.dropdown-menu', '[role=tabpanel]'
            ];
            const found = [];
            for (const sel of selectors) {
                const els = document.querySelectorAll(sel);
                for (const el of els) {
                    if (el.offsetParent !== null || el.getAttribute('data-state') === 'open') {
                        found.push({
                            selector: sel,
                            text: el.textContent.trim().substring(0, 500),
                        });
                    }
                }
            }
            return found;
        }""")

        if menus:
            for m in menus:
                print(f"    Menu/Dialog: {m['text'][:200]}")

        # Check for new sliders
        sliders = await browser.evaluate("""() => {
            return [...document.querySelectorAll('[role=slider], input[type=range], [class*=slider], [class*=Slider]')]
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    ariaLabel: el.getAttribute('aria-label'),
                    ariaValueNow: el.getAttribute('aria-valuenow'),
                    className: typeof el.className === 'string' ? el.className.substring(0, 80) : '',
                    x: Math.round(el.getBoundingClientRect().x),
                    y: Math.round(el.getBoundingClientRect().y),
                }));
        }""")

        if sliders:
            print(f"    SLIDERS FOUND: {len(sliders)}")
            for s in sliders:
                print(f"      {json.dumps(s)}")

        # Take screenshot
        fname = label.replace('/', '_').replace(' ', '_')[:30]
        await browser.screenshot(os.path.join(OUTPUT_DIR, f'03_btn_{fname}.png'))

        # Close any menus/dialogs
        await browser.page.keyboard.press('Escape')
        await asyncio.sleep(1)

    # STEP 5: Explore the "Clip" and "Track" tabs at top of right panel
    print("\n" + "=" * 60)
    print("STEP 5: CLIP vs TRACK TABS")
    print("=" * 60)

    for tab_name in ['Clip', 'Track']:
        try:
            # These tabs are in the upper right area
            tab_el = await browser.page.query_selector(f'button:has-text("{tab_name}")')
            if tab_el:
                box = await tab_el.bounding_box()
                if box and box['x'] > browser.page.viewport_size['width'] * 0.5:
                    await tab_el.click()
                    await asyncio.sleep(2)
                    print(f"\n  --- {tab_name} Tab ---")
                    await browser.screenshot(os.path.join(OUTPUT_DIR, f'04_tab_{tab_name}.png'))
                    data = await dump_right_panel(browser, f"tab_{tab_name}")
                    print(f"  Elements: {data['totalElements']}, Sliders: {len(data['sliders'])}")
                    print(f"  Text: {data['rightText'][:500]}")
                    for s in data['sliders']:
                        print(f"    Slider: {json.dumps(s)}")
                    for el in data['elements']:
                        if el['text'] or el['ariaLabel']:
                            print(f"    [{el['tag']}] {el['text'][:40]} | aria={el['ariaLabel']} | ({el['x']},{el['y']})")
        except Exception as e:
            print(f"  Error with {tab_name} tab: {e}")

    # STEP 6: Check the full page for ALL sliders anywhere
    print("\n" + "=" * 60)
    print("STEP 6: ALL SLIDERS ON PAGE")
    print("=" * 60)
    all_sliders = await browser.evaluate("""() => {
        return [...document.querySelectorAll('[role=slider], input[type=range], [class*=slider], [class*=Slider], [class*=knob], [class*=fader], [class*=volume], [class*=Volume], [class*=gain], [class*=Gain]')]
            .filter(el => el.offsetParent !== null)
            .map(el => ({
                tag: el.tagName,
                ariaLabel: el.getAttribute('aria-label'),
                ariaValueNow: el.getAttribute('aria-valuenow'),
                ariaValueMin: el.getAttribute('aria-valuemin'),
                ariaValueMax: el.getAttribute('aria-valuemax'),
                role: el.getAttribute('role'),
                type: el.getAttribute('type'),
                className: typeof el.className === 'string' ? el.className.substring(0, 120) : '',
                x: Math.round(el.getBoundingClientRect().x),
                y: Math.round(el.getBoundingClientRect().y),
                w: Math.round(el.getBoundingClientRect().width),
                h: Math.round(el.getBoundingClientRect().height),
            }));
    }""")
    print(f"  Total sliders found: {len(all_sliders)}")
    for s in all_sliders:
        print(f"    {json.dumps(s)}")

    # STEP 7: Search for mastering keywords in ALL elements
    print("\n" + "=" * 60)
    print("STEP 7: MASTERING KEYWORD SEARCH (DEEP)")
    print("=" * 60)
    mastering_search = await browser.evaluate("""() => {
        const keywords = ['master', 'mastering', 'loudness', 'lufs', 'limiter',
                          'compressor', 'eq', 'equalizer', 'reverb', 'effect',
                          'fx', 'normalize', 'gain', 'volume', 'pan', 'mix',
                          'bus', 'send', 'plugin', 'filter', 'frequency',
                          'low', 'mid', 'high', 'bass', 'treble', 'boost',
                          'cut', 'bandwidth', 'enhance', 'preset'];
        const allText = document.body.innerText.toLowerCase();
        const found = {};
        for (const kw of keywords) {
            const idx = allText.indexOf(kw);
            if (idx >= 0) {
                found[kw] = allText.substring(Math.max(0, idx - 40), idx + 60).trim();
            }
        }

        // Also check all element attributes
        const attrMatches = [];
        document.querySelectorAll('*').forEach(el => {
            const attrs = el.getAttributeNames();
            for (const attr of attrs) {
                const val = el.getAttribute(attr)?.toLowerCase() || '';
                for (const kw of keywords) {
                    if (val.includes(kw) && !val.includes('http')) {
                        attrMatches.push({
                            element: el.tagName,
                            attr: attr,
                            value: val.substring(0, 100),
                            keyword: kw,
                        });
                    }
                }
            }
        });

        return { textMatches: found, attrMatches: attrMatches.slice(0, 50) };
    }""")

    if mastering_search:
        text_matches = mastering_search.get('textMatches', {})
        attr_matches = mastering_search.get('attrMatches', [])
        print(f"  Text matches: {len(text_matches)}")
        for kw, ctx in text_matches.items():
            print(f"    '{kw}': ...{ctx}...")
        print(f"  Attribute matches: {len(attr_matches)}")
        for m in attr_matches:
            print(f"    <{m['element']} {m['attr']}=\"{m['value']}\"> (keyword: {m['keyword']})")

    # Save API calls
    print(f"\n  API calls captured during exploration: {len(api_calls)}")
    for call in api_calls:
        print(f"    {call['method']} {call['url']}")

    # Save all data
    with open(os.path.join(OUTPUT_DIR, 'right_panel_data.json'), 'w') as f:
        json.dump({
            'api_calls': api_calls,
            'mastering_search': mastering_search,
        }, f, indent=2, default=str)

    print(f"\nScreenshots and data saved to {OUTPUT_DIR}")
    await browser.close()


asyncio.run(main())
