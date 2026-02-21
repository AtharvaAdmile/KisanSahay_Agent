"""
HelpdeskTask — handles PM-KISAN helpdesk/query operations.

Live selectors (verified 2026-02-21 on /Grievance.aspx):
  Register Query radio:     #ContentPlaceHolder1_rdbAll_0
  Know Status radio:        #ContentPlaceHolder1_rdbAll_1
  By Registration No radio: #ContentPlaceHolder1_rdbAction_0  (default)
  By Mobile radio:          #ContentPlaceHolder1_rdbAction_1
  Input field:              #ContentPlaceHolder1_txtBox
  CAPTCHA input:            #ContentPlaceHolder1_TextCapcha_Reg
  Get OTP button:           #ContentPlaceHolder1_ButtonSubmitmobile

IMPORTANT: All radio button IDs include the ContentPlaceHolder1_ prefix.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import prompt_user, prompt_confirm


class HelpdeskTask:
    """Registers and checks PM-KISAN helpdesk queries."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def raise_query(self, **pre_params) -> dict:
        """
        Register a helpdesk query at /Grievance.aspx.

        Flow:
          1. Select 'Register Query' radio
          2. Select search mode (Registration No or Mobile)
          3. Fill input, CAPTCHA handoff, Get OTP, OTP handoff
          4. Fill query details (category, description)
          5. Submit
        """
        logger.section("PM-KISAN Helpdesk — Register Query")
        page = self.browser.page

        # Step 1: Select 'Register Query' mode
        logger.step("Step 1: Selecting 'Register Query' mode")
        try:
            await self.browser.click("#ContentPlaceHolder1_rdbAll_0")
            logger.success("'Register Query' selected")
        except Exception:
            logger.warning("Could not click Register Query radio — proceeding")

        await asyncio.sleep(1)

        # Step 2: Input mode (Registration No or Mobile)
        registration_no = pre_params.get("registration_no") or ""
        mobile = pre_params.get("mobile") or ""

        if not registration_no and not mobile:
            mode = prompt_user(
                "Search by Registration Number or Mobile? (reg/mobile)", default="reg"
            )
            if mode.strip().lower() == "mobile":
                mobile = prompt_user("Mobile Number (10 digits)")
            else:
                registration_no = prompt_user("Registration Number")

        # Select appropriate radio
        if mobile and not registration_no:
            try:
                await self.browser.click("#ContentPlaceHolder1_rdbAction_1")
                logger.success("Mobile search mode selected")
            except Exception:
                pass

        input_value = registration_no or mobile
        await self.browser.vision_fill(
            "#ContentPlaceHolder1_txtBox",
            input_value,
            "the registration number or mobile number input field in the query form"
        )

        # Step 3: CAPTCHA + OTP handoff
        await self.browser.screenshot("helpdesk_captcha")
        await self.browser.handoff_to_user(
            "Please complete these steps:\n"
            "  1. Solve the CAPTCHA and enter it in the CAPTCHA field\n"
            "  2. Click 'Get OTP'\n"
            "  3. Enter the OTP on your registered mobile\n"
            "  Then type 'continue' when the query form is loaded."
        )

        # Step 4: Query details
        await asyncio.sleep(3)
        await self.browser.screenshot("helpdesk_query_form")
        logger.warning(
            "Query category and description fields vary. "
            "Please complete the query details in the browser."
        )

        # Step 5: Submit
        if prompt_confirm("Submit the query after you fill the details?", default=False):
            await self.browser.handoff_to_user(
                "Complete the query details, click Submit, then type 'continue'."
            )
        else:
            logger.info("Submission left to user.")

        result_text = await self.browser.get_text(
            ".alert, .alert-success, #ContentPlaceHolder1_lblResponse, body"
        )
        await self.browser.screenshot("helpdesk_result")

        return {
            "task": "raise_helpdesk",
            "registration_no": registration_no or "",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": result_text[:400] if result_text else "See helpdesk_result.png",
        }

    async def check_status(self, **pre_params) -> dict:
        """
        Check helpdesk query status at /Grievance.aspx.

        Flow:
          1. Select 'Know Status' radio
          2. Fill input (reg no or mobile), CAPTCHA handoff, OTP handoff
          3. Extract and display query status
        """
        logger.section("PM-KISAN Helpdesk — Check Query Status")
        page = self.browser.page

        # Step 1: 'Know Status' mode
        logger.step("Step 1: Selecting 'Know the Query Status' mode")
        try:
            await self.browser.click("#ContentPlaceHolder1_rdbAll_1")
            logger.success("'Know Status' selected")
        except Exception:
            logger.warning("Could not click Know Status radio")

        await asyncio.sleep(1)

        # Step 2: Input
        registration_no = pre_params.get("registration_no") or ""
        mobile = pre_params.get("mobile") or ""

        if not registration_no and not mobile:
            mode = prompt_user(
                "Search by Registration Number or Mobile? (reg/mobile)", default="reg"
            )
            if mode.strip().lower() == "mobile":
                mobile = prompt_user("Mobile Number (10 digits)")
                try:
                    await self.browser.click("#ContentPlaceHolder1_rdbAction_1")
                except Exception:
                    pass
            else:
                registration_no = prompt_user("Registration Number")

        input_value = registration_no or mobile
        await self.browser.vision_fill(
            "#ContentPlaceHolder1_txtBox",
            input_value,
            "the registration number or mobile field in the query status form"
        )

        # CAPTCHA + OTP handoff
        await self.browser.screenshot("query_status_captcha")
        await self.browser.handoff_to_user(
            "Please:\n"
            "  1. Solve the CAPTCHA and enter it\n"
            "  2. Click 'Get OTP'\n"
            "  3. Enter the OTP received on your mobile\n"
            "  Then type 'continue' when the query status is shown."
        )

        # Extract result
        await asyncio.sleep(3)
        result_text = ""
        for sel in [
            "table",
            "#ContentPlaceHolder1_GridView1",
            ".alert",
            ".alert-info",
            "body",
        ]:
            try:
                txt = await self.browser.get_text(sel, timeout=3000)
                if txt and len(txt.strip()) > 20:
                    result_text = txt.strip()
                    break
            except Exception:
                continue

        await self.browser.screenshot("query_status_result")

        if result_text:
            logger.section("Query Status Results")
            for line in result_text.split("\n")[:25]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning("Could not auto-extract query status — check query_status_result.png")

        return {
            "task": "check_query_status",
            "registration_no": registration_no or "",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": result_text[:600] if result_text else "See query_status_result.png",
        }
