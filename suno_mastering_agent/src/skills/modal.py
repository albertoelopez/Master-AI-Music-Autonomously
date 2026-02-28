"""Modal dismissal skills - handles overlays that block interaction."""
import asyncio
from .base import Skill, SkillResult, console


class ModalSkill(Skill):
    """Dismiss modals and overlays blocking the UI."""

    async def dismiss_all(self) -> SkillResult:
        """Aggressively dismiss any modal/overlay/dialog."""
        # Press Escape multiple times
        for _ in range(3):
            await self.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)

        # Click close buttons in modal elements
        await self.browser.evaluate("""() => {
            document.querySelectorAll('[class*=modal], [class*=overlay], [role=dialog], [data-state=open]').forEach(modal => {
                const closeBtn = modal.querySelector('button[aria-label*=close], button[aria-label*=Close], [class*=close]');
                if (closeBtn) closeBtn.click();
            });
            document.querySelectorAll('[class*=backdrop], [class*=Backdrop]').forEach(el => {
                if (el.offsetParent !== null) el.click();
            });
        }""")

        # Force-hide any high z-index fixed elements
        removed = await self.browser.evaluate("""() => {
            let removed = 0;
            document.querySelectorAll('*').forEach(el => {
                const style = window.getComputedStyle(el);
                const z = parseInt(style.zIndex);
                if (z > 50000 && style.position === 'fixed') {
                    el.style.display = 'none';
                    removed++;
                }
            });
            return removed;
        }""") or 0

        await asyncio.sleep(0.5)
        return SkillResult(success=True, message=f"Dismissed modals (hid {removed} overlays)")

    async def check_blocking(self) -> SkillResult:
        """Check if there's anything blocking the center of the page."""
        element = await self.browser.evaluate("""() => {
            const center = document.elementFromPoint(640, 400);
            if (!center) return null;
            return {
                tag: center.tagName,
                className: (typeof center.className === 'string' ? center.className : '').substring(0, 60),
                text: (center.textContent || '').trim().substring(0, 100),
                zIndex: parseInt(window.getComputedStyle(center).zIndex) || 0,
            };
        }""")

        if not element:
            return SkillResult(success=True, message="Nothing blocking")

        is_modal = element.get('zIndex', 0) > 1000 or 'modal' in element.get('className', '').lower()
        return SkillResult(
            success=not is_modal,
            message=f"Center element: {element['tag']} z={element['zIndex']}",
            data=element
        )
