"""Navigation skills for Suno pages."""
import asyncio
from .base import Skill, SkillResult, console


class NavigateSkill(Skill):
    """Navigate between Suno pages."""

    async def to_studio(self) -> SkillResult:
        """Navigate to Suno Studio."""
        await self.browser.navigate("https://suno.com/studio")
        await asyncio.sleep(6)
        return SkillResult(success=True, message="Navigated to Studio")

    async def to_create(self) -> SkillResult:
        """Navigate to the Create page."""
        await self.browser.navigate("https://suno.com/create")
        await asyncio.sleep(5)
        return SkillResult(success=True, message="Navigated to Create")

    async def to_library(self) -> SkillResult:
        """Navigate to the Library page."""
        await self.browser.navigate("https://suno.com/me")
        await asyncio.sleep(5)
        return SkillResult(success=True, message="Navigated to Library")

    async def to_song(self, song_uuid: str) -> SkillResult:
        """Navigate to a specific song page."""
        await self.browser.navigate(f"https://suno.com/song/{song_uuid}")
        await asyncio.sleep(5)
        return SkillResult(success=True, message=f"Navigated to song {song_uuid}")

    async def is_logged_in(self) -> SkillResult:
        """Check if user is logged into Suno."""
        if not self.page:
            return SkillResult(success=False, message="No page")

        await asyncio.sleep(2)
        url = self.page.url

        if any(x in url for x in ["accounts.google.com", "login", "signin", "clerk_handshake"]):
            return SkillResult(success=False, message="Auth redirect detected")

        if "suno.com" not in url:
            return SkillResult(success=False, message="Not on suno.com")

        sign_in_visible = await self.browser.evaluate("""() => {
            const buttons = [...document.querySelectorAll('button')];
            return buttons.some(b => b.textContent?.trim() === 'Sign In');
        }""")

        if sign_in_visible:
            return SkillResult(success=False, message="Sign In button visible")

        return SkillResult(success=True, message="Logged in")
