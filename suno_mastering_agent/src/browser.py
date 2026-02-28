"""Browser automation module using Playwright Chromium."""
import asyncio
import os
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from rich.console import Console

console = Console()

# Persistent profile directory so login survives between sessions
DEFAULT_USER_DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "browser_data"
)


class BrowserController:
    """Controls Playwright's Chromium browser with persistent profile."""

    def __init__(self, headless: bool = False, user_data_dir: str = DEFAULT_USER_DATA_DIR,
                 cdp_port: int = 0):
        self.headless = headless
        self.user_data_dir = user_data_dir
        self.cdp_port = cdp_port
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    def get_cdp_url(self) -> str:
        """Get the CDP WebSocket URL for this browser instance."""
        port = self.cdp_port or 9222
        return f"http://localhost:{port}"

    async def connect(self) -> bool:
        """Launch Playwright Chromium with a persistent profile."""
        try:
            self.playwright = await async_playwright().start()

            launch_args = ["--disable-blink-features=AutomationControlled"]
            # WSL2 needs GPU and sandbox workarounds
            import platform
            if "microsoft" in platform.uname().release.lower():
                launch_args += ["--disable-gpu", "--no-sandbox"]
            if self.cdp_port:
                launch_args.append(f"--remote-debugging-port={self.cdp_port}")

            # Persistent context keeps cookies/login between sessions
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir=self.user_data_dir,
                headless=self.headless,
                args=launch_args,
                viewport={"width": 1280, "height": 900},
            )

            # Use existing page or create one
            if self.context.pages:
                self.page = self.context.pages[0]
            else:
                self.page = await self.context.new_page()

            cdp_msg = f" (CDP port {self.cdp_port})" if self.cdp_port else ""
            console.print(f"[green]✓[/green] Launched Chromium browser{cdp_msg}")
            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to launch browser: {e}")
            console.print(
                "[yellow]Tip:[/yellow] Run 'playwright install chromium' "
                "if the browser is not installed"
            )
            return False

    async def connect_cdp(self, cdp_url: str = None) -> bool:
        """Connect to an already-running Chrome via CDP."""
        try:
            url = cdp_url or self.get_cdp_url()
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.connect_over_cdp(url)
            self.context = self.browser.contexts[0] if self.browser.contexts else await self.browser.new_context()
            self.page = self.context.pages[0] if self.context.pages else await self.context.new_page()
            console.print(f"[green]✓[/green] Connected to Chrome via CDP ({url})")
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] CDP connection failed: {e}")
            return False

    async def navigate(self, url: str) -> bool:
        """Navigate to a URL."""
        if not self.page:
            console.print("[red]✗[/red] No page available")
            return False

        try:
            await self.page.goto(url, wait_until="domcontentloaded")
            console.print(f"[green]✓[/green] Navigated to {url}")
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] Navigation failed: {e}")
            return False

    async def click(self, selector: str, timeout: int = 10000) -> bool:
        """Click an element by selector."""
        if not self.page:
            return False

        try:
            await self.page.click(selector, timeout=timeout)
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] Click failed on {selector}: {e}")
            return False

    async def type_text(self, selector: str, text: str) -> bool:
        """Type text into an input field."""
        if not self.page:
            return False

        try:
            await self.page.fill(selector, text)
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] Type failed on {selector}: {e}")
            return False

    async def get_text(self, selector: str) -> Optional[str]:
        """Get text content of an element."""
        if not self.page:
            return None

        try:
            element = await self.page.query_selector(selector)
            if element:
                return await element.text_content()
            return None
        except Exception:
            return None

    async def wait_for_selector(self, selector: str, timeout: int = 30000) -> bool:
        """Wait for a selector to appear."""
        if not self.page:
            return False

        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return True
        except Exception:
            return False

    async def screenshot(self, path: str) -> bool:
        """Take a screenshot of the current page."""
        if not self.page:
            return False

        try:
            await self.page.screenshot(path=path)
            console.print(f"[green]✓[/green] Screenshot saved to {path}")
            return True
        except Exception as e:
            console.print(f"[red]✗[/red] Screenshot failed: {e}")
            return False

    async def get_page_content(self) -> Optional[str]:
        """Get the current page HTML content."""
        if not self.page:
            return None

        try:
            return await self.page.content()
        except Exception:
            return None

    async def evaluate(self, script: str):
        """Execute JavaScript in the page context."""
        if not self.page:
            return None

        try:
            return await self.page.evaluate(script)
        except Exception as e:
            console.print(f"[red]✗[/red] Script evaluation failed: {e}")
            return None

    async def get_all_pages(self) -> list:
        """Get all open pages/tabs."""
        if not self.context:
            return []
        return self.context.pages

    async def switch_to_page(self, index: int) -> bool:
        """Switch to a page by index."""
        pages = await self.get_all_pages()
        if 0 <= index < len(pages):
            self.page = pages[index]
            return True
        return False

    async def close(self):
        """Close the browser."""
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()
        console.print("[green]✓[/green] Browser closed")
