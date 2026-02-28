"""Base skill class for Suno Studio automation."""
import asyncio
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional
from rich.console import Console

console = Console()

# Load control map
_CONTROLS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "config", "suno_controls.json"
)
with open(_CONTROLS_PATH) as f:
    CONTROLS = json.load(f)


@dataclass
class SkillResult:
    """Result of a skill execution."""
    success: bool
    message: str = ""
    data: Any = None


class Skill:
    """Base class for all Suno Studio skills.

    A skill is an atomic, repeatable browser action.
    Skills use the control map (suno_controls.json) for element positions.
    """

    def __init__(self, browser):
        self.browser = browser
        self.controls = CONTROLS

    @property
    def page(self):
        return self.browser.page

    async def screenshot(self, name: str, output_dir: str = "/tmp/suno_skills") -> str:
        os.makedirs(output_dir, exist_ok=True)
        path = os.path.join(output_dir, f"{name}.png")
        await self.browser.screenshot(path)
        return path

    async def click_at(self, x: int, y: int, delay: float = 0.5):
        """Click at exact coordinates."""
        await self.page.mouse.click(x, y)
        await asyncio.sleep(delay)

    async def click_button(self, text: str, region: Optional[dict] = None, timeout: int = 3000) -> bool:
        """Click a button by its text content, optionally constrained to a region."""
        x_min = region.get("x_min", 0) if region else 0
        x_max = region.get("x_max", 9999) if region else 9999
        y_min = region.get("y_min", 0) if region else 0
        y_max = region.get("y_max", 9999) if region else 9999

        result = await self.browser.evaluate(f"""() => {{
            const buttons = document.querySelectorAll('button');
            for (const btn of buttons) {{
                const t = btn.textContent.trim();
                const r = btn.getBoundingClientRect();
                if (t === '{text}' && r.x >= {x_min} && r.x <= {x_max} &&
                    r.y >= {y_min} && r.y <= {y_max} && r.width > 0 && btn.offsetParent !== null) {{
                    return {{x: Math.round(r.x + r.width/2), y: Math.round(r.y + r.height/2)}};
                }}
            }}
            return null;
        }}""")

        if result:
            await self.click_at(result['x'], result['y'])
            return True
        return False

    async def drag(self, from_x: int, from_y: int, to_x: int, to_y: int, steps: int = 15):
        """Drag from one point to another."""
        await self.page.mouse.move(from_x, from_y)
        await self.page.mouse.down()
        for i in range(steps):
            x = from_x + (to_x - from_x) * (i + 1) / steps
            y = from_y + (to_y - from_y) * (i + 1) / steps
            await self.page.mouse.move(x, y)
            await asyncio.sleep(0.02)
        await self.page.mouse.up()
        await asyncio.sleep(0.3)

    async def get_right_panel_text(self) -> str:
        """Get all visible text from the right panel."""
        return await self.browser.evaluate("""() => {
            const vw = window.innerWidth;
            const texts = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
            while (walker.nextNode()) {
                const r = walker.currentNode.parentElement?.getBoundingClientRect();
                if (r && r.left > vw * 0.7 && r.width > 0) {
                    const t = walker.currentNode.textContent.trim();
                    if (t) texts.push(t);
                }
            }
            return texts.join(' | ');
        }""") or ""

    async def set_input_value(self, x: int, y: int, value: str):
        """Click an input field and set its value."""
        await self.page.mouse.click(x, y)
        await asyncio.sleep(0.3)
        # Triple-click to select all, then type new value
        await self.page.mouse.click(x, y, click_count=3)
        await asyncio.sleep(0.1)
        await self.page.keyboard.type(value)
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(0.3)

    async def wait(self, seconds: float = 1):
        await asyncio.sleep(seconds)
