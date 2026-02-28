#!/usr/bin/env python3
"""Intercept all Suno API calls to discover internal endpoints.

Navigates through key Suno pages while capturing every network request.
Outputs a structured map of all API endpoints, methods, and payloads.
"""
import asyncio
import json
import os
import time
from collections import defaultdict
from src.browser import BrowserController

OUTPUT_DIR = "/tmp/suno_api"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Store all captured requests
captured = []
api_endpoints = defaultdict(list)


def on_request(request):
    """Capture outgoing requests."""
    url = request.url
    # Only capture API calls (skip static assets, images, fonts)
    if any(skip in url for skip in [
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2',
        '.css', '.js', 'fonts.', 'static.', 'cdn.', 'analytics.',
        'google-analytics', 'gtag', 'facebook', 'segment.', 'amplitude.',
        'sentry.', 'intercom', 'clerk.', 'cloudflare'
    ]):
        return

    entry = {
        'timestamp': time.time(),
        'method': request.method,
        'url': url,
        'headers': dict(request.headers),
        'post_data': None,
    }

    try:
        pd = request.post_data
        if pd:
            try:
                entry['post_data'] = json.loads(pd)
            except (json.JSONDecodeError, TypeError):
                entry['post_data'] = str(pd)[:200]
    except Exception:
        entry['post_data'] = '<binary>'

    captured.append(entry)

    # Categorize by domain/path
    if 'suno' in url or 'studio-api' in url or 'api' in url.split('/')[2:3]:
        short = f"{request.method} {url.split('?')[0]}"
        print(f"  [API] {short}")


async def on_response(response):
    """Capture responses for API calls."""
    url = response.url
    if any(skip in url for skip in [
        '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2',
        '.css', '.js', 'fonts.', 'static.', 'cdn.', 'analytics.',
        'google-analytics', 'gtag', 'facebook', 'segment.', 'amplitude.',
        'sentry.', 'intercom', 'clerk.', 'cloudflare'
    ]):
        return

    if 'suno' not in url and 'studio-api' not in url:
        return

    try:
        body = await response.text()
        try:
            body_json = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            body_json = None

        api_endpoints[url.split('?')[0]].append({
            'method': response.request.method,
            'status': response.status,
            'url': url,
            'response_preview': str(body)[:500] if body else None,
            'response_json_keys': list(body_json.keys()) if isinstance(body_json, dict) else None,
            'content_type': response.headers.get('content-type', ''),
        })
    except Exception:
        pass


async def explore_page(browser, name, url, wait=4, actions=None):
    """Navigate to a page and capture API calls."""
    print(f"\n{'='*60}")
    print(f"INTERCEPTING: {name} ({url})")
    print(f"{'='*60}")

    await browser.navigate(url)
    await asyncio.sleep(wait)

    if actions:
        for action_name, action_fn in actions:
            print(f"\n  --- Action: {action_name} ---")
            try:
                await action_fn(browser)
                await asyncio.sleep(2)
            except Exception as e:
                print(f"  Error in {action_name}: {e}")


async def action_scroll_library(browser):
    """Scroll through library to trigger pagination API calls."""
    for i in range(3):
        await browser.page.evaluate('window.scrollBy(0, 800)')
        await asyncio.sleep(1.5)


async def action_click_create_tabs(browser):
    """Click through create tabs."""
    for tab in ['Custom', 'Sounds', 'Simple']:
        try:
            await browser.page.click(f'text={tab}', timeout=3000)
            await asyncio.sleep(2)
        except Exception:
            pass


async def action_open_export(browser):
    """Open the export dropdown."""
    try:
        await browser.page.click('text=Export', timeout=3000)
        await asyncio.sleep(2)
        await browser.page.keyboard.press('Escape')
    except Exception:
        pass


async def action_click_workspace_songs(browser):
    """Click on a song in workspace to trigger detail API."""
    try:
        songs = await browser.page.query_selector_all('a[href*="/song/"]')
        if songs:
            await songs[0].click()
            await asyncio.sleep(3)
            await browser.page.go_back()
            await asyncio.sleep(2)
    except Exception:
        pass


async def action_search(browser):
    """Perform a search to trigger search API."""
    try:
        search_input = await browser.page.query_selector('input[placeholder*="Search"]')
        if not search_input:
            search_input = await browser.page.query_selector('input[type="search"]')
        if search_input:
            await search_input.fill('soul music')
            await asyncio.sleep(3)
            await search_input.fill('')
    except Exception:
        pass


async def extract_auth(browser):
    """Extract auth tokens/cookies from browser."""
    print(f"\n{'='*60}")
    print("EXTRACTING AUTH TOKENS")
    print(f"{'='*60}")

    # Get cookies
    cookies = await browser.context.cookies()
    suno_cookies = [c for c in cookies if 'suno' in c.get('domain', '')]
    print(f"\n  Suno cookies ({len(suno_cookies)}):")
    for c in suno_cookies:
        name = c['name']
        val = c['value'][:50] + '...' if len(c['value']) > 50 else c['value']
        print(f"    {name} = {val}")

    # Check localStorage/sessionStorage for tokens
    auth_data = await browser.evaluate("""() => {
        const data = {};
        // localStorage
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (key.toLowerCase().includes('token') ||
                key.toLowerCase().includes('auth') ||
                key.toLowerCase().includes('session') ||
                key.toLowerCase().includes('user') ||
                key.toLowerCase().includes('clerk')) {
                data['localStorage:' + key] = localStorage.getItem(key)?.substring(0, 200);
            }
        }
        // sessionStorage
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            if (key.toLowerCase().includes('token') ||
                key.toLowerCase().includes('auth') ||
                key.toLowerCase().includes('session')) {
                data['sessionStorage:' + key] = sessionStorage.getItem(key)?.substring(0, 200);
            }
        }
        return data;
    }""")

    if auth_data:
        print(f"\n  Auth-related storage ({len(auth_data)} items):")
        for key, val in auth_data.items():
            print(f"    {key} = {val}")

    return {'cookies': suno_cookies, 'storage': auth_data}


async def main():
    browser = BrowserController()
    if not await browser.connect():
        return

    # Attach interceptors
    browser.page.on('request', on_request)
    browser.page.on('response', lambda r: asyncio.ensure_future(on_response(r)))

    # Navigate through every page and capture API calls
    pages = [
        ("Home", "https://suno.com", 5, None),
        ("Library - Songs", "https://suno.com/me", 5, [
            ("Scroll for pagination", action_scroll_library),
            ("Click song detail", action_click_workspace_songs),
        ]),
        ("Library - Workspaces", "https://suno.com/me?tab=workspaces", 4, None),
        ("Create", "https://suno.com/create", 5, [
            ("Click tabs", action_click_create_tabs),
        ]),
        ("Search", "https://suno.com/search", 4, [
            ("Perform search", action_search),
        ]),
        ("Studio", "https://suno.com/studio", 6, [
            ("Open export", action_open_export),
        ]),
    ]

    for name, url, wait, actions in pages:
        await explore_page(browser, name, url, wait, actions)

    # Extract auth info
    auth_info = await extract_auth(browser)

    # Save all results
    print(f"\n{'='*60}")
    print("RESULTS SUMMARY")
    print(f"{'='*60}")

    print(f"\nTotal requests captured: {len(captured)}")
    print(f"Unique API endpoints: {len(api_endpoints)}")

    # Group by base URL
    api_by_domain = defaultdict(list)
    for endpoint, calls in api_endpoints.items():
        from urllib.parse import urlparse
        parsed = urlparse(endpoint)
        domain = parsed.netloc
        api_by_domain[domain].append({
            'path': parsed.path,
            'methods': list(set(c['method'] for c in calls)),
            'statuses': list(set(c['status'] for c in calls)),
            'response_keys': calls[0].get('response_json_keys'),
            'content_type': calls[0].get('content_type', ''),
            'example_response': calls[0].get('response_preview', '')[:300],
        })

    for domain, endpoints in sorted(api_by_domain.items()):
        print(f"\n  [{domain}] ({len(endpoints)} endpoints)")
        for ep in sorted(endpoints, key=lambda x: x['path']):
            methods = ', '.join(ep['methods'])
            print(f"    {methods:6s} {ep['path']}")
            if ep['response_keys']:
                print(f"           keys: {ep['response_keys']}")

    # Save full data
    output = {
        'captured_requests': captured,
        'api_endpoints': {k: v for k, v in api_endpoints.items()},
        'api_by_domain': {k: v for k, v in api_by_domain.items()},
        'auth_info': {
            'cookies': auth_info['cookies'],
            'storage': auth_info.get('storage', {}),
        },
    }

    output_path = os.path.join(OUTPUT_DIR, 'api_map.json')
    with open(output_path, 'w') as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nFull API map saved to: {output_path}")

    # Save a clean endpoint summary
    summary_path = os.path.join(OUTPUT_DIR, 'endpoints_summary.txt')
    with open(summary_path, 'w') as f:
        for domain, endpoints in sorted(api_by_domain.items()):
            f.write(f"\n=== {domain} ===\n")
            for ep in sorted(endpoints, key=lambda x: x['path']):
                methods = ', '.join(ep['methods'])
                f.write(f"  {methods:6s} {ep['path']}\n")
                if ep['response_keys']:
                    f.write(f"         Response keys: {ep['response_keys']}\n")
                if ep['example_response']:
                    f.write(f"         Preview: {ep['example_response'][:200]}\n")
    print(f"Endpoint summary saved to: {summary_path}")

    await browser.close()


asyncio.run(main())
