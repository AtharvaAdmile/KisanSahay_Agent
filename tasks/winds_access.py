"""
WINDS (Weather Information Network & Data System) task handler.
Based on live exploration of https://pmfby.gov.in/winds/ — 2026-02-20.

KEY FINDINGS:
- Portal URL: https://pmfby.gov.in/winds/
- Public map available WITHOUT login: Temperature, Rainfall, Wind Speed, RH%
- Login: Mobile No + Password + CAPTCHA (no OTP)
- Login selector: .login__loginButton___29wrS
- Nav: Home, Weather Information, Documents, Gallery, External Links, About Us
"""

import asyncio

from browser.controller import PMFBYBrowser
from utils import logger
from utils.helpers import prompt_user, prompt_confirm

WINDS_URL = "https://pmfby.gov.in/winds/"

# Weather parameters available on the public map
WEATHER_PARAMS = ["Temperature", "Rainfall", "Wind Speed", "Humidity"]


class WINDSAccessTask:
    """Handles WINDS weather data viewing and login."""

    def __init__(self, browser: PMFBYBrowser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    # ── Public Weather Data ───────────────────────────────────────────────────

    async def view_public_data(self, **pre_params) -> dict:
        """
        Navigate to the WINDS portal and capture the public weather map.
        No login required. Extracts visible weather readings from the page.
        """
        logger.section("WINDS — Public Weather Map")
        logger.info("Navigating to WINDS portal (no login required for public data).\n")

        page = self.browser.page
        await self.browser.navigate(WINDS_URL)
        await asyncio.sleep(5)  # Map takes time to render

        # Wait for the map/data panel to appear
        try:
            await page.wait_for_selector(
                ".leaflet-container, [class*='map'], [class*='weather']",
                timeout=15000
            )
            logger.success("Weather map loaded")
        except Exception:
            logger.warning("Map container not found — taking screenshot anyway")

        # Extract any visible weather data text (current observation panel)
        data_text = ""
        for sel in [
            "[class*='CurrentObservation']",
            "[class*='weatherPanel']",
            ".observation-panel",
            "[class*='sidebar']",
            "aside",
        ]:
            try:
                txt = await page.inner_text(sel)
                if txt and len(txt.strip()) > 20:
                    data_text = txt.strip()
                    break
            except Exception:
                continue

        # Also grab any stat boxes
        stat_values = await self.browser.get_all_text(
            "[class*='statValue'], [class*='reading'], [class*='temp'], [class*='rain']"
        )

        await self.browser.screenshot("winds_weather_map")

        if data_text:
            logger.section("Current Weather Observations")
            for line in data_text.split("\n")[:20]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.info("Map loaded. See screenshot for current weather data.")
            logger.info("Tip: The WINDS map shows Temperature, Rainfall, Wind Speed, and Humidity.")

        return {
            "task": "winds_access",
            "action": "view_public_data",
            "status": "completed",
            "data_preview": data_text[:600] if data_text else "See winds_weather_map.png",
            "stat_values": stat_values[:10],
        }

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self, **pre_params) -> dict:
        """
        Log in to WINDS using Mobile No + Password + CAPTCHA.
        Login button: .login__loginButton___29wrS
        """
        logger.section("WINDS — Login")
        page = self.browser.page

        await self.browser.navigate(WINDS_URL)
        await asyncio.sleep(5)

        # Click login button
        try:
            login_btn = page.locator(
                ".login__loginButton___29wrS, button:has-text('Login'), a:has-text('Login')"
            )
            await login_btn.first.wait_for(state="visible", timeout=8000)
            await login_btn.first.click()
            await asyncio.sleep(3)
            logger.success("WINDS login form opened")
        except Exception as e:
            logger.error(f"Could not open WINDS login: {e}")
            await self.browser.handoff_to_user(
                "Please click the Login button on the WINDS portal, then type 'continue'."
            )

        # Mobile
        mobile = (
            pre_params.get("winds_mobile")
            or pre_params.get("mobile")
            or prompt_user("WINDS Registered Mobile Number")
        )
        if mobile:
            await self.browser.vision_fill(
                "input[name='mobile'], input[placeholder*='Mobile']",
                mobile,
                "Mobile Number input in WINDS login"
            )

        # Password
        password = pre_params.get("winds_password") or prompt_user("WINDS Password")
        if password:
            await self.browser.vision_fill(
                "input[name='password'], input[type='password']",
                password,
                "Password input in WINDS login"
            )

        # CAPTCHA handoff
        if await self.browser.detect_captcha():
            await self.browser.handle_captcha()
        else:
            await self.browser.handoff_to_user(
                "If a CAPTCHA is shown, please solve it and click Login, then type 'continue'."
            )

        await asyncio.sleep(5)
        await self.browser.screenshot("winds_login_result")

        body = await self.browser.get_text("body")
        return {
            "task": "winds_access",
            "action": "login",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": body[:400] if body else "See winds_login_result.png",
        }
