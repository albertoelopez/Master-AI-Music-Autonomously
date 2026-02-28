"""Browser automation module for connecting to Chrome."""
import asyncio
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page
from rich.console import Console

console = Console()


class BrowserController:
    """Controls Chrome browser via CDP (Chrome DevTools Protocol)."""

    def __init__(self, debug_port: int = 9222):
        self.debug_port = debug_port
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None

    async def connect(self) -> bool:
        """Connect to an existing Chrome instance with remote debugging enabled."""
        try:
            self.playwright = await async_playwright().start()

            # Connect to existing Chrome with remote debugging
            self.browser = await self.playwright.chromium.connect_over_cdp(
                f"http://localhost:{self.debug_port}"
            )

            # Get existing contexts
            contexts = self.browser.contexts
            if contexts:
                self.context = contexts[0]
                pages = self.context.pages
                if pages:
                    self.page = pages[0]
                else:
                    self.page = await self.context.new_page()
            else:
                self.context = await self.browser.new_context()
                self.page = await self.context.new_page()

            console.print("[green]✓[/green] Connected to Chrome browser")
            return True

        except Exception as e:
            console.print(f"[red]✗[/red] Failed to connect to Chrome: {e}")
            console.print(
                "[yellow]Tip:[/yellow] Start Chrome with: "
                f"google-chrome --remote-debugging-port={self.debug_port}"
            )
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
        """Close the browser connection."""
        if self.playwright:
            await self.playwright.stop()
            console.print("[green]✓[/green] Browser connection closed")
