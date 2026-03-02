"""Create a song on Suno using the full automation pipeline."""
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

    # Verify login
    await browser.navigate("https://suno.com")
    await asyncio.sleep(5)
    r = await nav.is_logged_in()
    print(f"Login: {r.success} - {r.message}")
    if not r.success:
        print("Not logged in!")
        await browser.close()
        return

    # Navigate to Create
    r = await nav.to_create()
    print(f"Navigate: {r.message}")
    await modal.dismiss_all()
    await asyncio.sleep(1)

    # Create the song
    lyrics = """[Verse 1]
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
Signal in the noise"""

    styles = "synthwave, electronic pop, dreamy, retro-futuristic, 80s inspired"
    title = "Signal in the Noise"

    print(f"\nCreating song: '{title}'")
    print(f"Styles: {styles}")
    print(f"Lyrics: {len(lyrics)} chars\n")

    r = await create.create_song(
        lyrics=lyrics,
        styles=styles,
        title=title,
    )
    print(f"\nResult: {r.success} - {r.message}")

    if r.success:
        print("\nSong creation started! Waiting for generation...")
        # Wait a bit and take a screenshot to see progress
        await asyncio.sleep(10)
        await browser.screenshot("/tmp/suno_skills/song_creating.png")
        print("Screenshot saved to /tmp/suno_skills/song_creating.png")

    await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
