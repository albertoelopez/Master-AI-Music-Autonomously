"""Mixing skills - volume, pan, solo, mute."""
import asyncio
from .base import Skill, SkillResult, console


# Track control positions (calibrated Feb 28 2026)
# Volume fader-knob is at x≈275, pan slider ~28px below
# Track number at x≈117, Solo (S) at x≈145, track controls x=130-310
TRACK_FADER_BASE_X = 275
TRACK_SPACING_Y = 90  # Approximate spacing between tracks


class MixingSkill(Skill):
    """Volume, pan, solo, mute operations on tracks."""

    def _track_y(self, track_index: int) -> int:
        """Get the Y position for a track (0-based)."""
        return 173 + track_index * TRACK_SPACING_Y

    async def set_volume(self, track_index: int, db_offset: float) -> SkillResult:
        """Set track volume by dragging the fader.

        Args:
            track_index: 0-based track index
            db_offset: Positive = louder (drag right), negative = quieter (drag left).
                       Each pixel ≈ 0.5dB. Range is roughly -inf to +6dB.
        """
        y = self._track_y(track_index)
        x = TRACK_FADER_BASE_X

        # Calculate drag distance (roughly 2 pixels per dB)
        drag_pixels = int(db_offset * 2)
        await self.drag(x, y, x + drag_pixels, y, steps=10)

        return SkillResult(success=True, message=f"Track {track_index + 1} volume: {db_offset:+.1f}dB offset")

    async def set_pan(self, track_index: int, pan_value: float) -> SkillResult:
        """Set track pan position.

        Args:
            track_index: 0-based track index
            pan_value: -1.0 (full left) to 1.0 (full right), 0 = center
        """
        y = self._track_y(track_index) + 28  # Pan is 28px below volume
        x = TRACK_FADER_BASE_X

        # Center first (double-click)
        await self.page.mouse.dblclick(x, y)
        await self.wait(0.3)

        # Then drag to position (roughly 30px = full range each side)
        drag_pixels = int(pan_value * 30)
        if drag_pixels != 0:
            await self.drag(x, y, x + drag_pixels, y, steps=8)

        side = "L" if pan_value < 0 else "R" if pan_value > 0 else "C"
        return SkillResult(success=True, message=f"Track {track_index + 1} pan: {side} ({pan_value:+.1f})")

    async def solo(self, track_index: int) -> SkillResult:
        """Toggle solo on a track."""
        # Solo button is the "S" button on the track header
        result = await self.browser.evaluate(f"""() => {{
            const buttons = document.querySelectorAll('button');
            let trackCount = 0;
            for (const btn of buttons) {{
                if (btn.textContent.trim() === 'S') {{
                    const r = btn.getBoundingClientRect();
                    if (r.x < 250 && r.y > 60) {{
                        if (trackCount === {track_index}) {{
                            return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
                        }}
                        trackCount++;
                    }}
                }}
            }}
            return null;
        }}""")

        if result:
            await self.click_at(result['x'], result['y'])
            return SkillResult(success=True, message=f"Toggled solo on track {track_index + 1}")
        return SkillResult(success=False, message="Solo button not found")

    async def mute(self, track_index: int) -> SkillResult:
        """Toggle mute on a track (speaker icon)."""
        result = await self.browser.evaluate(f"""() => {{
            const buttons = document.querySelectorAll('button');
            const muteButtons = [];
            for (const btn of buttons) {{
                const r = btn.getBoundingClientRect();
                if (r.x < 250 && r.y > 60 && r.width < 40 && r.height < 40) {{
                    const svg = btn.querySelector('svg');
                    const ariaLabel = btn.getAttribute('aria-label') || '';
                    if (svg && (ariaLabel.includes('mute') || ariaLabel.includes('speaker') || ariaLabel.includes('audio'))) {{
                        muteButtons.push({{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}});
                    }}
                }}
            }}
            return muteButtons[{track_index}] || null;
        }}""")

        if result:
            await self.click_at(result['x'], result['y'])
            return SkillResult(success=True, message=f"Toggled mute on track {track_index + 1}")
        return SkillResult(success=False, message="Mute button not found")

    async def get_track_info(self) -> SkillResult:
        """Get info about all tracks (names, count).

        Track names are in the track control area at x≈130-300, y>100.
        Each track has: number button, name, S(solo), mute, fader, pan, input selector.
        """
        tracks = await self.browser.evaluate("""() => {
            const tracks = [];
            const seen = new Set();
            // Look for track name elements - they have an edit icon nearby
            document.querySelectorAll('*').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.x > 100 && r.x < 310 && r.y > 100 && r.y < 800 && r.width > 60) {
                    const text = el.textContent.trim();
                    // Track names are typically song names, filter out control text
                    if (text.length > 3 && text.length < 80 && !seen.has(text) &&
                        !text.includes('Add Track') && !text.includes('No Input') &&
                        !text.includes('S') && !/^\\d+$/.test(text)) {
                        seen.add(text);
                        tracks.push({name: text.substring(0, 50), y: Math.round(r.y)});
                    }
                }
            });
            return tracks.sort((a, b) => a.y - b.y);
        }""") or []

        return SkillResult(success=True, message=f"{len(tracks)} tracks", data=tracks)
