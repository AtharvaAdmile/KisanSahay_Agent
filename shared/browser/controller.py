"""
Async Playwright browser controller for Government Scheme Agents.
Every action includes a mandatory 2-3 second delay to respect government servers.
Includes handoff_to_user for CAPTCHA/OTP challenges.

Site-specific behaviors are controlled by the SiteConfig:
  - has_homepage_modal: Whether to dismiss modal on homepage
  - uses_aspnet_postback: Whether to wait for __doPostBack
  - has_language_selector: Whether set_language() is available
"""

import asyncio
import random
from pathlib import Path
from playwright.async_api import async_playwright, Browser, Page, BrowserContext

from ..config.base import SiteConfig
from ..utils import logger
from ..utils.helpers import wait_for_continue
from ..utils.vision import VisionHelper

ACTION_DELAY_MIN = 2.0
ACTION_DELAY_MAX = 3.0
MAX_RETRIES = 3


async def _delay(min_s: float = ACTION_DELAY_MIN, max_s: float = ACTION_DELAY_MAX):
    """Human-like delay between actions."""
    wait = random.uniform(min_s, max_s)
    await asyncio.sleep(wait)


class Browser:
    """Async Playwright wrapper with built-in delays and handoff support."""

    def __init__(self, config: SiteConfig, headless: bool = True, verbose: bool = False):
        self.config = config
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
        """Navigate to URL with retry on failure. Adds delay after."""
        if not url.startswith("http"):
            url = f"{self.config.base_url}{url}"

        timeout = self.config.navigate_timeout
        delay = self.config.navigate_delay

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.step(f"Navigating to {url}")
                try:
                    await self.page.goto(url, wait_until="load", timeout=timeout)
                except Exception:
                    logger.debug(f"Full load timed out — retrying with domcontentloaded", self.verbose)
                    await self.page.goto(url, wait_until="domcontentloaded", timeout=timeout)
                await asyncio.sleep(delay)
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
        """Select a dropdown option robustly, handling label/value confusion."""
        logger.debug(f"Selecting option in: {selector}", self.verbose)
        await self.page.wait_for_selector(selector, timeout=timeout)
        
        try:
            if value:
                # Try selecting by exactly the value specified
                await self.page.select_option(selector, value=value, timeout=2000)
            elif label:
                await self.page.select_option(selector, label=label, timeout=2000)
        except Exception as e:
            # Fallback: Sometimes the LLM passes the label string directly to 'value='
            if value and not label:
                logger.debug(f"Select by value failed, trying by label '{value}'...")
                try:
                    await self.page.select_option(selector, label=value, timeout=2000)
                except Exception as e2:
                    logger.warning(f"Failed to select dropdown option: {e2}")
            else:
                logger.warning(f"Failed to select dropdown option: {e}")
                
        await asyncio.sleep(self.config.navigate_delay)

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

    async def wait_for_postback(self, timeout: int = 12000) -> None:
        """
        Wait for an ASP.NET __doPostBack to complete.
        Only used when config.uses_aspnet_postback is True.
        """
        if not self.config.uses_aspnet_postback:
            return
        try:
            await self.page.wait_for_load_state("domcontentloaded", timeout=timeout)
        except Exception:
            pass
        await asyncio.sleep(3)

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
            if value and text and text not in ("Select", "--Select--", "--Select State--"):
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

    async def dismiss_homepage_modal(self) -> None:
        """
        Dismiss homepage modal if the site has one.
        Uses JavaScript DOM removal for reliability.
        """
        if not self.config.has_homepage_modal:
            return

        try:
            result = await self.page.evaluate("""
            () => {
                let removed = 0;
                document.querySelectorAll(
                    '.modal, .modal-backdrop, #exampleModal, [id*="modal"]'
                ).forEach(el => {
                    el.style.display = 'none';
                    el.classList.remove('show', 'modal-show', 'fade');
                    removed++;
                });
                document.body.classList.remove('modal-open');
                document.body.style.overflow = 'auto';
                document.body.style.paddingRight = '';
                return removed;
            }
            """)
            if result and int(result) > 0:
                logger.debug(f"Modal dismissed via JS ({result} element(s) hidden)", self.verbose)
                await asyncio.sleep(0.5)
                return
        except Exception as e:
            logger.debug(f"JS modal dismissal attempted: {e}", self.verbose)

        for sel in ["button.close", "[aria-label='Close']", ".modal-header .close",
                    "button[data-dismiss='modal']", ".btn-close"]:
            try:
                if await self.is_visible(sel):
                    await self.page.click(sel, timeout=2000)
                    await asyncio.sleep(0.5)
                    logger.debug(f"Modal closed via click ({sel})", self.verbose)
                    return
            except Exception:
                continue
        logger.debug("No modal found (or already closed)", self.verbose)

    async def set_language(self, lang: str = "English") -> bool:
        """
        Switch the site language using the language dropdown.
        Only works if config.has_language_selector is True.
        """
        if not self.config.has_language_selector:
            logger.warning("This site does not have a language selector")
            return False

        try:
            await self.page.select_option("#ddlLanguage", label=lang)
            await asyncio.sleep(2)
            logger.success(f"Language switched to: {lang}")
            return True
        except Exception as e:
            logger.warning(f"Could not switch language to '{lang}': {e}")
            return False

    async def vision_click(self, selector: str, description: str,
                           timeout: int = 8000) -> bool:
        """
        Try to click 'selector'. If it fails, use VLM to visually locate
        the element and click its coordinates.
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
        await self.page.keyboard.press("Control+a")
        await self.page.keyboard.type(value, delay=60)
        await _delay()
        return True

    async def vision_select(self, select_idx: int, label: str,
                            description: str) -> bool:
        """
        Try to set a <select> element by nth() index + JS dispatchEvent.
        If the option is not found, use VLM to locate the dropdown visually.
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
                available = result.replace("NOT_FOUND:", "")
                logger.warning(
                    f"  Option '{label}' not found in select[{select_idx}].\n"
                    f"  Available: {available[:150]}"
                )
        except Exception as e:
            logger.warning(f"  JS select failed for select[{select_idx}]: {e}")

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
            try:
                result2 = await self.page.evaluate(js)
                if result2.startswith("OK:"):
                    logger.success(f"  Post-vision select[{select_idx}] = {result2[3:]}")
                    await asyncio.sleep(3)
                    return True
            except Exception:
                pass
        return False

    async def detect_captcha(self) -> bool:
        """Return True if a CAPTCHA element is visible on the current page."""
        selectors = [
            "img[src*='captcha']",
            "img[src*='Captcha']",
            "img[id*='captcha']",
            "img[id*='Captcha']",
            "canvas[id*='captcha']",
            "#captchaImg",
            ".captcha-img",
            "[class*='captcha'] img",
        ]
        for sel in selectors:
            if await self.is_visible(sel):
                logger.debug(f"CAPTCHA detected via selector: {sel}", self.verbose)
                return True
        return False

    async def handle_captcha(self) -> bool:
        """
        Detect a CAPTCHA on the page, take a screenshot, and hand off to
        the user for manual solving.
        """
        await self.screenshot("captcha_detected")
        logger.warning(
            "CAPTCHA detected — manual interaction required.\n"
            "The current page screenshot has been saved."
        )
        await self.handoff_to_user(
            "Please solve the CAPTCHA shown in the browser window, "
            "enter the solution in the CAPTCHA field, then type 'continue'."
        )
        return True

    async def handle_otp_flow(
        self,
        mobile_or_aadhaar: str,
        input_selector: str,
        captcha_selector: str = None,
        otp_btn_selector: str = None,
        label: str = "mobile number",
    ) -> bool:
        """
        Standard OTP flow:
          1. Fill input field
          2. Handoff for CAPTCHA solving (if applicable)
          3. Click OTP button (if applicable)
          4. Handoff for OTP entry
        """
        logger.step(f"Starting OTP flow for {label}...")

        await self.vision_fill(
            input_selector, mobile_or_aadhaar,
            f"the {label} input field"
        )

        if captcha_selector or otp_btn_selector:
            await self.screenshot("otp_flow_captcha")
            logger.warning("CAPTCHA required before OTP can be sent.")
            instructions = "Please:\n  1. Solve the CAPTCHA shown in the browser\n"
            if otp_btn_selector:
                instructions += "  2. Enter it in the CAPTCHA text field\n  3. Click 'Get OTP'\n"
            else:
                instructions += "  2. Enter it in the CAPTCHA field\n"
            instructions += "  Then type 'continue' here."
            await self.handoff_to_user(instructions)

        await asyncio.sleep(2)
        logger.warning(f"OTP has been sent to your registered number.")
        await self.handoff_to_user(
            "Enter the OTP received on your registered mobile. "
            "Please enter it in the browser OTP field, then type 'continue'."
        )

        await asyncio.sleep(2)
        logger.success("OTP flow handoffs completed — resuming automation.")
        return True

    async def handoff_to_user(self, reason: str) -> bool:
        """
        Hand off browser control to the user for CAPTCHA/OTP.
        Warns if in headless mode. Blocks until user types 'continue'.
        """
        if self.headless:
            logger.warning(
                "CAPTCHA/OTP detected but running in headless mode. "
                "Please re-run with --no-headless for manual challenges."
            )
            ss_path = await self.screenshot("captcha_challenge")
            logger.info(f"Challenge screenshot saved to: {ss_path}")

        logger.warning(f"Manual action required: {reason}")
        wait_for_continue(reason)

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
        site_domain = self.config.base_url.replace("https://", "").replace("http://", "")
        links = await self.page.eval_on_selector_all(
            "a[href]",
            f"""els => els.map(el => ({{
                text: el.innerText.trim(),
                href: el.href,
                title: el.getAttribute('title') || ''
            }})).filter(l => l.href.includes('{site_domain}') || l.href.startsWith('/'))"""
        )
        return links

    async def get_dom_state(self) -> list[dict]:
        """
        Extract a structured representation of the currently visible and interactable
        form elements (inputs, selects, buttons) to pass to the ReasoningEngine.
        Injects a unique data-agent-id into every visible element to guarantee valid selectors
        even for elements without IDs or names.
        """
        js = """
        () => {
            const isVisible = (elem) => !!( elem.offsetWidth || elem.offsetHeight || elem.getClientRects().length );
            
            const results = [];
            let counter = 0;
            
            const getLabel = (el) => {
                // 1. Check for 'for' label
                if (el.id) {
                    const lbl = document.querySelector(`label[for="${el.id}"]`);
                    if (lbl) return lbl.innerText.replace('*', '').trim();
                }
                // 2. Check parent wrappers (Angular/React structures)
                let parent = el.parentElement;
                let depth = 0;
                while (parent && depth < 3) {
                    const childLabel = parent.querySelector('label');
                    if (childLabel) return childLabel.innerText.replace('*', '').trim();
                    
                    const prev = parent.previousElementSibling;
                    if (prev && prev.innerText && prev.innerText.trim().length > 0 && prev.innerText.trim().length < 50) {
                        return prev.innerText.replace('*', '').trim();
                    }
                    parent = parent.parentElement;
                    depth++;
                }
                
                // 3. Fallback to placeholder or title
                return el.placeholder || el.title || "";
            };
            
            // 1. Inputs
            document.querySelectorAll('input:not([type="hidden"])').forEach(el => {
                if (!isVisible(el) || el.disabled) return;
                
                // Skip CAPTCHA text box explicitly if we want to deprioritize, but we just mark it
                const isCaptcha = el.id.toLowerCase().includes('captcha') || el.name.toLowerCase().includes('captcha') || el.placeholder.toLowerCase().includes('captcha');
                
                counter++;
                el.setAttribute('data-agent-id', `agent-input-${counter}`);
                
                results.push({
                    type: "input",
                    inputType: el.type,
                    label: getLabel(el),
                    placeholder: el.placeholder || "",
                    value: el.value || "",
                    isCaptcha: isCaptcha,
                    selector: `[data-agent-id="agent-input-${counter}"]`
                });
            });
            
            // 2. Selects
            document.querySelectorAll('select').forEach(el => {
                if (!isVisible(el) || el.disabled) return;
                
                counter++;
                el.setAttribute('data-agent-id', `agent-select-${counter}`);
                
                const rawOptions = Array.from(el.options);
                const placeholder = rawOptions.length > 0 ? rawOptions[0].text.trim() : "";
                
                const options = rawOptions
                    .map(o => ({ value: o.value, text: o.text.trim() }))
                    .filter(o => o.value && o.text && o.text.toLowerCase() !== "select" && !o.text.toLowerCase().includes("--select"));
                
                let label = getLabel(el);
                if (!label) label = placeholder;
                
                results.push({
                    type: "select",
                    label: label,
                    value: el.value || "",
                    options: options,
                    selector: `[data-agent-id="agent-select-${counter}"]`
                });
            });
            
            // 3. Buttons & Radio/Checkboxes
            document.querySelectorAll('button, input[type="submit"], input[type="button"], a.btn, input[type="radio"], input[type="checkbox"]').forEach(el => {
                if (!isVisible(el) || el.disabled) return;
                
                counter++;
                el.setAttribute('data-agent-id', `agent-action-${counter}`);
                
                if (el.tagName.toLowerCase() === 'input' && (el.type === 'radio' || el.type === 'checkbox')) {
                    results.push({
                        type: el.type,
                        name: el.name || "",
                        label: el.nextSibling ? el.nextSibling.textContent.trim() : getLabel(el),
                        checked: el.checked,
                        selector: `[data-agent-id="agent-action-${counter}"]`
                    });
                } else {
                    let text = el.innerText ? el.innerText.trim() : (el.value ? el.value.trim() : "");
                    results.push({
                        type: "button",
                        text: text,
                        selector: `[data-agent-id="agent-action-${counter}"]`
                    });
                }
            });
            
            return results;
        }
        """
        try:
            return await self.page.evaluate(js)
        except Exception as e:
            logger.error(f"Failed to get DOM state: {e}")
            return []

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
