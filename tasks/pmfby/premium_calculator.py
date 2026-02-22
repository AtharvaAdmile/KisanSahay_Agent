"""
Premium Calculator task handler.
Revised based on live exploration — 2026-02-20.
Behaviour fixes (v3):
  - Auto-selects from prompt params without prompting user
  - Aborts immediately on required-field selection failure (no silent continuation)
  - Shows available options and aborts when crop not found in list
  - Uses smart_match: exact → partial → acronym → metaphone

KEY FACTS from live exploration:
  - Calculator is a MODAL on the homepage.
  - Entry: click service card[1] ('Calculate') on homepage.
  - 6 selects in modal, all unnamed, scoped as '.modal-body select'
  - Cascade order: Season[0] → Year[1] → Scheme[2] → State[3] → District[4] → Crop[5]
  - Season values: "01///Kharif", "02///Rabi"  (option text = "Kharif", "Rabi")
  - "PMFBY" is the abbreviation for "Pradhan Mantri Fasal Bima Yojana"
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import re

from playwright.async_api import Page

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import prompt_user, display_table


# ── Custom exception for hard stops ────────────────────────────────────────

class TaskAbortError(Exception):
    """Raised when the task cannot proceed and must stop cleanly."""


# ── Smart fuzzy matching ────────────────────────────────────────────────────

def _acronym_of(abbr: str, phrase: str) -> bool:
    """
    Return True if 'abbr' is an acronym (initial letters) of 'phrase'.
    E.g. "PMFBY" matches "Pradhan Mantri Fasal Bima Yojana"
    """
    words = re.findall(r"[A-Za-z]+", phrase)
    initials = "".join(w[0].upper() for w in words if w)
    return abbr.upper() == initials


def _smart_match(label: str, options: list[str]) -> str | None:
    """
    Find the best match for 'label' in 'options' using a priority chain:
      1. Exact match (case-insensitive)
      2. Partial / substring match
      3. Acronym match (e.g. "PMFBY" → "Pradhan Mantri Fasal Bima Yojana")
      4. Token overlap (any word in label appears in option)

    Returns the matched option string, or None if no match.
    """
    lw = label.strip().lower()

    # 1. Exact
    for opt in options:
        if opt.strip().lower() == lw:
            return opt

    # 2. Partial (label is substring of option, or option is substring of label)
    for opt in options:
        if lw in opt.strip().lower() or opt.strip().lower() in lw:
            return opt

    # 3. Acronym
    for opt in options:
        if _acronym_of(label.strip(), opt.strip()):
            return opt

    # 4. Token overlap — any meaningful word (>3 chars) from label appears in option
    words = [w for w in re.findall(r"[a-z]+", lw) if len(w) > 3]
    for opt in options:
        opt_lower = opt.strip().lower()
        if any(w in opt_lower for w in words):
            return opt

    return None

# ── Hardcoded Selectors for Calculation fields ──────────────────────────────

SEL_SEASON = "#app > div > div:nth-child(1) > div > div.newHeader__headerMain___3js6e > div.newHeader__cardsMenu___1Sgs1.container-fluid > div > div:nth-child(1) > div > div.newHeader__modalInnerOverlay___2U5R2 > div > div > div > div > div.newHeader__InnerCalculator___1YK6V.modal-body > form > div > div > div:nth-child(1) > div > select"
SEL_YEAR = "#app > div > div:nth-child(1) > div > div.newHeader__headerMain___3js6e > div.newHeader__cardsMenu___1Sgs1.container-fluid > div > div:nth-child(1) > div > div.newHeader__modalInnerOverlay___2U5R2 > div > div > div > div > div.newHeader__InnerCalculator___1YK6V.modal-body > form > div > div > div:nth-child(2) > div > select"
SEL_SCHEME = "#app > div > div:nth-child(1) > div > div.newHeader__headerMain___3js6e > div.newHeader__cardsMenu___1Sgs1.container-fluid > div > div:nth-child(1) > div > div.newHeader__modalInnerOverlay___2U5R2 > div > div > div > div > div.newHeader__InnerCalculator___1YK6V.modal-body > form > div > div > div:nth-child(3) > div > select"
SEL_STATE = "#app > div > div:nth-child(1) > div > div.newHeader__headerMain___3js6e > div.newHeader__cardsMenu___1Sgs1.container-fluid > div > div:nth-child(1) > div > div.newHeader__modalInnerOverlay___2U5R2 > div > div > div > div > div.newHeader__InnerCalculator___1YK6V.modal-body > form > div > div > div:nth-child(4) > div > select"
SEL_DISTRICT = "#app > div > div:nth-child(1) > div > div.newHeader__headerMain___3js6e > div.newHeader__cardsMenu___1Sgs1.container-fluid > div > div:nth-child(1) > div > div.newHeader__modalInnerOverlay___2U5R2 > div > div > div > div > div.newHeader__InnerCalculator___1YK6V.modal-body > form > div > div > div:nth-child(5) > div > select"
SEL_CROP = "xpath=//*[@id=\"app\"]/div/div[1]/div/div[2]/div[3]/div/div[1]/div/div[3]/div/div/div/div/div[2]/form/div/div/div[6]/div/select"
SEL_AREA = "#app > div > div:nth-child(1) > div > div.newHeader__headerMain___3js6e > div.newHeader__cardsMenu___1Sgs1.container-fluid > div > div:nth-child(1) > div > div.newHeader__modalInnerOverlay___2U5R2 > div > div > div > div > div.newHeader__InnerCalculator___1YK6V.modal-body > form > div > div > div:nth-child(7) > div > input"
SEL_CALCULATE = "#app > div > div:nth-child(1) > div > div.newHeader__headerMain___3js6e > div.newHeader__cardsMenu___1Sgs1.container-fluid > div > div:nth-child(1) > div > div.newHeader__modalInnerOverlay___2U5R2 > div > div > div > div > div.newHeader__cardFooter___1P8JE.modal-footer > div > button:nth-child(2)"


# ── Main Task Handler ───────────────────────────────────────────────────────

class PremiumCalculatorTask:
    """Handles the insurance premium calculation modal on PMFBY homepage."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def _ask_sahayak(self, executor, question: str, options: list = None) -> str:
        """Uses executor queues to ask frontend Sahayak and get user response."""
        if not executor:
            if options:
                logger.info(f"Available options: {options}")
            return prompt_user(question)
        
        await executor.agent_output_queue.put({
            "status": "requires_input",
            "question": question,
            "options": options or []
        })
        answer = await executor._await_user_input()
        return answer

    async def _get_options_for_selector(self, page: Page, selector: str) -> list[str]:
        """Return text options for a specific select element."""
        try:
            options = await page.locator(selector).locator("option").evaluate_all(
                "opts => opts.map(o => o.textContent.trim()).filter(t => t && t.toLowerCase() !== 'select' && t !== '--Select--')"
            )
            return options
        except Exception:
            return []

    async def _wait_selector_populated(self, page: Page, selector: str, min_count: int = 2) -> bool:
        """Wait for specific select to have at least min_count options."""
        try:
            for _ in range(30):
                count = await page.locator(selector).locator("option").count()
                if count >= min_count:
                    return True
                await asyncio.sleep(0.5)
            return False
        except Exception:
            return False

    async def _select_by_selector_label(self, page: Page, selector: str, label: str) -> str | None:
        """
        Select option in specific select using smart_match.
        Returns the matched option text, or None if no match found.
        """
        opts = await self._get_options_for_selector(page, selector)
        if not opts:
            return None
            
        matched = _smart_match(label, opts)
        if not matched:
            return None

        try:
            # Playwright select_option automatically dispatches 'change' and handles matching
            await page.locator(selector).select_option(label=matched)
            await asyncio.sleep(2)
            return matched
        except Exception:
            try:
                # Fallback to value if label matching fails
                await page.locator(selector).select_option(value=matched)
                await asyncio.sleep(2)
                return matched
            except Exception:
                return None
            
    async def _select_required(self, page: Page, selector: str, label: str, field_name: str) -> str:
        matched = await self._select_by_selector_label(page, selector, label)
        if not matched:
            opts = await self._get_options_for_selector(page, selector)
            raise TaskAbortError(
                f"Could not select '{label}' for field '{field_name}'.\n"
                f"Available options ({len(opts)}): {', '.join(opts[:10])}..."
            )
        logger.success(f"  Selected {field_name}: {matched}")
        return matched

    async def calculate(self, **pre_params) -> dict:
        """
        Open the Premium Calculator modal on the homepage and fill cascading dropdowns using interactive mode.

        Modal cascade order: Season → Year → Scheme → State → District → Crop
        """
        logger.section("Insurance Premium Calculator")
        logger.info("Opening the premium calculator modal on the homepage.\n")

        page = self.browser.page

        # ── Navigate and open modal ──────────────────────────────────────
        await self.browser.navigate("https://pmfby.gov.in/")
        await asyncio.sleep(3)

        logger.step("Clicking 'Insurance Premium Calculator' service card (index 1)...")
        try:
            card = page.locator('[class*="ciListBtn"]').nth(1)
            await card.wait_for(state="visible", timeout=8000)
            await card.click()
            await asyncio.sleep(3)
            logger.success("Premium Calculator modal opened")
        except Exception as e:
            return self._abort(f"Could not open calculator modal: {e}")

        # Wait for modal
        try:
            await page.wait_for_selector(
                '[class*="InnerCalculator"], .modal-body', timeout=8000
            )
        except Exception:
            logger.warning("Modal selector timeout — proceeding anyway")

        # Confirm first dropdown is ready
        if not await self._wait_selector_populated(page, SEL_SEASON):
            return self._abort("Modal did not load its dropdowns in time.")

        try:
            return await self._fill_and_calculate(page, pre_params)
        except TaskAbortError as e:
            logger.error(f"\n❌ Calculation aborted: {e}\n")
            await self.browser.screenshot("premium_calc_abort")
            return {
                "task": "premium_calculator",
                "status": "aborted",
                "reason": str(e),
            }

    async def _fill_and_calculate(self, page: Page, params: dict) -> dict:
        """Fill modal dropdowns, click Calculate, extract result."""
        executor = params.get("executor")
        profile = params.get("profile", {})
        
        # ── Season ────────────────────────────────────────────────────────
        season_opts = await self._get_options_for_selector(page, SEL_SEASON)
        season_raw = await self._ask_sahayak(executor, "Please pick a season for insurance premium calculation.", season_opts)
        season = await self._select_required(page, SEL_SEASON, season_raw, "Season")

        await self._wait_selector_populated(page, SEL_YEAR)

        # ── Year ──────────────────────────────────────────────────────────
        year_opts = await self._get_options_for_selector(page, SEL_YEAR)
        year_raw = await self._ask_sahayak(executor, "Please pick a year.", year_opts)
        year = await self._select_required(page, SEL_YEAR, year_raw, "Year")

        await self._wait_selector_populated(page, SEL_SCHEME)

        # ── Scheme ────────────────────────────────────────────────────────
        # Always "Pradhan Mantri Fasal Bima Yojna" (or PMFBY)
        scheme_raw = "Pradhan Mantri Fasal Bima Yojna"
        scheme = await self._select_by_selector_label(page, SEL_SCHEME, scheme_raw)
        if not scheme: 
            scheme = await self._select_required(page, SEL_SCHEME, "PMFBY", "Scheme")
        else:
            logger.success(f"  Selected Scheme: {scheme}")

        await self._wait_selector_populated(page, SEL_STATE)

        # ── State ─────────────────────────────────────────────────────────
        state_raw = profile.get("state")
        if not state_raw:
            state_raw = profile.get("address.state")
        if not state_raw:
            state_opts = await self._get_options_for_selector(page, SEL_STATE)
            state_raw = await self._ask_sahayak(executor, "I could not find your state in the profile. Which state?", state_opts)
            
        state = await self._select_required(page, SEL_STATE, state_raw, "State")

        await self._wait_selector_populated(page, SEL_DISTRICT)

        # ── District ──────────────────────────────────────────────────────
        district_raw = profile.get("district")
        if not district_raw:
            district_raw = profile.get("address.district")
        if not district_raw:
            district_opts = await self._get_options_for_selector(page, SEL_DISTRICT)
            district_raw = await self._ask_sahayak(executor, "I could not find your district. Which district?", district_opts)
            
        district = await self._select_required(page, SEL_DISTRICT, district_raw, "District")

        await self._wait_selector_populated(page, SEL_CROP)

        # ── Crop ──────────────────────────────────────────────────────────
        crop_opts = await self._get_options_for_selector(page, SEL_CROP)
        crop_raw = await self._ask_sahayak(executor, "Which crop are you insuring?", crop_opts)
        crop = await self._select_required(page, SEL_CROP, crop_raw, "Crop")

        # ── Area ──────────────────────────────────────────────────────────
        area_raw = await self._ask_sahayak(executor, "Please enter the area of your land in hectares.")
        await page.fill(SEL_AREA, area_raw)
        logger.success(f"  Filled Area: {area_raw}")

        # ── Click Calculate ───────────────────────────────────────────────
        logger.step("Clicking Calculate...")
        try:
            calc_btn = page.locator(f"{SEL_CALCULATE}, button:has-text('Calculate')").last
            await calc_btn.wait_for(state="visible", timeout=5000)
            await calc_btn.click()
            await asyncio.sleep(5)
            logger.success("Calculate clicked — waiting for result...")
        except Exception as e:
            raise TaskAbortError(f"Calculate button not found or not clickable: {e}")

        # ── Extract result ────────────────────────────────────────────────
        await asyncio.sleep(2)
        result_text = ""
        for sel in [
            ".modal-body table",
            "[class*='InnerCalculator'] table",
            ".modal-body .result",
            "[class*='premiumResult']",
            ".modal-body",
        ]:
            try:
                txt = await page.inner_text(sel)
                if txt and len(txt.strip()) > 20:
                    result_text = txt.strip()
                    break
            except Exception:
                continue

        if result_text:
            logger.section("Premium Calculation Result")
            for line in result_text.split("\n")[:25]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning("Could not auto-extract result — check the browser window.")

        await self.browser.screenshot("premium_result")

        return {
            "task": "premium_calculator",
            "season": season,
            "year": year,
            "scheme": scheme,
            "state": state,
            "district": district,
            "crop": crop,
            "area_ha": area_raw,
            "status": "completed",
            "result_preview": result_text[:600] if result_text else "See premium_result.png",
        }

    def _abort(self, reason: str) -> dict:
        logger.error(f"\n❌ Calculation aborted: {reason}\n")
        return {"task": "premium_calculator", "status": "aborted", "reason": reason}

