"""
FarmerRegistrationTask — handles PM-KISAN new farmer registration and
editing / updating self-registration.

Live selectors (verified 2026-02-21 on pmkisan.gov.in):
  Aadhaar input:    #txtsrch
  Mobile input:     #ContentPlaceHolder1_txtMobileNo
  State dropdown:   #ContentPlaceHolder1_DropDownState
  CAPTCHA input:    #ContentPlaceHolder1_txtcaptcha
  Send OTP button:  #ContentPlaceHolder1_btnSendOTP

  Edit/Search page selectors (SearchSelfRegisterfarmerDetailsnewUpdated.aspx):
  Aadhaar input:    #txtsrch
  CAPTCHA input:    #ContentPlaceHolder1_txtcaptcha
  Search button:    #ContentPlaceHolder1_btnsrch
"""

import asyncio
from playwright.async_api import Page

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import prompt_user, prompt_confirm


class FarmerRegistrationTask:
    """Handles new farmer registration and self-registration editing."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def fill_form(self, **pre_params) -> dict:
        """
        New Farmer Registration at /RegistrationFormupdated.aspx.

        Flow:
          1. Fill Aadhaar (UIDAI verification step)
          2. Fill Mobile Number
          3. Select State
          4. Handoff: CAPTCHA + Get OTP (user completes manually)
          5. Handoff: OTP entry
          6. Fill detailed form (personal, bank, land)
          7. Confirm & submit
        """
        logger.section("PM-KISAN New Farmer Registration")
        page = self.browser.page

        # ── Step 1: Aadhaar ───────────────────────────────────────────────
        logger.step("Step 1: Enter Aadhaar Number")
        aadhaar = pre_params.get("aadhaar") or prompt_user(
            "Aadhaar Number (12 digits)", secret=True
        )
        await self.browser.vision_fill(
            "#txtsrch", aadhaar,
            "the Aadhaar number input field at the top of the registration page"
        )

        # ── Step 2: Mobile Number ─────────────────────────────────────────
        logger.step("Step 2: Enter Mobile Number")
        mobile = pre_params.get("mobile") or prompt_user("Mobile Number (10 digits)")
        await self.browser.vision_fill(
            "#ContentPlaceHolder1_txtMobileNo", mobile,
            "the Mobile Number input field"
        )

        # ── Step 3: Select State ──────────────────────────────────────────
        logger.step("Step 3: Select State")
        state = pre_params.get("state") or prompt_user(
            "State (e.g., Maharashtra, Rajasthan)"
        )
        try:
            await self.browser.select_option(
                "#ContentPlaceHolder1_DropDownState", label=state
            )
            logger.success(f"State selected: {state}")
        except Exception:
            logger.warning(f"Could not select state '{state}' via selector — trying vision")
            await self.browser.vision_select(
                0, state, "the State dropdown on the registration form"
            )

        # ── Step 4 & 5: CAPTCHA + OTP (full handoff) ──────────────────────
        logger.section("Step 4: CAPTCHA + OTP (Manual Action Required)")
        await self.browser.screenshot("registration_before_captcha")
        await self.browser.handoff_to_user(
            "Please complete these steps in the browser:\n"
            "  1. The CAPTCHA image is visible — solve it and type the code "
            "       in the CAPTCHA field\n"
            "  2. Click 'Get OTP' button\n"
            "  3. Enter the OTP received on your Aadhaar-linked mobile\n"
            "  4. Once the detailed form loads, type 'continue' here."
        )

        # ── Step 6: Detailed registration form ────────────────────────────
        logger.section("Step 5: Detailed Registration Form")
        await asyncio.sleep(3)

        # Attempt to fill what's pre-available
        full_name = pre_params.get("full_name") or pre_params.get("personal_full_name") or ""
        if full_name:
            try:
                name_input = page.locator("input[placeholder*='Name'], #ContentPlaceHolder1_txtFarmerName")
                if await name_input.count() > 0:
                    await name_input.first.fill(full_name)
                    await asyncio.sleep(1)
                    logger.success(f"Filled farmer name: {full_name}")
            except Exception as e:
                logger.warning(f"Could not fill farmer name: {e}")

        # Bank account details
        account_no = pre_params.get("account_no") or pre_params.get("bank_account_no") or ""
        ifsc = pre_params.get("ifsc") or pre_params.get("bank_ifsc") or ""

        if account_no:
            try:
                acc_input = page.locator(
                    "input[placeholder*='Account'], #ContentPlaceHolder1_txtaccno"
                )
                if await acc_input.count() > 0:
                    await acc_input.first.fill(account_no)
                    await asyncio.sleep(1)
                    logger.success(f"Filled account number: ****{account_no[-4:]}")
            except Exception as e:
                logger.warning(f"Could not fill account number: {e}")

        if ifsc:
            try:
                ifsc_input = page.locator(
                    "input[placeholder*='IFSC'], #ContentPlaceHolder1_txtifsc"
                )
                if await ifsc_input.count() > 0:
                    await ifsc_input.first.fill(ifsc)
                    await asyncio.sleep(1)
                    logger.success(f"Filled IFSC: {ifsc}")
            except Exception as e:
                logger.warning(f"Could not fill IFSC: {e}")

        # The remaining form fields vary by state/scheme — hand off
        await self.browser.screenshot("registration_form_filled")
        logger.warning(
            "Some form fields may need manual completion "
            "(address, land details, etc. vary by state)."
        )

        # ── Step 7: Confirm & submit ───────────────────────────────────────
        if prompt_confirm("Do you want the agent to submit the registration form?", default=False):
            await self.browser.handoff_to_user(
                "Please review all form fields, then click the Submit button. "
                "After submission, type 'continue'."
            )
        else:
            logger.info("Submission left to user — complete manually in the browser.")

        # Extract result
        await asyncio.sleep(3)
        result_text = await self.browser.get_text(
            "#ContentPlaceHolder1_lblResult, .alert, .alert-success, body"
        )
        await self.browser.screenshot("registration_result")

        return {
            "task": "register_pmkisan",
            "aadhaar_last4": aadhaar[-4:] if aadhaar else "",
            "mobile": mobile or "",
            "state": state or "",
            "status": "completed",
            "result_preview": result_text[:400] if result_text else "See registration_result.png",
        }

    async def edit_registration(self, **pre_params) -> dict:
        """
        Edit/Update PM-KISAN Self-Registration at
        /SearchSelfRegisterfarmerDetailsnewUpdated.aspx.

        Flow:
          1. Enter Aadhaar
          2. Handoff: CAPTCHA → Search
          3. Display found record for user review/edit
        """
        logger.section("PM-KISAN Edit Self-Registration")
        page = self.browser.page

        # Step 1: Aadhaar
        logger.step("Step 1: Enter Aadhaar for lookup")
        aadhaar = pre_params.get("aadhaar") or prompt_user(
            "Aadhaar Number (12 digits)", secret=True
        )
        await self.browser.vision_fill(
            "#txtsrch", aadhaar,
            "the Aadhaar number input field for self-registration edit search"
        )

        # Step 2: CAPTCHA + Search
        logger.section("Step 2: CAPTCHA + Search (Manual Action)")
        await self.browser.screenshot("edit_registration_captcha")
        await self.browser.handoff_to_user(
            "Please:\n"
            "  1. Solve the CAPTCHA in the browser\n"
            "  2. Enter the CAPTCHA code in the CAPTCHA field\n"
            "  3. Click 'Search' button\n"
            "  Then type 'continue' when the record appears."
        )

        # Step 3: Extract and display record
        await asyncio.sleep(3)
        result_text = await self.browser.get_text(
            "table, .farmer-details, .content, body"
        )
        await self.browser.screenshot("edit_registration_record")

        if result_text:
            logger.section("Farmer Record Found")
            for line in result_text.split("\n")[:20]:
                if line.strip():
                    logger.info(f"  {line.strip()[:100]}")
        else:
            logger.warning("Could not auto-extract record — check the browser window.")

        if prompt_confirm("Do you want to edit/update the record in the browser?", default=True):
            await self.browser.handoff_to_user(
                "Please make the required edits in the form, then submit. "
                "Type 'continue' when done."
            )

        return {
            "task": "edit_registration",
            "aadhaar_last4": aadhaar[-4:] if aadhaar else "",
            "status": "completed",
            "result_preview": result_text[:400] if result_text else "See edit_registration_record.png",
        }
