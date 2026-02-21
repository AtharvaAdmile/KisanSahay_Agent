"""
YES-TECH (Yield Estimation System based on Technology) task handler.
Based on live exploration of https://pmfby.gov.in/yestech/ — 2026-02-20.

KEY FINDINGS:
- Portal URL: https://pmfby.gov.in/yestech/
- Shows a splash/loading screen for public users — no public data
- Login URL: https://pmfby.gov.in/yestech/signin
- Auth: Departmental credentials (username/password) — NOT mobile OTP
- Target users: State/district agriculture officers, NOT farmers
- Limitation: Agent cannot authenticate without departmental credentials
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio

from shared.browser.controller import Browser
from shared.utils import logger

YESTECH_URL   = "https://pmfby.gov.in/yestech/"
YESTECH_LOGIN = "https://pmfby.gov.in/yestech/signin"


class YESTECHAccessTask:
    """
    Handles YES-TECH navigation and information display.
    Note: Full functionality requires authorized departmental credentials.
    The agent navigates to the portal, captures its state, and informs
    the user about its purpose and access requirements.
    """

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def navigate(self, **pre_params) -> dict:
        """
        Navigate to the YES-TECH portal and capture its current state.
        Explains the portal's purpose and access requirements.
        """
        logger.section("YES-TECH — Yield Estimation Portal")
        logger.info(
            "YES-TECH is primarily for authorized state/district government\n"
            "officials and insurance company staff — not farmers directly.\n"
        )

        page = self.browser.page

        # Navigate to the main portal
        await self.browser.navigate(YESTECH_URL)
        await asyncio.sleep(5)

        current_url = page.url
        title = await page.title()

        # Try to read any public visible content
        body_text = await self.browser.get_text("body")
        headings   = await self.browser.get_all_text("h1, h2, h3")
        headings   = [h.strip() for h in headings if h.strip()]

        await self.browser.screenshot("yestech_portal")

        logger.info(f"Current URL: {current_url}")
        logger.info(f"Page Title: {title}")

        if headings:
            logger.info("Page headings found:")
            for h in headings[:10]:
                logger.info(f"  • {h}")

        logger.section("YES-TECH Access Information")
        logger.info(
            "What YES-TECH does:\n"
            "  • Technology-based yield estimation for crop insurance assessment\n"
            "  • Monitors crop health via satellite/IoT sensor data\n"
            "  • Used to settle insurance claims fairly\n\n"
            "Access requirements:\n"
            "  • Authorized departmental login (State/District Agriculture Officers)\n"
            "  • Insurance company representatives\n"
            "  • NOT accessible to farmers directly\n\n"
            "Login URL: https://pmfby.gov.in/yestech/signin\n"
            "If you have departmental credentials, run the agent in --no-headless mode\n"
            "and manually log in, then explore the dashboard."
        )

        # If already on sign-in page or can navigate there
        if "signin" not in current_url:
            try:
                signin_link = page.locator(
                    "a:has-text('Login'), a:has-text('Sign In'), a[href*='signin']"
                )
                if await signin_link.count() > 0:
                    logger.info("Sign-in link found — navigating to it")
                    await signin_link.first.click()
                    await asyncio.sleep(3)
                    await self.browser.screenshot("yestech_signin_page")
            except Exception:
                await self.browser.navigate(YESTECH_LOGIN)
                await asyncio.sleep(3)
                await self.browser.screenshot("yestech_signin_page")

        return {
            "task": "yestech_access",
            "action": "navigate",
            "portal_url": YESTECH_URL,
            "login_url": YESTECH_LOGIN,
            "status": "completed",
            "note": (
                "YES-TECH requires authorized departmental credentials. "
                "This portal is not accessible to farmers directly. "
                "See screenshot at yestech_portal.png."
            ),
            "headings": headings[:10],
        }
