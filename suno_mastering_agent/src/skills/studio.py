"""Studio skills - clip selection, tab switching, export, timeline operations."""
import asyncio
from .base import Skill, SkillResult, console


class StudioSkill(Skill):
    """Core Studio operations: clip selection, tab switching, export."""

    async def _get_track_positions(self) -> list:
        """Get Y positions of track number buttons.

        Identifies track numbers by finding digit-only buttons that have
        a 'No Input' dropdown within ~60px vertically below them (same track row).
        """
        return await self.browser.evaluate("""() => {
            const allBtns = [...document.querySelectorAll('button')];
            // 'No Input' dropdowns mark real track rows
            const noInputYs = allBtns
                .filter(b => b.textContent.trim().startsWith('No Input'))
                .map(b => b.getBoundingClientRect().y);
            const positions = [];
            allBtns.forEach(btn => {
                const text = btn.textContent.trim();
                const r = btn.getBoundingClientRect();
                if (/^\\d+$/.test(text) && r.width < 40 && r.height < 40 && r.y > 50) {
                    // A track number button should have a 'No Input' dropdown
                    // 30-80px below it in the same track row
                    const hasNoInput = noInputYs.some(niy => niy > r.y && niy - r.y < 80);
                    if (hasNoInput) {
                        positions.push({ num: parseInt(text), y: Math.round(r.y) });
                    }
                }
            });
            positions.sort((a, b) => a.num - b.num);
            return positions;
        }""") or []

    async def select_clip(self, track_index: int = 0) -> SkillResult:
        """Click a clip on the timeline to select it.

        Args:
            track_index: 0-based track index (0=first track, 1=second, etc.)

        Track layout (calibrated Mar 2026):
        - Track controls area: x=108-310, track 1 starts at y≈140
        - Timeline/waveform area: x=316+, each track is ~90px tall
        - First track waveform center: y≈200, second: y≈290, third: y≈380
        """
        # Dynamically find the Y position of each track's number button,
        # then click on the clip label area at that Y coordinate.
        track_positions = await self._get_track_positions()

        target_num = track_index + 1

        # If the track isn't visible, scroll it into view by clicking its
        # track number button (which Playwright can scroll to).
        if track_index >= len(track_positions):
            # Track not visible yet — try scrolling the track list container
            scrolled = await self.browser.evaluate(f"""(() => {{
                const btns = [...document.querySelectorAll('button')];
                const target = btns.find(b => {{
                    const t = b.textContent.trim();
                    const r = b.getBoundingClientRect();
                    return t === '{target_num}' && r.width < 40 && r.height < 40;
                }});
                if (target) {{
                    target.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                    return true;
                }}
                // Fallback: scroll the timeline container down
                const containers = document.querySelectorAll('div');
                for (const c of containers) {{
                    const r = c.getBoundingClientRect();
                    if (r.x > 100 && r.x < 600 && c.scrollHeight > c.clientHeight + 50) {{
                        c.scrollTop += 300;
                        return true;
                    }}
                }}
                return false;
            }})()""")
            await self.wait(1)

            # Re-detect track positions after scroll
            track_positions = await self._get_track_positions()

        # Find the target track in the (possibly updated) positions
        target_pos = None
        for tp in track_positions:
            if tp['num'] == target_num:
                target_pos = tp
                break

        if not target_pos:
            return SkillResult(success=False,
                               message=f"Track {target_num} not found ({len(track_positions)} tracks visible)")

        # Click on the clip label at the track's Y position
        y = target_pos['y'] + 5

        for x in [500, 600, 700]:
            await self.page.mouse.click(x, y)
            await self.wait(0.8)

            text = await self.get_right_panel_text()
            if any(kw in text for kw in ['Clip Settings', 'Clip Volume', 'Transpose',
                                          'Tempo', 'Extract', 'Stems', 'Remix']):
                return SkillResult(success=True, message=f"Selected clip on track {target_num}")

        return SkillResult(success=False, message=f"Could not select clip on track {target_num}")

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

    async def open_project(self, search_query: str) -> SkillResult:
        """Open a Studio project by searching the library.

        Clicks Open Library, searches for the query, right-clicks the first
        matching result with 'Stems' badge, and selects 'Open in Studio'.
        Falls back to first result if no Stems match found.

        Args:
            search_query: Song name to search for (e.g. "Golden Hour")
        """
        # Dismiss any welcome modals first
        try:
            close = self.page.locator('[aria-label="close"], [aria-label="Close"]').first
            await close.click(timeout=3000)
            await self.wait(1)
        except Exception:
            pass

        # Click Open Library button at the bottom (or the library icon in the sidebar)
        if not await self.click_button("Open Library"):
            # Try clicking the waveform icon (library) in the left sidebar
            try:
                await self.page.locator('a[href="/me"], text=Library').first.click(timeout=3000)
                await self.wait(2)
            except Exception:
                # Last resort: use the sidebar waveform icon or bottom bar
                try:
                    await self.page.locator('text=Open Library').first.click(timeout=3000)
                except Exception:
                    return SkillResult(success=False, message="Open Library button not found")
        await self.wait(2)

        # Click the search icon and type the query
        search_input = await self.page.query_selector('input[placeholder*="Search"], input[type="text"]')
        if not search_input:
            # Try clicking the magnifying glass icon area
            await self.click_at(487, 86)
            await self.wait(0.5)
            search_input = await self.page.query_selector('input[placeholder*="Search"], input[type="text"]')

        if not search_input:
            return SkillResult(success=False, message="Search input not found")

        await search_input.fill(search_query)
        await self.wait(2)

        # Right-click the first matching result (prefer one with Stems badge)
        safe_query = search_query.replace("'", "\\'")
        result = await self.browser.evaluate(f"""(() => {{
            const query = '{safe_query}';
            const items = document.querySelectorAll('*');
            let stemTarget = null;
            let anyTarget = null;
            for (const el of items) {{
                const text = el.textContent || '';
                if (text.includes(query) && text.length < 300) {{
                    const rect = el.getBoundingClientRect();
                    if (rect.y > 130 && rect.y < 800 && rect.height > 30 && rect.height < 120) {{
                        const pos = {{ x: rect.x + rect.width/2, y: rect.y + rect.height/2 }};
                        if (!anyTarget) anyTarget = pos;
                        if (text.includes('Stems') && !stemTarget) stemTarget = pos;
                    }}
                }}
            }}
            const target = stemTarget || anyTarget;
            if (!target) return null;
            document.elementFromPoint(target.x, target.y)?.dispatchEvent(
                new MouseEvent('contextmenu', {{ bubbles: true, cancelable: true,
                    clientX: target.x, clientY: target.y, button: 2, view: window }})
            );
            return target;
        }})()""")

        if not result:
            return SkillResult(success=False, message=f"No results for '{search_query}'")

        await self.wait(1)

        # Hover over Remix/Edit to reveal submenu using Playwright hover
        try:
            remix_edit = self.page.locator("text=Remix/Edit").first
            await remix_edit.hover(timeout=5000)
            await self.wait(1)
        except Exception:
            return SkillResult(success=False, message="Remix/Edit menu not found")

        # Click "Open in Studio" from the submenu
        try:
            await self.page.locator("text=Open in Studio").first.click(timeout=5000)
        except Exception:
            return SkillResult(success=False, message="'Open in Studio' option not found")

        # Wait for project to load (Studio loading animation takes a while)
        await self.wait(8)

        # Dismiss any welcome modals that appear
        try:
            close_btn = self.page.locator('[aria-label="close"], [aria-label="Close"]').first
            await close_btn.click(timeout=3000)
            await self.wait(1)
        except Exception:
            pass

        title = await self.page.title()
        return SkillResult(success=True, message=f"Opened project: {title}", data=title)

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
        positions = await self._get_track_positions()
        count = max((p['num'] for p in positions), default=0)

        return SkillResult(success=True, message=f"{count} tracks", data=count)
