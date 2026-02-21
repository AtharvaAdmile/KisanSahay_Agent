"""
StatusCheckTask — handles PM-KISAN status-related queries:
  - check_beneficiary_status: Know Your Status (Registration Number + OTP)
  - check_farmer_status:      Status of Self-Registered Farmer (Aadhaar)
  - know_registration_number: Find Registration Number (Mobile or Aadhaar)

Live selectors (verified 2026-02-21 on pmkisan.gov.in):

  BeneficiaryStatus_New.aspx:
    Registration No input:   #ContentPlaceHolder1_txtBox
    CAPTCHA input:           #ContentPlaceHolder1_txtcaptcha
    Get OTP button:          #ContentPlaceHolder1_btnsendotp
    Know Reg No link:        #ContentPlaceHolder1_knowReNo

  FarmerStatus.aspx:
    Aadhaar input:           #ContentPlaceHolder1_txtsrch
    CAPTCHA input:           #ContentPlaceHolder1_txtcaptcha
    Search button:           #ContentPlaceHolder1_btnsrch

  KnowYour_Registration.aspx:
    By Mobile radio:         #rdlselection_0
    By Aadhaar radio:        #rdlselection_1
    Input field:             #ContentPlaceHolder1_txtMobile
    CAPTCHA input:           #ContentPlaceHolder1_txtcaptcha_Front
    Get OTP button:          #ContentPlaceHolder1_btnMobileOtp
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from playwright.async_api import Page

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import prompt_user, prompt_confirm


class StatusCheckTask:
    """Handles all PM-KISAN status/lookup queries."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def check_beneficiary_status(self, **pre_params) -> dict:
        """
        Know Your Status at /BeneficiaryStatus_New.aspx.
        Requires Registration Number + CAPTCHA + OTP.
        """
        logger.section("PM-KISAN Beneficiary Status Check")
        page = self.browser.page

        # Registration number — or offer to look it up first
        registration_no = pre_params.get("registration_no") or ""
        if not registration_no:
            logger.info(
                "No registration number provided.\n"
                "Tip: Use 'know_registration_number' intent to find it first."
            )
            registration_no = prompt_user(
                "Enter your Registration Number (or press Enter to skip and use "
                "the 'Know Your Registration Number' link in the browser)"
            )

        if registration_no:
            # Fill registration number
            await self.browser.vision_fill(
                "#ContentPlaceHolder1_txtBox",
                registration_no,
                "the Registration Number input field"
            )

        # CAPTCHA + OTP handoff
        await self.browser.screenshot("beneficiary_status_captcha")
        await self.browser.handoff_to_user(
            "Please complete these steps:\n"
            "  1. Solve the CAPTCHA and enter it in the CAPTCHA field\n"
            "  2. Click 'Get OTP'\n"
            "  3. Enter the OTP received on your registered mobile\n"
            "  Then type 'continue' when the status is displayed."
        )

        # Extract result
        await asyncio.sleep(3)
        result_text = await self._extract_status_result()
        await self.browser.screenshot("beneficiary_status_result")

        if result_text:
            logger.section("Beneficiary Status")
            for line in result_text.split("\n")[:30]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning("Could not auto-extract status — check beneficiary_status_result.png")

        return {
            "task": "check_beneficiary_status",
            "registration_no": registration_no or "",
            "status": "completed",
            "result_preview": result_text[:600] if result_text else "See beneficiary_status_result.png",
        }

    async def check_farmer_status(self, **pre_params) -> dict:
        """
        Status of Self-Registered Farmer at /FarmerStatus.aspx.
        Requires Aadhaar + CAPTCHA (no OTP for this page).
        """
        logger.section("PM-KISAN Self-Registered Farmer Status")
        page = self.browser.page

        # Aadhaar
        aadhaar = pre_params.get("aadhaar") or prompt_user(
            "Aadhaar Number (12 digits)", secret=True
        )
        await self.browser.vision_fill(
            "#ContentPlaceHolder1_txtsrch",
            aadhaar,
            "the Aadhaar number input field for farmer status check"
        )

        # CAPTCHA + Search handoff
        await self.browser.screenshot("farmer_status_captcha")
        await self.browser.handoff_to_user(
            "Please:\n"
            "  1. Solve the CAPTCHA and enter the code in the CAPTCHA field\n"
            "  2. Click the 'Search' / 'Get Data' button\n"
            "  Then type 'continue' when the result is shown."
        )

        # Extract result
        await asyncio.sleep(3)
        result_text = await self._extract_status_result()
        await self.browser.screenshot("farmer_status_result")

        if result_text:
            logger.section("Farmer Status Result")
            for line in result_text.split("\n")[:30]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning("Could not auto-extract status — check farmer_status_result.png")

        return {
            "task": "check_farmer_status",
            "aadhaar_last4": aadhaar[-4:] if aadhaar else "",
            "status": "completed",
            "result_preview": result_text[:600] if result_text else "See farmer_status_result.png",
        }

    async def know_registration_number(self, **pre_params) -> dict:
        """
        Know Your Registration Number at /KnowYour_Registration.aspx.
        Searches by Mobile or Aadhaar + OTP.
        """
        logger.section("PM-KISAN — Know Your Registration Number")
        page = self.browser.page

        # Choose search mode
        mobile = pre_params.get("mobile") or ""
        aadhaar = pre_params.get("aadhaar") or ""
        by_mobile = bool(mobile) or not bool(aadhaar)

        if not mobile and not aadhaar:
            mode = prompt_user("Search by Mobile or Aadhaar? (mobile/aadhaar)", default="mobile")
            by_mobile = mode.strip().lower() != "aadhaar"
            if by_mobile:
                mobile = prompt_user("Mobile Number (10 digits)")
            else:
                aadhaar = prompt_user("Aadhaar Number (12 digits)", secret=True)

        # Select radio button
        radio_sel = "#rdlselection_0" if by_mobile else "#rdlselection_1"
        try:
            await self.browser.click(radio_sel)
            logger.success(f"Selected search mode: {'Mobile' if by_mobile else 'Aadhaar'}")
        except Exception:
            logger.warning("Could not click search mode radio — proceeding anyway")

        # Fill input
        input_value = mobile if by_mobile else aadhaar
        label = "mobile number" if by_mobile else "Aadhaar number"
        await self.browser.vision_fill(
            "#ContentPlaceHolder1_txtMobile",
            input_value,
            f"the {label} input field for registration number lookup"
        )

        # CAPTCHA + OTP handoff
        await self.browser.screenshot("know_reg_no_captcha")
        await self.browser.handoff_to_user(
            "Please:\n"
            "  1. Solve the CAPTCHA and enter the code in the CAPTCHA field\n"
            "  2. Click 'Get OTP'\n"
            "  3. Enter the OTP received on your registered mobile\n"
            "  Then type 'continue' when the Registration Number is shown."
        )

        # Extract registration number
        await asyncio.sleep(3)
        result_text = await self._extract_status_result()
        await self.browser.screenshot("know_reg_no_result")

        # Try to extract reg number specifically
        reg_no = ""
        if result_text:
            import re
            match = re.search(r"\b\d{10,13}\b", result_text)
            if match:
                reg_no = match.group()
                logger.success(f"Registration Number found: {reg_no}")

        if result_text:
            logger.section("Registration Number Result")
            for line in result_text.split("\n")[:20]:
                if line.strip():
                    logger.info(f"  {line.strip()}")

        return {
            "task": "know_registration_number",
            "mobile": mobile or "",
            "registration_no": reg_no,
            "status": "completed",
            "result_preview": result_text[:400] if result_text else "See know_reg_no_result.png",
        }

    async def _extract_status_result(self) -> str:
        """Try multiple selectors to extract status result text."""
        for sel in [
            "#ContentPlaceHolder1_pnlSuccess",
            ".alert-success",
            ".alert",
            "table",
            "#ContentPlaceHolder1_GridView1",
            ".content-main",
            "body",
        ]:
            try:
                text = await self.browser.get_text(sel, timeout=3000)
                if text and len(text.strip()) > 20:
                    return text.strip()
            except Exception:
                continue
        return ""
