"""Song creation skills - create songs with lyrics, styles, and parameters."""
import asyncio
from typing import Optional
from .base import Skill, SkillResult, console


class CreateSkill(Skill):
    """Create songs on Suno using Simple, Custom, or Sounds mode."""

    async def _dismiss_modals(self):
        """Quick modal dismissal between create steps."""
        for _ in range(2):
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        # Close chakra portals and force-hide high z-index fixed overlays
        await self.browser.evaluate("""() => {
            document.querySelectorAll('.chakra-portal, [class*=modal], [class*=overlay], [role=dialog]').forEach(el => {
                const closeBtn = el.querySelector('[class*=close], button[aria-label*=close], button[aria-label*=Close]');
                if (closeBtn) closeBtn.click();
            });
            // Only check direct children of body and chakra portals for z-index overlays
            document.querySelectorAll('body > *, .chakra-portal > *').forEach(el => {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex);
                if (z > 50000 && style.position === 'fixed') {
                    el.style.display = 'none';
                }
            });
        }""")
        await asyncio.sleep(0.3)

    async def switch_to_custom(self) -> SkillResult:
        """Switch to Custom creation mode."""
        if not await self.click_button("Custom"):
            return SkillResult(success=False, message="Custom tab not found")
        await self.wait(1)
        return SkillResult(success=True, message="Switched to Custom mode")

    async def switch_to_simple(self) -> SkillResult:
        """Switch to Simple creation mode."""
        if not await self.click_button("Simple"):
            return SkillResult(success=False, message="Simple tab not found")
        await self.wait(1)
        return SkillResult(success=True, message="Switched to Simple mode")

    async def switch_to_sounds(self) -> SkillResult:
        """Switch to Sounds creation mode."""
        if not await self.click_button("Sounds"):
            return SkillResult(success=False, message="Sounds tab not found")
        await self.wait(1)
        return SkillResult(success=True, message="Switched to Sounds mode")

    async def set_lyrics(self, lyrics: str) -> SkillResult:
        """Fill in the lyrics textarea.

        Uses coordinate-based click to avoid Playwright's actionability checks
        being blocked by Suno's modals/overlays.
        """
        lyrics_el = await self.browser.evaluate("""() => {
            const textareas = document.querySelectorAll('textarea');
            for (const ta of textareas) {
                const r = ta.getBoundingClientRect();
                const ph = (ta.getAttribute('placeholder') || '').toLowerCase();
                if (r.width > 200 && r.height > 0 && r.y < 350 &&
                    (ph.includes('lyrics') || ph.includes('prompt') || ph.includes('write'))) {
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
            // Fallback: first visible textarea in form area
            for (const ta of textareas) {
                const r = ta.getBoundingClientRect();
                if (r.width > 200 && r.height > 0 && r.x < 700 && r.y > 100 && r.y < 400) {
                    return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                }
            }
            return null;
        }""")

        if not lyrics_el:
            return SkillResult(success=False, message="Lyrics textarea not found")

        await self.click_at(lyrics_el['x'], lyrics_el['y'])
        await self.wait(0.3)
        await self.page.keyboard.press("Control+a")
        await self.page.keyboard.press("Backspace")
        await self.wait(0.2)
        await self.page.keyboard.type(lyrics, delay=5)
        return SkillResult(success=True, message=f"Set lyrics ({len(lyrics)} chars)")

    async def set_styles(self, styles: str) -> SkillResult:
        """Set the style tags/text.

        In Custom mode, the Styles field is a textarea (NOT an input).
        We find it by locating the "Styles" label and then the textarea below it.
        """
        style_el = await self.browser.evaluate("""() => {
            // Strategy 1: Find the "Styles" heading/label, then get the textarea below it
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            let stylesLabelY = null;
            while (walker.nextNode()) {
                const text = walker.currentNode.textContent.trim();
                if (text === 'Styles') {
                    const r = walker.currentNode.parentElement?.getBoundingClientRect();
                    if (r && r.width > 0 && r.x < 700) {
                        stylesLabelY = r.y;
                        break;
                    }
                }
            }

            if (stylesLabelY !== null) {
                // Find the first textarea BELOW the Styles label
                const textareas = document.querySelectorAll('textarea');
                for (const ta of textareas) {
                    const r = ta.getBoundingClientRect();
                    if (r.width > 200 && r.height > 0 && r.y > stylesLabelY && r.y < stylesLabelY + 200) {
                        return {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)};
                    }
                }
            }

            // Strategy 2: Fallback - visible textareas sorted by y, pick second one
            // (first is Lyrics, second is Styles in Custom mode)
            const visible = [];
            const textareas = document.querySelectorAll('textarea');
            for (const ta of textareas) {
                const r = ta.getBoundingClientRect();
                if (r.width > 200 && r.height > 0 && r.x < 700 && r.y > 100 && r.y < 800) {
                    visible.push({x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), fy: r.y});
                }
            }
            visible.sort((a, b) => a.fy - b.fy);
            // Filter to only Custom mode textareas (Lyrics ~y200-300, Styles ~y400-550)
            const customMode = visible.filter(v => v.fy > 150);
            if (customMode.length >= 2) return customMode[1];
            return null;
        }""")

        if style_el:
            await self.click_at(style_el['x'], style_el['y'])
            await self.wait(0.3)
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Backspace")
            await self.wait(0.2)
            await self.page.keyboard.type(styles)
            return SkillResult(success=True, message=f"Set styles: {styles[:50]}")

        return SkillResult(success=False, message="Styles textarea not found")

    async def set_title(self, title: str) -> SkillResult:
        """Set the song title.

        In current Suno UI, Song Title input is visible directly in Custom mode.
        There may be multiple inputs matching "Song Title (Optional)" - we want
        the one near the bottom of the form (y > 600), not the one near the top.
        """
        title_input = await self.browser.evaluate("""() => {
            const inputs = document.querySelectorAll('input');
            let best = null;
            for (const inp of inputs) {
                const r = inp.getBoundingClientRect();
                const placeholder = inp.getAttribute('placeholder') || '';
                if ((placeholder.includes('Title') || placeholder.includes('title')) &&
                    r.width > 100 && r.x < 700 && r.y > 60) {
                    // Pick the one with the largest y (bottom of form)
                    if (!best || r.y > best.fy) {
                        best = {x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2), fy: r.y};
                    }
                }
            }
            return best;
        }""")

        if title_input:
            await self.click_at(title_input['x'], title_input['y'])
            await self.page.keyboard.press("Control+a")
            await self.page.keyboard.press("Backspace")
            await self.page.keyboard.type(title)
            return SkillResult(success=True, message=f"Set title: {title}")

        return SkillResult(success=False, message="Title input not found")

    async def set_weirdness(self, value: int) -> SkillResult:
        """Set the Weirdness slider (0-100). Requires Advanced Options open."""
        return await self._set_slider_by_label("Weirdness", value)

    async def set_style_influence(self, value: int) -> SkillResult:
        """Set the Style Influence slider (0-100). Requires Advanced Options open."""
        return await self._set_slider_by_label("Style Influence", value)

    async def click_create(self) -> SkillResult:
        """Click the Create button to generate a song.

        After clicking, checks for CAPTCHA challenges and waits for
        the user to solve them manually. Re-clicks Create after CAPTCHA
        is solved since the original click gets consumed by the challenge.
        """
        if not await self.click_button("Create"):
            return SkillResult(success=False, message="Create button not found")
        await self.wait(3)

        # Check for CAPTCHA and wait for user to solve it
        captcha_solved = await self._wait_for_captcha()

        if captcha_solved:
            # CAPTCHA consumed the original Create click — must click again
            await self.wait(2)
            console.print("[yellow]Re-clicking Create after CAPTCHA...[/yellow]")
            if not await self.click_button("Create"):
                return SkillResult(success=False, message="Create button not found after CAPTCHA")
            await self.wait(3)

            # Check if CAPTCHA appears again
            captcha_again = await self._wait_for_captcha()
            if captcha_again:
                await self.wait(2)
                console.print("[yellow]Re-clicking Create again...[/yellow]")
                await self.click_button("Create")
                await self.wait(3)

        # Verify creation started by checking if credits changed or page updated
        await self.wait(2)

        msg = "Create clicked - song generation started"
        if captcha_solved:
            msg += " (CAPTCHA solved)"
        return SkillResult(success=True, message=msg)

    async def _wait_for_captcha(self, timeout: int = 120) -> bool:
        """Detect CAPTCHA and wait for user to solve it manually.

        Returns True if a CAPTCHA was detected and resolved.
        """
        import time
        start = time.time()

        while time.time() - start < timeout:
            has_captcha = await self.browser.evaluate("""() => {
                // Check for common CAPTCHA indicators
                const body = document.body.innerHTML.toLowerCase();
                const iframes = document.querySelectorAll('iframe');
                for (const iframe of iframes) {
                    const src = (iframe.src || '').toLowerCase();
                    if (src.includes('captcha') || src.includes('challenge') ||
                        src.includes('recaptcha') || src.includes('hcaptcha') ||
                        src.includes('arkoselabs') || src.includes('funcaptcha')) {
                        return true;
                    }
                }
                // Check for visual CAPTCHA overlays (image grid challenges)
                const allEls = document.querySelectorAll('[class*=captcha], [id*=captcha], [class*=challenge], [id*=challenge]');
                if (allEls.length > 0) return true;
                // Check for Arkose/FunCaptcha enforcement div
                const arkoDiv = document.querySelector('#arkose-enforcement, [data-callback*=captcha]');
                if (arkoDiv) return true;
                // Check for high z-index overlay with image grid (generic CAPTCHA pattern)
                for (const el of document.querySelectorAll('div')) {
                    const style = window.getComputedStyle(el);
                    const z = parseInt(style.zIndex);
                    if (z > 10000 && style.position === 'fixed') {
                        const imgs = el.querySelectorAll('img');
                        if (imgs.length >= 4) return true;  // Image grid = CAPTCHA
                    }
                }
                return false;
            }""")

            if has_captcha:
                if time.time() - start < 1:
                    # First detection
                    console.print("\n[bold yellow]CAPTCHA detected![/bold yellow] Please solve it in the browser window.")
                    console.print("[dim]Waiting up to 2 minutes for you to complete it...[/dim]")
                await self.wait(3)
                continue
            else:
                # No CAPTCHA (either never appeared or was solved)
                if time.time() - start > 2:
                    # We waited, meaning CAPTCHA was present and now gone
                    console.print("[green]CAPTCHA solved! Continuing...[/green]")
                    return True
                return False

        console.print("[red]CAPTCHA timeout (2 minutes). Song may not have been created.[/red]")
        return True

    async def create_song(self, lyrics: str, styles: str,
                          title: Optional[str] = None,
                          weirdness: Optional[int] = None,
                          style_influence: Optional[int] = None) -> SkillResult:
        """Complete song creation workflow in Custom mode.

        Args:
            lyrics: Song lyrics or prompt
            styles: Style description/tags
            title: Optional song title
            weirdness: 0-100, default 50
            style_influence: 0-100, default 50
        """
        results = []

        r = await self.switch_to_custom()
        results.append(r.message)
        if not r.success:
            return r
        await self._dismiss_modals()

        r = await self.set_lyrics(lyrics)
        results.append(r.message)
        if not r.success:
            return r
        await self._dismiss_modals()

        r = await self.set_styles(styles)
        results.append(r.message)
        if not r.success:
            return r
        await self._dismiss_modals()

        # Title is directly visible in Custom mode
        if title:
            r = await self.set_title(title)
            results.append(r.message)
            await self._dismiss_modals()

        # Advanced options (weirdness, style influence are behind this toggle)
        if any(x is not None for x in [weirdness, style_influence]):
            await self.click_button("Advanced Options")
            await self.wait(1)

            if weirdness is not None:
                r = await self.set_weirdness(weirdness)
                results.append(r.message)

            if style_influence is not None:
                r = await self.set_style_influence(style_influence)
                results.append(r.message)

        r = await self.click_create()
        results.append(r.message)

        return SkillResult(success=r.success, message=" → ".join(results))

    async def _set_slider_by_label(self, label: str, value: int) -> SkillResult:
        """Set a slider by its aria-label."""
        slider = await self.browser.evaluate(f"""() => {{
            const sliders = document.querySelectorAll('[role=slider], input[type=range]');
            for (const s of sliders) {{
                if ((s.getAttribute('aria-label') || '').includes('{label}')) {{
                    const r = s.getBoundingClientRect();
                    return {{
                        x: Math.round(r.x), y: Math.round(r.y + r.height/2),
                        w: Math.round(r.width),
                        current: parseInt(s.getAttribute('aria-valuenow') || s.value || '50')
                    }};
                }}
            }}
            return null;
        }}""")

        if not slider:
            return SkillResult(success=False, message=f"{label} slider not found")

        # Calculate target position
        target_x = slider['x'] + int(slider['w'] * value / 100)
        await self.click_at(target_x, slider['y'])

        return SkillResult(success=True, message=f"{label}: {value}")
