"""Phase 1: Fill form, trigger CAPTCHA, save cell images, and WAIT.

The browser stays open on CDP port 9222 so Phase 2 can connect and click cells.
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.browser import BrowserController
from src.skills import NavigateSkill, ModalSkill, CreateSkill


async def main():
    browser = BrowserController(headless=False, cdp_port=9222)
    ok = await browser.connect()
    if not ok:
        print("FAIL: Browser launch")
        return

    nav = NavigateSkill(browser)
    modal = ModalSkill(browser)
    create = CreateSkill(browser)
    page = browser.page

    # Navigate to Create
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)
    await nav.to_create()
    await modal.dismiss_all()
    await asyncio.sleep(1)

    # Fill form
    await create.switch_to_custom()
    await create._dismiss_modals()
    await create.set_lyrics("""[Verse 1]
Neon lights flicker on the midnight train
Strangers passing shadows through the windowpane
City hums a melody that no one wrote
Carried on the wind like a half-remembered note

[Chorus]
We are the signal in the noise
We are the quiet steady voice
Through the static we will rise
Dancing underneath electric skies

[Verse 2]
Every screen a window to a thousand lives
Binary heartbeats keeping time
The future whispers from a satellite above
Sending down a frequency of love

[Chorus]
We are the signal in the noise
We are the quiet steady voice
Through the static we will rise
Dancing underneath electric skies

[Bridge]
Turn the dial up, let it glow
Every wavelength has a soul
In the echo, find your own
You were never meant to walk alone

[Outro]
Signal in the noise
Signal in the noise""")
    await create._dismiss_modals()
    await create.set_styles("synthwave, electronic pop, dreamy, retro-futuristic, 80s inspired")
    await create._dismiss_modals()
    await create.set_title("Signal in the Noise")
    await create._dismiss_modals()

    print("\n=== Form filled. Clicking Create... ===\n")
    await create.click_button("Create")
    await asyncio.sleep(5)

    # Check for CAPTCHA
    iframe_pos = await browser.evaluate("""() => {
        const iframes = document.querySelectorAll('iframe');
        for (const f of iframes) {
            if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                const r = f.getBoundingClientRect();
                if (r.width > 100) return {x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
            }
        }
        return null;
    }""")

    if not iframe_pos:
        print("No CAPTCHA! Song should be creating.")
        await asyncio.sleep(30)
        await browser.close()
        return

    print(f"hCaptcha iframe at ({iframe_pos['x']},{iframe_pos['y']}) {iframe_pos['w']}x{iframe_pos['h']}")

    # Get the challenge prompt
    captcha_frame = None
    for frame in page.frames:
        if "hcaptcha" in frame.url and "challenge" in frame.url:
            captcha_frame = frame
            break

    prompt = ""
    if captcha_frame:
        prompt = await captcha_frame.evaluate("""() => {
            const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
            return el ? el.textContent.trim() : '';
        }""")

    print(f"Challenge: {prompt}")

    # Save screenshot
    os.makedirs("/tmp/suno_skills", exist_ok=True)
    await browser.screenshot("/tmp/suno_skills/captcha_phase1.png")

    # Fetch individual cell images
    if captcha_frame:
        img_urls = await captcha_frame.evaluate("""() => {
            const urls = [];
            document.querySelectorAll('.task-image .image').forEach(img => {
                const style = window.getComputedStyle(img);
                const bg = style.backgroundImage || '';
                const match = bg.match(/url\\("(.+?)"\\)/);
                urls.push(match ? match[1] : null);
            });
            return urls;
        }""")

        import base64
        print(f"\nFetching {len(img_urls)} cell images...")
        for i, url in enumerate(img_urls):
            row, col = divmod(i, 3)
            if not url:
                print(f"  Cell [{row},{col}]: no URL")
                continue
            try:
                img_data = await page.evaluate(f"""async () => {{
                    try {{
                        const resp = await fetch("{url}");
                        const blob = await resp.blob();
                        return new Promise((resolve) => {{
                            const reader = new FileReader();
                            reader.onloadend = () => resolve(reader.result);
                            reader.readAsDataURL(blob);
                        }});
                    }} catch(e) {{
                        return null;
                    }}
                }}""")
                if img_data and img_data.startswith('data:'):
                    header, b64 = img_data.split(',', 1)
                    cell_path = f"/tmp/suno_skills/cell_{row}_{col}.png"
                    with open(cell_path, 'wb') as f:
                        f.write(base64.b64decode(b64))
                    print(f"  Cell [{row},{col}]: saved")
                else:
                    print(f"  Cell [{row},{col}]: fetch failed")
            except Exception as e:
                print(f"  Cell [{row},{col}]: error - {e}")

    # Write state file for Phase 2
    import json
    state = {
        "iframe": iframe_pos,
        "prompt": prompt,
        "status": "waiting_for_clicks"
    }
    with open("/tmp/suno_skills/captcha_state.json", "w") as f:
        json.dump(state, f, indent=2)

    print(f"\n=== READY FOR PHASE 2 ===")
    print(f"Iframe: ({iframe_pos['x']},{iframe_pos['y']})")
    print(f"Challenge: {prompt}")
    print(f"Cell images: /tmp/suno_skills/cell_R_C.png")
    print(f"State: /tmp/suno_skills/captcha_state.json")
    print(f"\nBrowser will stay open for 10 minutes. Run captcha_phase2.py to click cells.")

    # Wait for up to 10 minutes, checking if CAPTCHA goes away
    for tick in range(120):  # 120 * 5s = 10 min
        await asyncio.sleep(5)
        still = await browser.evaluate("""() => {
            const iframes = document.querySelectorAll('iframe');
            for (const f of iframes) {
                if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                    const r = f.getBoundingClientRect();
                    return r.width > 100 && r.x > 0;
                }
            }
            return false;
        }""")
        if not still:
            print(f"\n[{tick*5}s] CAPTCHA dismissed!")
            await asyncio.sleep(2)

            # Re-click Create
            print("Re-clicking Create...")
            await create.click_button("Create")
            await asyncio.sleep(5)

            # Check for another CAPTCHA
            another = await browser.evaluate("""() => {
                const iframes = document.querySelectorAll('iframe');
                for (const f of iframes) {
                    if (f.src.includes('hcaptcha') && f.src.includes('challenge')) {
                        const r = f.getBoundingClientRect();
                        return r.width > 100;
                    }
                }
                return false;
            }""")
            if another:
                print("Another CAPTCHA! Saving new images...")
                # Re-save cell images for the new challenge
                captcha_frame = None
                for frame in page.frames:
                    if "hcaptcha" in frame.url and "challenge" in frame.url:
                        captcha_frame = frame
                        break
                if captcha_frame:
                    prompt = await captcha_frame.evaluate("""() => {
                        const el = document.querySelector('.prompt-text, h2, [class*=prompt]');
                        return el ? el.textContent.trim() : '';
                    }""")
                    print(f"New challenge: {prompt}")
                continue
            else:
                print("No more CAPTCHA! Song should be generating.")
                break

        if tick % 12 == 0 and tick > 0:
            print(f"[{tick*5}s] Waiting for Phase 2 clicks...")

    await asyncio.sleep(5)
    await browser.screenshot("/tmp/suno_skills/phase1_final.png")
    print("\nPhase 1 done. Keeping browser alive for 2 more minutes...")
    await asyncio.sleep(120)
    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
