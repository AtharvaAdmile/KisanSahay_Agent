"""
Farmer Registration (Crop Insurance Application) task handler.
Revised based on live exploration of pmfby.gov.in on 2026-02-20.

KEY FINDING: All form elements on the registration form lack 'id' and 'name'
attributes. Selectors MUST use nth() index-based addressing.
The form lives at /farmerRegistrationForm after clicking:
  Homepage → "Farmer Corner" card (index 0) → "Guest Farmer" button
"""

import asyncio
from playwright.async_api import Page

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import prompt_user, prompt_confirm


# ── Helpers ────────────────────────────────────────────────────────────────

async def _wait_for_options(page: Page, select_idx: int,
                            min_count: int = 2, timeout_ms: int = 12000) -> None:
    """Wait until the nth select element has at least min_count options (AJAX loads)."""
    try:
        await page.wait_for_function(
            f"document.querySelectorAll('select')[{select_idx}].options.length >= {min_count}",
            timeout=timeout_ms,
        )
    except Exception:
        logger.warning(f"Timeout waiting for select[{select_idx}] to populate — continuing anyway")


async def _select_nth_by_label(page: Page, select_idx: int, label: str) -> bool:
    """
    Select the option in the Nth <select> element whose text matches label (fuzzy).
    Returns True if successful.
    """
    try:
        js = f"""
        (function() {{
            const sel = document.querySelectorAll('select')[{select_idx}];
            if (!sel) return false;
            const opts = Array.from(sel.options);
            // Exact match
            let match = opts.find(o => o.text.trim().toLowerCase() === "{label.lower()}");
            // Partial match if no exact
            if (!match) match = opts.find(o => o.text.trim().toLowerCase().includes("{label.lower()}"));
            if (match) {{
                sel.value = match.value;
                sel.dispatchEvent(new Event('change', {{bubbles: true}}));
                return match.text;
            }}
            return false;
        }})()
        """
        result = await page.evaluate(js)
        if result:
            logger.success(f"  Selected select[{select_idx}]: {result}")
            await asyncio.sleep(3)  # Wait for AJAX cascade
            return True
        else:
            logger.warning(f"  No match for '{label}' in select[{select_idx}]")
            return False
    except Exception as e:
        logger.warning(f"  select[{select_idx}] error: {e}")
        return False


async def _fill_nth_input(page: Page, input_idx: int, value: str) -> None:
    """Fill the Nth <input> element on the page."""
    try:
        locator = page.locator("input").nth(input_idx)
        await locator.wait_for(state="visible", timeout=5000)
        await locator.click()
        await locator.fill("")
        await locator.type(value, delay=60)
        await asyncio.sleep(1)
        logger.debug(f"  Filled input[{input_idx}]: {value[:30]}", verbose=True)
    except Exception as e:
        logger.warning(f"  Could not fill input[{input_idx}]: {e}")


async def _list_nth_select_options(page: Page, select_idx: int) -> list:
    """Return the option texts of the Nth select element."""
    try:
        js = f"""
        Array.from(document.querySelectorAll('select')[{select_idx}].options)
             .map(o => o.text.trim()).filter(t => t && t !== 'Select' && t !== '--Select--')
        """
        return await page.evaluate(js)
    except Exception:
        return []


# ── Main Task Handler ───────────────────────────────────────────────────────

class FarmerRegistrationTask:
    """Handles the farmer registration / crop insurance application flow."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def fill_form(self, **pre_params) -> dict:
        """
        Navigate to farmer registration form via:
          Homepage → Farmer Corner card → Guest Farmer button → /farmerRegistrationForm

        Then fill fields using nth() index selectors (no id/name attributes on form).
        """
        logger.section("Farmer Registration — Crop Insurance Application")
        logger.info("Navigating: Homepage → Farmer Corner → Guest Farmer")

        page = self.browser.page

        # ── Navigate via Homepage Cards ──────────────────────────────────
        await self.browser.navigate("https://pmfby.gov.in/")
        await asyncio.sleep(3)

        # Click "Farmer Corner" (index 0 in service card row)
        try:
            farmer_corner = page.locator('[class*="ciListBtn"]').nth(0)
            await farmer_corner.wait_for(state="visible", timeout=8000)
            await farmer_corner.click()
            await asyncio.sleep(2)
            logger.success("Clicked 'Farmer Corner' card")
        except Exception as e:
            logger.warning(f"Could not click Farmer Corner card: {e}")
            await self.browser.vision_click(
                "text=Farmer Corner",
                "the 'Farmer Corner' service card or button on the homepage"
            )

        # Click "Guest Farmer" button in the resulting modal/dropdown
        try:
            await page.click("text=Guest Farmer", timeout=6000)
            await asyncio.sleep(3)
            logger.success("Clicked 'Guest Farmer'")
        except Exception:
            await self.browser.vision_click(
                "text=Guest Farmer",
                "the 'Guest Farmer' button inside the Farmer Corner popup or modal"
            )

        await asyncio.sleep(3)
        logger.info(f"Current URL: {page.url}")

        logger.info("Fill mode: Using nth() index selectors — per live exploration, "
                    "form has NO id/name attributes.\n")

        # ── Step 1: Scheme & Season Selection ─────────────────────────────
        logger.section("Step 1: Scheme, Season & Year")

        # State (index 0)
        state_opts = await _list_nth_select_options(page, 0)
        if state_opts:
            logger.info(f"States available ({len(state_opts)}): {', '.join(state_opts[:5])}...")
        state = pre_params.get("state") or prompt_user("Your State")
        if state:
            await self.browser.vision_select(0, state, "State dropdown (first select on page)")
            await _wait_for_options(page, 1)  # Wait for Scheme to load

        # Scheme (index 1)
        scheme_opts = await _list_nth_select_options(page, 1)
        if scheme_opts:
            logger.info(f"Schemes: {', '.join(scheme_opts)}")
        scheme = prompt_user("Scheme (e.g., PMFBY)", default=scheme_opts[0] if scheme_opts else "")
        if scheme:
            await self.browser.vision_select(1, scheme, "Scheme dropdown (second select)")
            await _wait_for_options(page, 2)

        # Season (index 2)
        season_opts = await _list_nth_select_options(page, 2)
        if season_opts:
            logger.info(f"Seasons: {', '.join(season_opts)}")
        season = pre_params.get("season") or prompt_user("Season (Kharif/Rabi/Zaid)")
        if season:
            await self.browser.vision_select(2, season, "Season dropdown (Kharif / Rabi / Zaid)")
            await asyncio.sleep(2)

        # Year (index 3)
        year_opts = await _list_nth_select_options(page, 3)
        if year_opts:
            logger.info(f"Years: {', '.join(year_opts[:5])}")
        year = pre_params.get("year") or prompt_user("Year", default="2025")
        if year:
            await self.browser.vision_select(3, year, "Year dropdown")
            await asyncio.sleep(2)

        # ── Step 2: Farmer Details ────────────────────────────────────────
        logger.section("Step 2: Farmer Details")

        full_name = prompt_user("Full Name of Farmer")
        if full_name:
            await _fill_nth_input(page, 4, full_name)

        passbook_name = prompt_user("Passbook Name (as in bank passbook)")
        if passbook_name:
            await _fill_nth_input(page, 5, passbook_name)

        # Relationship (index 6): S/O, D/O, W/O, C/O
        rel_opts = await _list_nth_select_options(page, 6)
        if rel_opts:
            logger.info(f"Relationship: {', '.join(rel_opts)}")
        relationship = prompt_user("Relationship (S/O / D/O / W/O / C/O)", default="S/O")
        if relationship:
            await _select_nth_by_label(page, 6, relationship)

        relative_name = prompt_user("Father / Husband Name")
        if relative_name:
            await _fill_nth_input(page, 7, relative_name)

        mobile = prompt_user("Mobile Number (10 digits)")
        if mobile:
            await _fill_nth_input(page, 8, mobile)

        age = prompt_user("Age")
        if age:
            await _fill_nth_input(page, 9, age)

        # Caste (index 10): GENERAL, OBC, SC, ST
        caste_opts = await _list_nth_select_options(page, 10)
        if caste_opts:
            logger.info(f"Caste options: {', '.join(caste_opts)}")
        caste = prompt_user("Caste Category", default="GENERAL")
        if caste:
            await self.browser.vision_select(10, caste, "Caste Category dropdown (GENERAL/OBC/SC/ST)")

        # Gender (index 11)
        gender_opts = await _list_nth_select_options(page, 11)
        if gender_opts:
            logger.info(f"Gender options: {', '.join(gender_opts)}")
        gender = prompt_user("Gender")
        if gender:
            await self.browser.vision_select(11, gender, "Gender dropdown (Male/Female/Others)")

        # Farmer Type (index 12)
        ftype_opts = await _list_nth_select_options(page, 12)
        if ftype_opts:
            logger.info(f"Farmer Types: {', '.join(ftype_opts)}")
        farmer_type = prompt_user("Farmer Type (Small/Marginal/Others)", default="Small")
        if farmer_type:
            await self.browser.vision_select(12, farmer_type, "Farmer Type dropdown")

        # Farmer Category (index 13)
        fcat_opts = await _list_nth_select_options(page, 13)
        if fcat_opts:
            logger.info(f"Farmer Categories: {', '.join(fcat_opts)}")
        farmer_cat = prompt_user("Farmer Category (Owner/Tenant/Share Cropper)", default="Owner")
        if farmer_cat:
            await self.browser.vision_select(13, farmer_cat, "Farmer Category dropdown (Owner/Tenant/Share Cropper)")

        # ── Step 3: Mobile OTP ────────────────────────────────────────────
        logger.section("Step 3: Mobile Verification (OTP)")
        try:
            verify_btn = page.locator("button:has-text('Verify')")
            if await verify_btn.count() > 0:
                await verify_btn.first.click()
                logger.warning("OTP sent to your mobile number.")
                await self.browser.handoff_to_user(
                    "Enter the OTP in the browser, then type 'continue' here."
                )
        except Exception as e:
            logger.warning(f"Verify button not found or click failed: {e}")
            await self.browser.handoff_to_user(
                "Please verify your mobile number in the browser, then type 'continue'."
            )

        # ── Step 4: Residential Details ───────────────────────────────────
        logger.section("Step 4: Residential  Details")

        res_state = prompt_user("Residential State", default=state or "")
        if res_state:
            await self.browser.vision_select(14, res_state, "Residential State dropdown")
            await _wait_for_options(page, 15)  # Wait for District

        res_district = prompt_user("District")
        if res_district:
            await self.browser.vision_select(15, res_district, "Residential District dropdown")
            await _wait_for_options(page, 16)  # Wait for Sub-District

        res_sub = prompt_user("Sub-District / Tehsil")
        if res_sub:
            await self.browser.vision_select(16, res_sub, "Sub-District or Tehsil dropdown")
            await _wait_for_options(page, 17)  # Wait for Village

        res_village = prompt_user("Village / Town")
        if res_village:
            await self.browser.vision_select(17, res_village, "Village or Town dropdown")

        address = prompt_user("Full Address")
        if address:
            await _fill_nth_input(page, 18, address)

        pincode = prompt_user("PIN Code")
        if pincode:
            await _fill_nth_input(page, 19, pincode)

        # ── Step 5: Farmer ID ─────────────────────────────────────────────
        logger.section("Step 5: Farmer ID (Aadhaar)")

        # ID Type (index 20) — usually pre-set to UID/Aadhaar
        id_num = prompt_user("Aadhaar Number (12 digits)")
        if id_num:
            await _fill_nth_input(page, 21, id_num)

        # ── Step 6: Bank Account Details ──────────────────────────────────
        logger.section("Step 6: Bank Account Details")

        bank_state = prompt_user("Bank State", default=state or "")
        if bank_state:
            await self.browser.vision_select(25, bank_state, "Bank State dropdown")
            await _wait_for_options(page, 26, timeout_ms=10000)

        bank_district = prompt_user("Bank District")
        if bank_district:
            await self.browser.vision_select(26, bank_district, "Bank District dropdown")
            await _wait_for_options(page, 27, timeout_ms=10000)

        bank_name = prompt_user("Bank Name")
        if bank_name:
            await self.browser.vision_select(27, bank_name, "Bank Name dropdown")
            await _wait_for_options(page, 28, timeout_ms=10000)

        branch = prompt_user("Bank Branch")
        if branch:
            await self.browser.vision_select(28, branch, "Bank Branch dropdown")

        acc_no = prompt_user("Bank Account Number")
        if acc_no:
            await _fill_nth_input(page, 29, acc_no)

        confirm_acc = prompt_user("Confirm Account Number")
        if confirm_acc:
            await _fill_nth_input(page, 30, confirm_acc)

        # ── Step 7: CAPTCHA ───────────────────────────────────────────────
        logger.section("Step 7: CAPTCHA")
        try:
            cap_visible = await page.is_visible("input[placeholder*='Captcha'], input[placeholder*='captcha']")
            if cap_visible:
                await self.browser.screenshot("captcha_farmer_reg")
                await self.browser.handoff_to_user(
                    "Please solve the CAPTCHA shown in the browser, then type 'continue'."
                )
        except Exception:
            pass

        # ── Step 8: Review & Submit ───────────────────────────────────────
        logger.section("Review & Submit")
        await self.browser.screenshot("form_filled_preview")
        logger.info("Screenshot saved — review the completed form in the browser.")

        if prompt_confirm("Submit the form?", default=False):
            try:
                submit = page.locator("button:has-text('Create User'), button[type='submit']").first
                await submit.click()
                await asyncio.sleep(5)
                await self.browser.screenshot("submission_result")
                logger.success("Form submitted. Check browser for confirmation.")
            except Exception as e:
                logger.error(f"Submit failed: {e}")
                await self.browser.handoff_to_user(
                    "Please submit the form manually, then type 'continue'."
                )
        else:
            logger.info("Submission cancelled.")

        body = await self.browser.get_text("body")
        return {
            "task": "farmer_registration",
            "status": "completed",
            "preview": body[:400] if body else "",
        }
