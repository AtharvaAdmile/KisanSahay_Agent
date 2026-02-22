"""
Farmer Registration (Crop Insurance Application) task handler.
Revised based on live exploration of pmfby.gov.in on 2026-02-20.

KEY FINDING: All form elements on the registration form lack 'id' and 'name'
attributes. Selectors MUST use nth() index-based addressing.
The form lives at /farmerRegistrationForm after clicking:
  Homepage → "Farmer Corner" card (index 0) → "Guest Farmer" button

API COMPATIBLE: Uses queue-based I/O instead of CLI stdin. Each field is
checked against the profile first; if missing, an ASK_USER message is
yielded to the executor's output queue and the handler awaits the answer
from the input queue.
"""

import asyncio
from playwright.async_api import Page

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.browser.controller import Browser
from shared.utils import logger


# ── Helpers ────────────────────────────────────────────────────────────────

USER_INPUT_TIMEOUT = 300  # 5 minutes max wait for user answer


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


# ── Queue-based I/O ────────────────────────────────────────────────────────

async def _ask_user(output_queue: asyncio.Queue, input_queue: asyncio.Queue,
                    question: str, options: list = None) -> str:
    """
    Yield an ASK_USER message to the output queue and wait for the user's
    answer from the input queue. Used as a drop-in replacement for prompt_user().
    """
    msg = {
        "status": "requires_input",
        "question": question,
        "options": options or []
    }
    await output_queue.put(msg)
    logger.info(f"Asking user: {question}")

    try:
        answer = await asyncio.wait_for(input_queue.get(), timeout=USER_INPUT_TIMEOUT)
    except asyncio.TimeoutError:
        logger.error(f"User input timed out for: {question}")
        raise TimeoutError(f"No user response within {USER_INPUT_TIMEOUT}s for: {question}")

    logger.info(f"User answered: {answer}")
    return str(answer).strip()


async def _ask_confirm(output_queue: asyncio.Queue, input_queue: asyncio.Queue,
                       question: str) -> bool:
    """
    Yield a yes/no confirmation question and return True if the user confirms.
    """
    answer = await _ask_user(output_queue, input_queue, question, options=["Yes", "No"])
    return answer.lower() in ("yes", "y", "true", "1")


def _get_profile_value(profile: dict, *keys) -> str:
    """
    Look up a value from the profile dict, trying multiple key names.
    Returns the first non-empty match, or empty string.
    """
    for key in keys:
        val = profile.get(key, "")
        if val:
            return str(val)
    return ""


# ── Main Task Handler ───────────────────────────────────────────────────────

class FarmerRegistrationTask:
    """Handles the farmer registration / crop insurance application flow."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def fill_form(self, executor=None, profile: dict = None, **pre_params) -> dict:
        """
        Navigate to farmer registration form via:
          Homepage → Farmer Corner card → Guest Farmer button → /farmerRegistrationForm

        Then fill fields using nth() index selectors (no id/name attributes on form).

        Args:
            executor: The Executor instance (provides user_input_queue and agent_output_queue)
            profile: Dict of farmer profile data to auto-fill from
            **pre_params: Additional pre-filled parameters
        """
        # Set up I/O queues — either from executor or create standalone (for testing)
        if executor:
            output_q = executor.agent_output_queue
            input_q = executor.user_input_queue
        else:
            output_q = asyncio.Queue()
            input_q = asyncio.Queue()

        if profile is None:
            profile = {}

        # Merge pre_params into profile (pre_params take precedence)
        merged = {**profile, **pre_params}

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

        # ── Helper: get value from profile or ask user ───────────────────
        async def _get_or_ask(question: str, *profile_keys, options: list = None, default: str = "") -> str:
            """Check profile for value, ask user if missing."""
            value = _get_profile_value(merged, *profile_keys)
            if value:
                logger.info(f"  Auto-filling from profile: {question} = {value[:30]}")
                return value
            if default:
                # Ask with default hint
                full_q = f"{question} (default: {default})"
            else:
                full_q = question
            answer = await _ask_user(output_q, input_q, full_q, options=options)
            return answer or default

        # ── Step 1: Scheme & Season Selection ─────────────────────────────
        logger.section("Step 1: Scheme, Season & Year")

        # State (index 0)
        state_opts = await _list_nth_select_options(page, 0)
        if state_opts:
            logger.info(f"States available ({len(state_opts)}): {', '.join(state_opts[:5])}...")
        state = await _get_or_ask("Your State", "state", options=state_opts[:20] if state_opts else None)
        if state:
            await self.browser.vision_select(0, state, "State dropdown (first select on page)")
            await _wait_for_options(page, 1)  # Wait for Scheme to load

        # Scheme (index 1)
        scheme_opts = await _list_nth_select_options(page, 1)
        if scheme_opts:
            logger.info(f"Schemes: {', '.join(scheme_opts)}")
        scheme = await _get_or_ask(
            "Scheme (e.g., PMFBY)", "scheme",
            options=scheme_opts if scheme_opts else None,
            default=scheme_opts[0] if scheme_opts else ""
        )
        if scheme:
            await self.browser.vision_select(1, scheme, "Scheme dropdown (second select)")
            await _wait_for_options(page, 2)

        # Season (index 2)
        season_opts = await _list_nth_select_options(page, 2)
        if season_opts:
            logger.info(f"Seasons: {', '.join(season_opts)}")
        season = await _get_or_ask("Season (Kharif/Rabi/Zaid)", "season", options=season_opts if season_opts else None)
        if season:
            await self.browser.vision_select(2, season, "Season dropdown (Kharif / Rabi / Zaid)")
            await asyncio.sleep(2)

        # Year (index 3)
        year_opts = await _list_nth_select_options(page, 3)
        if year_opts:
            logger.info(f"Years: {', '.join(year_opts[:5])}")
        year = await _get_or_ask("Year", "crop_year", "year", options=year_opts[:5] if year_opts else None, default="2025")
        if year:
            await self.browser.vision_select(3, year, "Year dropdown")
            await asyncio.sleep(2)

        # ── Step 2: Farmer Details ────────────────────────────────────────
        logger.section("Step 2: Farmer Details")

        full_name = await _get_or_ask("Full Name of Farmer", "full_name", "name")
        if full_name:
            await _fill_nth_input(page, 4, full_name)

        passbook_name = await _get_or_ask("Passbook Name (as in bank passbook)", "passbook_name")
        if not passbook_name and full_name:
            passbook_name = full_name  # Sensible default
            logger.info(f"  Using full name as passbook name: {passbook_name}")
        if passbook_name:
            await _fill_nth_input(page, 5, passbook_name)

        # Relationship (index 6): S/O, D/O, W/O, C/O
        rel_opts = await _list_nth_select_options(page, 6)
        if rel_opts:
            logger.info(f"Relationship: {', '.join(rel_opts)}")
        relationship = await _get_or_ask(
            "Relationship (S/O / D/O / W/O / C/O)", "relationship",
            options=rel_opts if rel_opts else None, default="S/O"
        )
        if relationship:
            await _select_nth_by_label(page, 6, relationship)

        relative_name = await _get_or_ask("Father / Husband Name", "relative_name")
        if relative_name:
            await _fill_nth_input(page, 7, relative_name)

        mobile = await _get_or_ask("Mobile Number (10 digits)", "mobile")
        if mobile:
            await _fill_nth_input(page, 8, mobile)

        age = await _get_or_ask("Age", "age")
        if age:
            await _fill_nth_input(page, 9, age)

        # Caste (index 10): GENERAL, OBC, SC, ST
        caste_opts = await _list_nth_select_options(page, 10)
        if caste_opts:
            logger.info(f"Caste options: {', '.join(caste_opts)}")
        caste = await _get_or_ask(
            "Caste Category", "caste", "category",
            options=caste_opts if caste_opts else None, default="GENERAL"
        )
        if caste:
            await self.browser.vision_select(10, caste, "Caste Category dropdown (GENERAL/OBC/SC/ST)")

        # Gender (index 11)
        gender_opts = await _list_nth_select_options(page, 11)
        if gender_opts:
            logger.info(f"Gender options: {', '.join(gender_opts)}")
        gender = await _get_or_ask(
            "Gender", "gender",
            options=gender_opts if gender_opts else None
        )
        if gender:
            await self.browser.vision_select(11, gender, "Gender dropdown (Male/Female/Others)")

        # Farmer Type (index 12)
        ftype_opts = await _list_nth_select_options(page, 12)
        if ftype_opts:
            logger.info(f"Farmer Types: {', '.join(ftype_opts)}")
        farmer_type = await _get_or_ask(
            "Farmer Type (Small/Marginal/Others)", "farmer_type",
            options=ftype_opts if ftype_opts else None, default="Small"
        )
        if farmer_type:
            await self.browser.vision_select(12, farmer_type, "Farmer Type dropdown")

        # Farmer Category (index 13)
        fcat_opts = await _list_nth_select_options(page, 13)
        if fcat_opts:
            logger.info(f"Farmer Categories: {', '.join(fcat_opts)}")
        farmer_cat = await _get_or_ask(
            "Farmer Category (Owner/Tenant/Share Cropper)", "farmer_category",
            options=fcat_opts if fcat_opts else None, default="Owner"
        )
        if farmer_cat:
            await self.browser.vision_select(13, farmer_cat, "Farmer Category dropdown (Owner/Tenant/Share Cropper)")

        # ── Step 3: Mobile OTP ────────────────────────────────────────────
        logger.section("Step 3: Mobile Verification (OTP)")
        try:
            verify_btn = page.locator("button:has-text('Verify')")
            if await verify_btn.count() > 0:
                await verify_btn.first.click()
                logger.warning("OTP sent to your mobile number.")
                otp = await _ask_user(
                    output_q, input_q,
                    "An OTP has been sent to your mobile number. Please enter the OTP."
                )
                if otp:
                    # Try to find and fill the OTP input field
                    try:
                        otp_input = page.locator("input[placeholder*='OTP'], input[placeholder*='otp']")
                        if await otp_input.count() > 0:
                            await otp_input.first.fill(otp)
                            await asyncio.sleep(2)
                    except Exception:
                        logger.warning("Could not auto-fill OTP, user may need to enter manually")
        except Exception as e:
            logger.warning(f"Verify button not found or click failed: {e}")
            await _ask_user(
                output_q, input_q,
                "Please verify your mobile number in the browser manually, then send 'continue'."
            )

        # ── Step 4: Residential Details ───────────────────────────────────
        logger.section("Step 4: Residential Details")

        res_state = await _get_or_ask("Residential State", "state", default=state or "")
        if res_state:
            await self.browser.vision_select(14, res_state, "Residential State dropdown")
            await _wait_for_options(page, 15)  # Wait for District

        res_district = await _get_or_ask("District", "district")
        if res_district:
            await self.browser.vision_select(15, res_district, "Residential District dropdown")
            await _wait_for_options(page, 16)  # Wait for Sub-District

        res_sub = await _get_or_ask("Sub-District / Tehsil", "taluka", "sub_district")
        if res_sub:
            await self.browser.vision_select(16, res_sub, "Sub-District or Tehsil dropdown")
            await _wait_for_options(page, 17)  # Wait for Village

        res_village = await _get_or_ask("Village / Town", "village")
        if res_village:
            await self.browser.vision_select(17, res_village, "Village or Town dropdown")

        address = await _get_or_ask("Full Address", "address")
        if address:
            await _fill_nth_input(page, 18, address)

        pincode = await _get_or_ask("PIN Code", "pincode")
        if pincode:
            await _fill_nth_input(page, 19, pincode)

        # ── Step 5: Farmer ID ─────────────────────────────────────────────
        logger.section("Step 5: Farmer ID (Aadhaar)")

        # ID Type (index 20) — usually pre-set to UID/Aadhaar
        id_num = await _get_or_ask("Aadhaar Number (12 digits)", "aadhaar", "aadhaarNumber")
        if id_num:
            await _fill_nth_input(page, 21, id_num)

        # ── Step 6: Bank Account Details ──────────────────────────────────
        logger.section("Step 6: Bank Account Details")

        bank_state = await _get_or_ask("Bank State", "bank_state", default=state or "")
        if bank_state:
            await self.browser.vision_select(25, bank_state, "Bank State dropdown")
            await _wait_for_options(page, 26, timeout_ms=10000)

        bank_district = await _get_or_ask("Bank District", "bank_district")
        if bank_district:
            await self.browser.vision_select(26, bank_district, "Bank District dropdown")
            await _wait_for_options(page, 27, timeout_ms=10000)

        bank_name = await _get_or_ask("Bank Name", "bank_name")
        if bank_name:
            await self.browser.vision_select(27, bank_name, "Bank Name dropdown")
            await _wait_for_options(page, 28, timeout_ms=10000)

        branch = await _get_or_ask("Bank Branch", "bank_branch")
        if branch:
            await self.browser.vision_select(28, branch, "Bank Branch dropdown")

        acc_no = await _get_or_ask("Bank Account Number", "account_no")
        if acc_no:
            await _fill_nth_input(page, 29, acc_no)
            # Auto-fill confirm field with same value
            await _fill_nth_input(page, 30, acc_no)

        # ── Step 7: CAPTCHA ───────────────────────────────────────────────
        logger.section("Step 7: CAPTCHA")
        try:
            cap_visible = await page.is_visible("input[placeholder*='Captcha'], input[placeholder*='captcha']")
            if cap_visible:
                await self.browser.screenshot("captcha_farmer_reg")
                captcha = await _ask_user(
                    output_q, input_q,
                    "Please enter the CAPTCHA shown in the form."
                )
                if captcha:
                    try:
                        captcha_input = page.locator("input[placeholder*='Captcha'], input[placeholder*='captcha']")
                        if await captcha_input.count() > 0:
                            await captcha_input.first.fill(captcha)
                    except Exception:
                        logger.warning("Could not auto-fill CAPTCHA")
        except Exception:
            pass

        # ── Step 8: Review & Submit ───────────────────────────────────────
        logger.section("Review & Submit")
        await self.browser.screenshot("form_filled_preview")
        logger.info("Screenshot saved — review the completed form.")

        # Yield ready_to_submit with a summary so the user can confirm
        summary = {
            "name": full_name, "mobile": mobile, "age": age,
            "state": state, "district": res_district,
            "season": season, "year": year,
        }
        await output_q.put({
            "status": "ready_to_submit",
            "summary": {k: v for k, v in summary.items() if v}
        })

        confirm_answer = await _ask_user(output_q, input_q, "Submit the form? (Yes/No)", options=["Yes", "No"])
        if confirm_answer.lower() in ("yes", "y", "true", "1"):
            try:
                submit = page.locator("button:has-text('Create User'), button[type='submit']").first
                await submit.click()
                await asyncio.sleep(5)
                await self.browser.screenshot("submission_result")
                logger.success("Form submitted. Check browser for confirmation.")
            except Exception as e:
                logger.error(f"Submit failed: {e}")
                await _ask_user(
                    output_q, input_q,
                    "Form submission failed. Please submit manually in the browser, then send 'continue'."
                )
        else:
            logger.info("Submission cancelled by user.")

        body = await self.browser.get_text("body")
        return {
            "task": "farmer_registration",
            "status": "completed",
            "preview": body[:400] if body else "",
        }
