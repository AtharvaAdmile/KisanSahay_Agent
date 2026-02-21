"""
Navigator — self-navigation and recovery logic for agents.

When a task step fails (wrong page, element not found, navigation error),
Navigator.recover() is called. It:
  1. Reads the current page URL
  2. Identifies which known page the agent is on
  3. Determines the correct target page for the active intent
  4. Navigates there and logs a human-readable explanation
  5. Returns True if recovery is possible, False if a user handoff is needed.
"""

import asyncio

from ..config.base import SiteConfig
from ..browser.sitemap import Sitemap
from ..browser.controller import Browser
from ..utils import logger


class Navigator:
    """Handles routing, page-awareness, and error recovery."""

    def __init__(self, browser: Browser, config: SiteConfig, verbose: bool = False):
        self.browser = browser
        self.config = config
        self.verbose = verbose
        self._sitemap = Sitemap(config)
        self._current_intent: str = "get_info"

    def set_intent(self, intent: str) -> None:
        """Tell the navigator which intent is currently executing."""
        self._current_intent = intent

    async def current_page_key(self) -> str:
        """Identify which known page the agent is on from the URL."""
        url = self.browser.page.url
        key = self._sitemap.match_current_page(url)
        logger.debug(f"Navigator: current page = '{key}' ({url[:60]})", self.verbose)
        return key

    async def is_on_correct_page(self) -> bool:
        """Return True if we are already on the target page for the current intent."""
        target_key = self.config.intent_routes.get(self._current_intent, "home")
        current_key = await self.current_page_key()
        return current_key == target_key

    async def navigate_to_intent_page(self) -> bool:
        """Navigate directly to the target page for the current intent."""
        target_url = self._sitemap.find_route(self._current_intent)
        target_key = self.config.intent_routes.get(self._current_intent, "home")
        logger.info(f"Navigator: going to '{target_key}' for intent '{self._current_intent}'")
        await self.browser.navigate(target_url)
        await self.browser.dismiss_homepage_modal()
        return True

    async def recover(self, reason: str = "") -> bool:
        """
        Called when a task step fails. Reasons about the situation and
        navigates to the correct page.

        Returns:
            True  — recovery successful, caller should retry the step.
            False — recovery not possible, caller should hand off to user.
        """
        current_url = self.browser.page.url
        current_key = self._sitemap.match_current_page(current_url)
        target_key = self.config.intent_routes.get(self._current_intent, "home")
        target_url = self._sitemap.find_route(self._current_intent)

        logger.warning(
            f"⟳ Auto-recovery triggered\n"
            f"  Reason    : {reason[:120] if reason else '(unknown)'}\n"
            f"  Currently : '{current_key}' ({current_url[:70]})\n"
            f"  Need      : '{target_key}' ({target_url[:70]})\n"
            f"  Intent    : {self._current_intent}"
        )

        if current_key == target_key:
            logger.info("  → Already on correct page — scrolling to top and retrying")
            try:
                await self.browser.page.evaluate("window.scrollTo(0, 0)")
            except Exception:
                pass
            await asyncio.sleep(2)
            return True

        if current_key == "home":
            logger.info("  → On homepage — dismissing modal and re-navigating")
            await self.browser.dismiss_homepage_modal()
            await asyncio.sleep(1)
            await self.browser.navigate(target_url)
            await self.browser.dismiss_homepage_modal()
            return True

        if target_url:
            logger.info(f"  → Navigating directly to target: {target_url[:70]}")
            try:
                await self.browser.navigate(target_url)
                await self.browser.dismiss_homepage_modal()
                return True
            except Exception as e:
                logger.warning(f"  → Direct navigation failed: {e}")

        logger.info("  → Falling back: home → target")
        try:
            await self.browser.navigate(self.config.get_url("home"))
            await self.browser.dismiss_homepage_modal()
            await asyncio.sleep(2)
            await self.browser.navigate(target_url)
            return True
        except Exception as e:
            logger.error(f"  → Recovery failed entirely: {e}")
            return False

    async def go_home(self) -> None:
        """Navigate to homepage and dismiss modal."""
        await self.browser.navigate(self.config.get_url("home"))
        await self.browser.dismiss_homepage_modal()

    def describe_available_pages(self) -> str:
        """Return a formatted sitemap string for logging or LLM context."""
        return self._sitemap.describe_site()
