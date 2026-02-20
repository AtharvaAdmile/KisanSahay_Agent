"""
Async Playwright browser controller for PMFBY Agent.
Every action includes a mandatory 2-3 second delay to respect the government server.
Includes handoff_to_user for CAPTCHA/OTP challenges.
"""

import asyncio
import random
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from utils import logger
from utils.helpers import wait_for_continue
from utils.vision import VisionHelper

BASE_URL = "https://pmfby.gov.in"
ACTION_DELAY_MIN = 2.0
ACTION_DELAY_MAX = 3.0
NAVIGATE_DELAY = 3.0
MAX_RETRIES = 3


async def _delay(min_s: float = ACTION_DELAY_MIN, max_s: float = ACTION_DELAY_MAX):
    """Human-like delay between actions."""
    wait = random.uniform(min_s, max_s)
    await asyncio.sleep(wait)


class PMFBYBrowser:
    """Async Playwright wrapper with built-in delays and handoff support."""

    def __init__(self, headless: bool = True, verbose: bool = False):
        self.headless = headless
        self._playwright = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None
        self.page: Page | None = None
        self.verbose = verbose
        self._screenshots_dir = Path("screenshots")
        self._screenshots_dir.mkdir(exist_ok=True)
        self._vision = VisionHelper(verbose=verbose)

    async def launch(self) -> Page:
        """Launch the browser and return the page."""
        logger.step("Launching browser...")
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self.page = await self._context.new_page()
        logger.success("Browser launched")
        return self.page

    async def navigate(self, url: str) -> None:
        """Navigate to URL with retry on failure. Adds 3s delay after."""
        if not url.startswith("http"):
            url = f"{BASE_URL}{url}"

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.step(f"Navigating to {url}")
                await self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await asyncio.sleep(NAVIGATE_DELAY)
                logger.debug(f"Navigation complete (attempt {attempt})", self.verbose)
                return
            except Exception as e:
                logger.warning(f"Navigation failed (attempt {attempt}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES:
                    backoff = attempt * 3
                    logger.info(f"Retrying in {backoff}s...")
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Failed to navigate to {url} after {MAX_RETRIES} attempts")
                    raise

    async def click(self, selector: str, timeout: int = 10000) -> None:
        """Wait for element, click it, then delay 2-3s."""
        logger.debug(f"Clicking: {selector}", self.verbose)
        await self.page.wait_for_selector(selector, timeout=timeout)
        await self.page.click(selector)
        await _delay()

    async def fill(self, selector: str, value: str, timeout: int = 10000) -> None:
        """Clear field, type value with human-like delay, then delay 2-3s."""
        logger.debug(f"Filling: {selector}", self.verbose)
        await self.page.wait_for_selector(selector, timeout=timeout)
        await self.page.click(selector)
        await self.page.fill(selector, "")
        await self.page.type(selector, value, delay=random.randint(50, 120))
        await _delay()

    async def select_option(self, selector: str, value: str = None,
                            label: str = None, timeout: int = 10000) -> None:
        """Select a dropdown option, then delay 3s for AJAX loading."""
        logger.debug(f"Selecting option in: {selector}", self.verbose)
        await self.page.wait_for_selector(selector, timeout=timeout)
        if value:
            await self.page.select_option(selector, value=value)
        elif label:
            await self.page.select_option(selector, label=label)
        await asyncio.sleep(NAVIGATE_DELAY)  # AJAX wait

    async def wait_for(self, selector: str, timeout: int = 15000) -> None:
        """Wait for a selector to appear."""
        logger.debug(f"Waiting for: {selector}", self.verbose)
        await self.page.wait_for_selector(selector, timeout=timeout)

    async def wait_for_network_idle(self, timeout: int = 10000) -> None:
        """Wait until network is idle (no pending requests)."""
        try:
            await self.page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            logger.debug("Network idle timeout — continuing anyway", self.verbose)

    async def get_text(self, selector: str, timeout: int = 5000) -> str:
        """Extract visible text from an element."""
        try:
            await self.page.wait_for_selector(selector, timeout=timeout)
            return await self.page.inner_text(selector)
        except Exception:
            return ""

    async def get_all_text(self, selector: str) -> list[str]:
        """Extract text from all matching elements."""
        elements = await self.page.query_selector_all(selector)
        return [await el.inner_text() for el in elements]

    async def get_attribute(self, selector: str, attr: str) -> str | None:
        """Get an attribute value from an element."""
        try:
            el = await self.page.query_selector(selector)
            if el:
                return await el.get_attribute(attr)
        except Exception:
            pass
        return None

    async def get_dropdown_options(self, selector: str) -> list[dict]:
        """Get all options from a <select> element."""
        options = await self.page.query_selector_all(f"{selector} option")
        results = []
        for opt in options:
            value = await opt.get_attribute("value")
            text = (await opt.inner_text()).strip()
            if value and text and text != "Select" and text != "--Select--":
                results.append({"value": value, "text": text})
        return results

    async def is_visible(self, selector: str) -> bool:
        """Check if an element is visible on the page."""
        try:
            el = await self.page.query_selector(selector)
            if el:
                return await el.is_visible()
        except Exception:
            pass
        return False

    async def screenshot(self, name: str = "screenshot") -> str:
        """Take a screenshot and return the absolute file path."""
        path = self._screenshots_dir / f"{name}.png"
        await self.page.screenshot(path=str(path), full_page=False)
        logger.info(f"Screenshot saved: {path}")
        return str(path.resolve())

    # ── Vision-assisted interaction methods ──────────────────────────────────

    async def vision_click(self, selector: str, description: str,
                           timeout: int = 8000) -> bool:
        """
        Try to click 'selector'. If it fails, take a screenshot and ask the
        VLM to visually locate the element described by 'description',
        then click its coordinates.

        Args:
            selector:    Playwright CSS/text selector (tried first).
            description: Human-readable description for the VLM fallback,
                         e.g. 'the blue Calculate button in the modal'.
            timeout:     Timeout for the primary selector attempt (ms).

        Returns:
            True if click succeeded (via either method), False otherwise.
        """
        try:
            locator = self.page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click()
            await _delay()
            return True
        except Exception as primary_err:
            logger.warning(
                f"⚠  Primary click failed ({selector[:60]}): {primary_err}\n"
                f"   → Falling back to VLM vision"
            )

        # Vision fallback
        if not self._vision.available:
            logger.error("   Vision fallback unavailable — no API key configured")
            return False

        ss_path = await self.screenshot("vision_fallback_click")
        vp = self.page.viewport_size or {"width": 1280, "height": 900}
        coords = self._vision.locate_element(
            ss_path, description,
            page_width=vp["width"], page_height=vp["height"]
        )
        if coords is None:
            logger.error(f"   Vision fallback: could not locate '{description}'")
            return False

        x, y = coords
        logger.info(f"👁  Vision click at ({x}, {y})")
        await self.page.mouse.click(x, y)
        await _delay()
        return True

    async def vision_fill(self, selector: str, value: str, description: str,
                          timeout: int = 8000) -> bool:
        """
        Try to fill 'selector'. If it fails, use VLM to click the field
        visually, then type the value.

        Args:
            selector:    Playwright CSS selector (tried first).
            value:       Text to type into the field.
            description: Human-readable description for VLM fallback.
            timeout:     Timeout for primary selector (ms).

        Returns:
            True if fill succeeded, False otherwise.
        """
        try:
            locator = self.page.locator(selector).first
            await locator.wait_for(state="visible", timeout=timeout)
            await locator.click()
            await locator.fill("")
            await locator.type(value, delay=60)
            await _delay()
            return True
        except Exception as primary_err:
            logger.warning(
                f"⚠  Primary fill failed ({selector[:60]}): {primary_err}\n"
                f"   → Falling back to VLM vision for '{description}'"
            )

        # Vision fallback — click then type
        if not self._vision.available:
            logger.error("   Vision fallback unavailable — no API key configured")
            return False

        ss_path = await self.screenshot("vision_fallback_fill")
        vp = self.page.viewport_size or {"width": 1280, "height": 900}
        coords = self._vision.locate_element(
            ss_path, description,
            page_width=vp["width"], page_height=vp["height"]
        )
        if coords is None:
            logger.error(f"   Vision fallback: could not locate '{description}'")
            return False

        x, y = coords
        logger.info(f"👁  Vision fill at ({x}, {y}) — typing '{value[:20]}'")
        await self.page.mouse.click(x, y)
        await asyncio.sleep(0.5)
        # Select all + type to replace any existing content
        await self.page.keyboard.press("Control+a")
        await self.page.keyboard.type(value, delay=60)
        await _delay()
        return True

    async def vision_select(self, select_idx: int, label: str,
                            description: str) -> bool:
        """
        Try to set a <select> element by nth() index + JS dispatchEvent.
        If the option is not found or selection fails, ask VLM to locate
        the dropdown visually and click on it so the user can see it
        (or for future coordinate-based interaction).

        Args:
            select_idx:  Index of the <select> element on the page (0-based).
            label:       Option text to select (fuzzy matched).
            description: Human-readable description for VLM fallback.

        Returns:
            True if selection succeeded, False otherwise.
        """
        js = f"""
        (function() {{
            const sel = document.querySelectorAll('select')[{select_idx}];
            if (!sel) return 'NO_ELEMENT';
            const opts = Array.from(sel.options);
            let match = opts.find(o => o.text.trim().toLowerCase() === "{label.lower()}");
            if (!match) match = opts.find(
                o => o.text.trim().toLowerCase().includes("{label.lower()}")
            );
            if (match) {{
                sel.value = match.value;
                sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                return 'OK:' + match.text;
            }}
            return 'NOT_FOUND:' + opts.map(o => o.text.trim()).join('|');
        }})()
        """
        try:
            result = await self.page.evaluate(js)
            if result.startswith("OK:"):
                logger.success(f"  Select[{select_idx}] = {result[3:]}")
                await asyncio.sleep(3)
                return True
            elif result == "NO_ELEMENT":
                logger.warning(f"  Select[{select_idx}] does not exist on page")
            else:
                # NOT_FOUND — log available options and use vision fallback for click
                available = result.replace("NOT_FOUND:", "")
                logger.warning(
                    f"  Option '{label}' not found in select[{select_idx}].\n"
                    f"  Available: {available[:150]}"
                )
        except Exception as e:
            logger.warning(f"  JS select failed for select[{select_idx}]: {e}")

        # Vision fallback — at least visually locate and click the dropdown
        if not self._vision.available:
            return False

        logger.info(f"   → Vision fallback: trying to click dropdown '{description}'")
        ss_path = await self.screenshot("vision_fallback_select")
        vp = self.page.viewport_size or {"width": 1280, "height": 900}
        coords = self._vision.locate_element(
            ss_path, description,
            page_width=vp["width"], page_height=vp["height"]
        )
        if coords:
            x, y = coords
            logger.info(f"👁  Vision clicking dropdown at ({x}, {y})")
            await self.page.mouse.click(x, y)
            await asyncio.sleep(1)
            # Try JS select again after visual click
            try:
                result2 = await self.page.evaluate(js)
                if result2.startswith("OK:"):
                    logger.success(f"  Post-vision select[{select_idx}] = {result2[3:]}")
                    await asyncio.sleep(3)
                    return True
            except Exception:
                pass
        return False

    async def handoff_to_user(self, reason: str) -> bool:
        """
        Hand off browser control to the user for CAPTCHA/OTP.
        Switches to headed mode if in headless, waits for 'continue' command.
        Returns True if the challenge appears resolved.
        """
        if self.headless:
            logger.warning(
                "CAPTCHA/OTP detected but running in headless mode. "
                "Please re-run with --no-headless for manual challenges."
            )
            # Take a screenshot so user can see the CAPTCHA
            ss_path = await self.screenshot("captcha_challenge")
            logger.info(f"Challenge screenshot saved to: {ss_path}")

        logger.warning(f"Manual action required: {reason}")

        # Block until user says continue
        wait_for_continue(reason)

        # After user continues, give the page a moment to update
        await asyncio.sleep(2)
        logger.success("Resuming automated control...")
        return True

    async def get_page_info(self) -> dict:
        """Get current page title and URL."""
        return {
            "url": self.page.url,
            "title": await self.page.title(),
        }

    async def get_all_links(self) -> list[dict]:
        """Extract all internal links from the current page."""
        links = await self.page.eval_on_selector_all(
            "a[href]",
            """els => els.map(el => ({
                text: el.innerText.trim(),
                href: el.href,
                title: el.getAttribute('title') || ''
            })).filter(l => l.href.includes('pmfby.gov.in') || l.href.startsWith('/'))"""
        )
        return links

    async def close(self) -> None:
        """Clean up browser resources."""
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Browser closed")
