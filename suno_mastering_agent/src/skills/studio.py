"""Studio skills - clip selection, tab switching, export, timeline operations."""
import asyncio
from .base import Skill, SkillResult, console


class StudioSkill(Skill):
    """Core Studio operations: clip selection, tab switching, export."""

    async def select_clip(self, track_index: int = 0) -> SkillResult:
        """Click a clip on the timeline to select it.

        Args:
            track_index: 0-based track index (0=first track, 1=second, etc.)

        Track layout (calibrated Feb 28 2026):
        - Track controls area: x=108-310, track 1 starts at y≈140
        - Timeline/waveform area: x=316+, each track is ~90px tall
        - First track waveform center: y≈170, second: y≈260, third: y≈350
        """
        # Each track is approximately 90px tall, starting at y≈140
        base_y = 170
        track_height = 90
        y = base_y + track_index * track_height

        # Click in the waveform/timeline area (x > 316 where canvases are)
        for x in [500, 600, 700]:
            await self.click_at(x, y)
            await self.wait(1)

            text = await self.get_right_panel_text()
            if 'Clip' in text and 'Track' in text:
                return SkillResult(success=True, message=f"Selected clip on track {track_index + 1}")

        return SkillResult(success=False, message="Could not select clip")

    async def switch_to_clip_tab(self) -> SkillResult:
        """Switch to the Clip tab in the right panel."""
        # Clip tab button: center at (1088, 85) - calibrated Feb 28 2026
        await self.click_at(1088, 85)
        await self.wait(1)
        return SkillResult(success=True, message="Switched to Clip tab")

    async def switch_to_track_tab(self) -> SkillResult:
        """Switch to the Track tab in the right panel (where EQ lives)."""
        # Track tab button: center at (1150, 85) - calibrated Feb 28 2026
        await self.click_at(1150, 85)
        await self.wait(1.5)

        text = await self.get_right_panel_text()
        if 'EQ' in text or 'Preset' in text or 'Flat' in text or 'Band' in text:
            return SkillResult(success=True, message="Switched to Track tab (EQ visible)")
        return SkillResult(success=True, message="Switched to Track tab")

    async def drag_clip_to_timeline(self, sidebar_index: int = 0) -> SkillResult:
        """Drag a clip from the left sidebar to the timeline.

        Sidebar thumbnails are at x≈79, starting at y≈150 with ~65px spacing.
        Timeline canvas starts at x=316, y=110.
        """
        # Find sidebar thumbnails (images with x < 150)
        sidebar = await self.browser.evaluate("""() => {
            const items = [];
            document.querySelectorAll('img').forEach(el => {
                const r = el.getBoundingClientRect();
                if (r.x < 150 && r.y > 60 && r.width > 20 && r.height > 20 && el.offsetParent !== null) {
                    items.push({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)});
                }
            });
            return items;
        }""") or []

        if sidebar_index >= len(sidebar):
            return SkillResult(success=False, message=f"No sidebar item at index {sidebar_index}")

        src = sidebar[sidebar_index]
        # Drag to center of timeline area
        await self.drag(src['x'], src['y'], 600, 300)
        await self.wait(3)

        # Handle tempo dialog
        try:
            await self.page.click("text=Confirm", timeout=3000)
            await self.wait(5)
        except Exception:
            pass

        return SkillResult(success=True, message="Dragged clip to timeline")

    async def export_full_song(self) -> SkillResult:
        """Export the full song as WAV."""
        # Click Export dropdown
        if not await self.click_button("Export"):
            return SkillResult(success=False, message="Export button not found")
        await self.wait(1)

        # Click Full Song
        if not await self.click_button("Full Song"):
            return SkillResult(success=False, message="Full Song option not found")
        await self.wait(2)

        return SkillResult(success=True, message="Export started (Full Song WAV)")

    async def export_selected_range(self) -> SkillResult:
        """Export the selected time range as WAV."""
        if not await self.click_button("Export"):
            return SkillResult(success=False, message="Export button not found")
        await self.wait(1)

        if not await self.click_button("Selected Time Range"):
            return SkillResult(success=False, message="Selected Time Range option not found")
        await self.wait(2)

        return SkillResult(success=True, message="Export started (Selected Time Range WAV)")

    async def export_multitrack(self) -> SkillResult:
        """Export multitrack (each track as separate WAV)."""
        if not await self.click_button("Export"):
            return SkillResult(success=False, message="Export button not found")
        await self.wait(1)

        if not await self.click_button("Multitrack"):
            return SkillResult(success=False, message="Multitrack option not found")
        await self.wait(2)

        return SkillResult(success=True, message="Export started (Multitrack WAV)")

    async def extract_stems(self, mode: str = "all") -> SkillResult:
        """Extract stems from the selected clip.

        Args:
            mode: 'all' for all detected stems (up to 12), 'vocals' for vocals+instrumental
        """
        if not await self.click_button("Extract Stems"):
            return SkillResult(success=False, message="Extract Stems button not found")
        await self.wait(1)

        target = "All Detected Stems" if mode == "all" else "Vocals + Instrumental"
        if not await self.click_button(target):
            # Try partial match
            await self.click_button("All Detected" if mode == "all" else "Vocals")
        await self.wait(2)

        return SkillResult(success=True, message=f"Stem extraction started ({mode})")

    async def get_track_count(self) -> SkillResult:
        """Get the number of tracks in the current project.

        Track number buttons are at x≈106-128, y>100, with text "1", "2", etc.
        """
        count = await self.browser.evaluate("""() => {
            let count = 0;
            document.querySelectorAll('button').forEach(btn => {
                const text = btn.textContent.trim();
                const r = btn.getBoundingClientRect();
                if (/^\\d+$/.test(text) && r.x < 150 && r.x > 80 && r.y > 100 && r.y < 800 && r.width < 40) {
                    count = Math.max(count, parseInt(text));
                }
            });
            return count;
        }""") or 0

        return SkillResult(success=True, message=f"{count} tracks", data=count)
