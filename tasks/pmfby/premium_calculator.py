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


# ── Modal select helpers ────────────────────────────────────────────────────

_MODAL_SEL = ".modal-body select, [class*='InnerCalculator'] select"


async def _get_modal_options(page: Page, idx: int) -> list[str]:
    """Return text options for modal's Nth select (excluding placeholder 'Select')."""
    try:
        js = f"""
        (() => {{
            const sels = document.querySelectorAll("{_MODAL_SEL}");
            const sel = sels[{idx}];
            if (!sel) return [];
            return Array.from(sel.options)
                .map(o => o.text.trim())
                .filter(t => t && t.toLowerCase() !== 'select' && t !== '--Select--');
        }})()
        """
        return await page.evaluate(js)
    except Exception:
        return []


async def _wait_modal_populated(page: Page, idx: int,
                                 min_count: int = 2, timeout_ms: int = 15000) -> bool:
    """Wait for modal select[idx] to have at least min_count options. Returns success bool."""
    try:
        await page.wait_for_function(
            f"""
            (() => {{
                const sels = document.querySelectorAll("{_MODAL_SEL}");
                const sel = sels[{idx}];
                return sel && sel.options.length >= {min_count};
            }})()
            """,
            timeout=timeout_ms,
        )
        return True
    except Exception:
        return False


async def _select_modal_by_label(page: Page, idx: int, label: str) -> str | None:
    """
    Select option in modal select[idx] using smart_match.
    Returns the matched option text, or None if no match found.
    """
    opts = await _get_modal_options(page, idx)
    matched = _smart_match(label, opts)
    if not matched:
        return None

    js = f"""
    (function() {{
        const sels = document.querySelectorAll("{_MODAL_SEL}");
        const sel = sels[{idx}];
        if (!sel) return false;
        const opts = Array.from(sel.options);
        const match = opts.find(o => o.text.trim() === {repr(matched)});
        if (match) {{
            sel.value = match.value;
            sel.dispatchEvent(new Event('change', {{bubbles: true}}));
            return true;
        }}
        return false;
    }})()
    """
    try:
        ok = await page.evaluate(js)
        if ok:
            await asyncio.sleep(3)
        return matched if ok else None
    except Exception:
        return None


async def _select_required(page: Page, idx: int, label: str,
                            field_name: str, wait_next: int | None = None) -> str:
    """
    Select a required field. Raises TaskAbortError if selection fails.
    Optionally waits for the next dropdown (wait_next index) to populate.
    Returns the matched option text.
    """
    opts = await _get_modal_options(page, idx)
    if not opts:
        raise TaskAbortError(
            f"Required field '{field_name}' has no options available — "
            "the previous cascade selection may have failed."
        )

    matched = await _select_modal_by_label(page, idx, label)
    if matched is None:
        raise TaskAbortError(
            f"Could not select '{label}' for field '{field_name}'.\n"
            f"Available options ({len(opts)}): {', '.join(opts[:10])}"
            + ("..." if len(opts) > 10 else "")
        )

    logger.success(f"  Selected {field_name}: {matched}")

    if wait_next is not None:
        populated = await _wait_modal_populated(page, wait_next)
        if not populated:
            raise TaskAbortError(
                f"Field '{field_name}' was selected but the next dropdown "
                f"(select[{wait_next}]) did not populate — page may not have responded."
            )

    return matched


# ── Main Task Handler ───────────────────────────────────────────────────────

class PremiumCalculatorTask:
    """Handles the insurance premium calculation modal on PMFBY homepage."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def calculate(self, **pre_params) -> dict:
        """
        Open the Premium Calculator modal on the homepage and fill cascading dropdowns.

        Auto-selects all fields using params extracted from the user's prompt.
        Only asks for user input when a field is genuinely not specified.
        Aborts with a clear message on any required selection failure.

        Modal cascade order: Season[0] → Year[1] → Scheme[2] → State[3] → District[4] → Crop[5]
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
        if not await _wait_modal_populated(page, 0):
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

        # ── Season (index 0) — Required: 'season' from prompt ────────────
        season_raw = params.get("season", "")
        if not season_raw:
            # Only ask user if genuinely not in prompt
            opts = await _get_modal_options(page, 0)
            logger.info(f"Seasons available: {opts}")
            season_raw = prompt_user("Season (Kharif / Rabi)")

        season = await _select_required(
            page, 0, season_raw, "Season", wait_next=1
        )

        # ── Year (index 1) — Default to 2025 unless specified ────────────
        year_raw = params.get("year", "2025")
        year = await _select_required(page, 1, year_raw, "Year", wait_next=2)

        # ── Scheme (index 2) — Auto-pick PMFBY default if not specified ──
        scheme_opts = await _get_modal_options(page, 2)
        logger.info(f"Schemes available: {scheme_opts}")
        scheme_raw = params.get("scheme", "")
        if not scheme_raw:
            # Default to the first scheme (usually PMFBY) without prompting
            scheme_raw = scheme_opts[0] if scheme_opts else "PMFBY"
            logger.info(f"No scheme in prompt — auto-selecting: '{scheme_raw}'")

        scheme = await _select_required(page, 2, scheme_raw, "Scheme", wait_next=3)

        # ── State (index 3) — Required: 'state' from prompt ─────────────
        state_raw = params.get("state", "")
        if not state_raw:
            state_opts = await _get_modal_options(page, 3)
            logger.info(f"States ({len(state_opts)}): {', '.join(state_opts[:5])}...")
            state_raw = prompt_user("State")

        state = await _select_required(page, 3, state_raw, "State", wait_next=4)

        # ── District (index 4) — Ask user if not in prompt ───────────────
        district_raw = params.get("district", "")
        district_opts = await _get_modal_options(page, 4)
        logger.info(f"Districts ({len(district_opts)}): {', '.join(district_opts[:5])}...")
        if not district_raw:
            district_raw = prompt_user("District")

        district = await _select_required(page, 4, district_raw, "District", wait_next=5)

        # ── Crop (index 5) — Required: 'crop' from prompt ────────────────
        crop_raw = params.get("crop", "")
        crop_opts = await _get_modal_options(page, 5)

        if not crop_raw:
            logger.info(f"Available crops: {', '.join(crop_opts)}")
            crop_raw = prompt_user("Crop Name")

        # Check crop availability BEFORE attempting selection
        matched_crop = _smart_match(crop_raw, crop_opts)
        if matched_crop is None:
            # Crop not available — clean abort with full options list
            raise TaskAbortError(
                f"Crop '{crop_raw}' is not available for the selected "
                f"scheme/season/state/district combination.\n\n"
                f"Available crops ({len(crop_opts)}):\n"
                + "\n".join(f"  • {c}" for c in sorted(crop_opts))
                + f"\n\nTip: Re-run with one of the listed crops above."
            )

        crop = await _select_required(page, 5, crop_raw, "Crop")

        # ── Click Calculate ───────────────────────────────────────────────
        logger.step("Clicking Calculate...")
        try:
            calc_btn = page.locator("button:has-text('Calculate')").last
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
            "area_ha": params.get("area", ""),
            "status": "completed",
            "result_preview": result_text[:600] if result_text else "See premium_result.png",
        }

    def _abort(self, reason: str) -> dict:
        logger.error(f"\n❌ Calculation aborted: {reason}\n")
        return {"task": "premium_calculator", "status": "aborted", "reason": reason}
