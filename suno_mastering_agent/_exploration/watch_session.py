#!/usr/bin/env python3
"""Watch session - takes screenshots every 5 seconds while user navigates.
Also captures all DOM state at each snapshot."""
import asyncio
import json
import os
import time
from src.browser import BrowserController

OUTPUT_DIR = "/tmp/suno_watch"
os.makedirs(OUTPUT_DIR, exist_ok=True)


async def capture_state(browser, idx):
    """Capture screenshot + full interactive element state."""
    fname = f"{idx:04d}"
    await browser.screenshot(os.path.join(OUTPUT_DIR, f"{fname}.png"))

    # Capture all interactive elements with positions
    state = await browser.evaluate("""() => {
        const elements = [];

        // All buttons
        document.querySelectorAll('button').forEach(el => {
            if (el.offsetParent === null) return;
            const r = el.getBoundingClientRect();
            if (r.width === 0) return;
            elements.push({
                type: 'button',
                text: (el.textContent || '').trim().substring(0, 60),
                ariaLabel: el.getAttribute('aria-label'),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        });

        // All sliders/faders/knobs
        document.querySelectorAll('[role=slider], input[type=range], [class*=fader], [class*=knob], [class*=slider]').forEach(el => {
            if (el.offsetParent === null) return;
            const r = el.getBoundingClientRect();
            if (r.width === 0) return;
            elements.push({
                type: 'slider',
                ariaLabel: el.getAttribute('aria-label'),
                ariaValueNow: el.getAttribute('aria-valuenow'),
                ariaValueMin: el.getAttribute('aria-valuemin'),
                ariaValueMax: el.getAttribute('aria-valuemax'),
                className: typeof el.className === 'string' ? el.className.substring(0, 80) : '',
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        });

        // All inputs
        document.querySelectorAll('input, textarea, select').forEach(el => {
            if (el.offsetParent === null) return;
            const r = el.getBoundingClientRect();
            if (r.width === 0) return;
            elements.push({
                type: 'input',
                inputType: el.getAttribute('type'),
                placeholder: el.getAttribute('placeholder'),
                value: (el.value || '').substring(0, 50),
                x: Math.round(r.x), y: Math.round(r.y),
                w: Math.round(r.width), h: Math.round(r.height),
            });
        });

        // Dialogs/menus
        document.querySelectorAll('[role=dialog], [role=menu], [data-state=open]').forEach(el => {
            if (el.offsetParent === null && el.getAttribute('data-state') !== 'open') return;
            elements.push({
                type: 'dialog',
                text: (el.textContent || '').trim().substring(0, 300),
                role: el.getAttribute('role'),
            });
        });

        // Current URL
        const url = window.location.href;
        const pageText = document.body.innerText.substring(0, 500);

        return { url, pageText, elements, timestamp: Date.now() };
    }""")

    with open(os.path.join(OUTPUT_DIR, f"{fname}.json"), 'w') as f:
        json.dump(state, f, indent=2, default=str)

    return state


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    await browser.navigate('https://suno.com/studio')
    await asyncio.sleep(5)

    print("=" * 60)
    print("WATCHING SESSION - Screenshots every 5 seconds")
    print("Navigate through Suno. Show me everything.")
    print(f"Saving to: {OUTPUT_DIR}")
    print("=" * 60)

    # Take screenshots for 10 minutes
    for i in range(120):
        state = await capture_state(browser, i)
        url = state.get('url', '')
        n_elements = len(state.get('elements', []))
        sliders = [e for e in state.get('elements', []) if e['type'] == 'slider']
        print(f"[{i:3d}] {url.split('/')[-1][:30]:30s} | {n_elements:3d} elements | {len(sliders)} sliders")
        await asyncio.sleep(5)

    await browser.close()
    print(f"\nSession complete. {120} snapshots saved to {OUTPUT_DIR}")


asyncio.run(main())
