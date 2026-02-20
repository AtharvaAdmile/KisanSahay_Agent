"""
Grievance / Crop Loss task handler.
Revised based on live exploration — 2026-02-20.

KEY FINDINGS:
- KRPH is a SEPARATE React SPA at https://pmfby.gov.in/krph/
- Navigation: Farmer Corner dropdown → "Crop Loss Intimation"
- Sign-in requires: Mobile Number (id='mobile-number') + CAPTCHA (name='txtCaptchaValForgotPass')
  → Send OTP (class='get-otpN') → OTP entry → actual form
- Always requires Mobile OTP — must use handoff_to_user after initiating OTP.
- The "Complaint Status" option is also available under Farmer Corner if user only wants to check.
"""

import asyncio
from playwright.async_api import Page

from browser.controller import PMFBYBrowser
from utils import logger
from utils.helpers import prompt_user, prompt_confirm


class GrievanceTask:
    """Handles crop loss intimation / grievance via the KRPH SPA portal."""

    KRPH_URL = "https://pmfby.gov.in/krph/"

    def __init__(self, browser: PMFBYBrowser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def file_grievance(self, **pre_params) -> dict:
        """
        Navigate to KRPH portal → Farmer Corner → Crop Loss Intimation.
        Sign in with mobile + OTP, then guide through the crop loss form.
        """
        logger.section("Grievance / Crop Loss Intimation — KRPH Portal")
        logger.info(f"Navigating to KRPH portal: {self.KRPH_URL}\n")

        page = self.browser.page

        # ── Step 1: Navigate to KRPH ─────────────────────────────────────
        await self.browser.navigate(self.KRPH_URL)
        await asyncio.sleep(5)  # KRPH is a separate server, needs extra time
        logger.info(f"Current URL: {page.url}")

        # ── Step 2: Open Farmer Corner dropdown ───────────────────────────
        logger.step("Opening 'Farmer Corner' menu in KRPH...")
        try:
            # The Farmer Corner button on KRPH is a MUI button — use text search
            farmer_corner = page.locator("button:has-text('Farmer Corner'), a:has-text('Farmer Corner')")
            await farmer_corner.first.wait_for(state="visible", timeout=10000)
            await farmer_corner.first.click()
            await asyncio.sleep(2)
            logger.success("Farmer Corner menu opened")
        except Exception as e:
            logger.error(f"Could not open Farmer Corner menu: {e}")
            await self.browser.handoff_to_user(
                "Please click 'Farmer Corner' in the top menu of the KRPH portal, "
                "then type 'continue'."
            )

        # ── Step 3: Click "Crop Loss Intimation" ──────────────────────────
        logger.step("Clicking 'Crop Loss Intimation'...")
        try:
            crop_loss_link = page.locator(
                "text=Crop Loss Intimation, "
                "[class*='dropdown'] a:has-text('Crop Loss'), "
                "li:has-text('Crop Loss') a"
            )
            await crop_loss_link.first.wait_for(state="visible", timeout=6000)
            await crop_loss_link.first.click()
            await asyncio.sleep(3)
            logger.success("Crop Loss Intimation selected")
        except Exception as e:
            logger.warning(f"Crop Loss Intimation click error: {e}")
            await self.browser.handoff_to_user(
                "Please click 'Crop Loss Intimation' in the Farmer Corner dropdown, "
                "then type 'continue'."
            )

        # ── Step 4: Mobile Number Sign-in ────────────────────────────────
        logger.section("Step 4: Mobile Sign-In (OTP Required)")
        logger.info("A mobile number + OTP is required to proceed with crop loss intimation.\n")

        mobile = pre_params.get("mobile") or prompt_user(
            "Your registered mobile number (10 digits)"
        )
        if mobile:
            try:
                mobile_input = page.locator("input#mobile-number")
                await mobile_input.wait_for(state="visible", timeout=8000)
                await mobile_input.fill("")
                await mobile_input.type(mobile, delay=60)
                logger.success(f"Entered mobile number: {mobile}")
            except Exception as e:
                logger.warning(f"Mobile input error: {e}")
                await self.browser.handoff_to_user(
                    f"Please enter your mobile number ({mobile}) in the input field, "
                    "then type 'continue'."
                )

        # ── CAPTCHA for OTP send ──────────────────────────────────────────
        logger.warning("CAPTCHA is required before sending OTP — handing off to user.")
        await self.browser.screenshot("krph_captcha")
        await self.browser.handoff_to_user(
            "Please:\n"
            "  1. Solve the CAPTCHA shown in the KRPH browser window\n"
            "  2. Enter the CAPTCHA code in the field\n"
            "  3. Click 'Send OTP'\n"
            "  4. Enter the OTP received on your mobile\n"
            "  5. Type 'continue' here when done."
        )

        # ── Step 5: After OTP — crop loss form appears ────────────────────
        logger.section("Step 5: Crop Loss Form")
        logger.info("After OTP verification, filling the crop loss form...\n")
        await asyncio.sleep(3)

        # Try to fill form fields if they're present (structure varies by state/scheme)
        # Policy number search
        try:
            policy_input = page.locator("input[placeholder*='Policy'], input[placeholder*='Application']").first
            if await policy_input.is_visible():
                policy = pre_params.get("policy_id") or prompt_user("Policy / Application Number")
                if policy:
                    await policy_input.fill(policy)
                    search_btn = page.locator("button:has-text('Search'), button:has-text('Fetch')")
                    if await search_btn.count() > 0:
                        await search_btn.first.click()
                        await asyncio.sleep(4)
        except Exception:
            pass

        # Loss details
        try:
            loss_date_input = page.locator(
                "input[type='date'], input[placeholder*='Date'], input[placeholder*='date']"
            ).first
            if await loss_date_input.is_visible():
                loss_date = prompt_user("Date of Crop Loss (YYYY-MM-DD)")
                if loss_date:
                    await loss_date_input.fill(loss_date)
        except Exception:
            pass

        # For remaining fields that vary dynamically, hand off to user
        logger.warning(
            "The crop loss form has dynamic fields that vary by policy/location. "
            "You may need to complete some fields manually."
        )
        screenshots = await self.browser.screenshot("crop_loss_form")

        if prompt_confirm("Do you want the agent to submit the form?", default=False):
            try:
                submit_btn = page.locator("button:has-text('Submit'), button[type='submit']").last
                await submit_btn.click()
                await asyncio.sleep(5)
                await self.browser.screenshot("crop_loss_submitted")
                logger.success("Crop loss form submitted!")
            except Exception as e:
                logger.error(f"Submit failed: {e}")
                await self.browser.handoff_to_user(
                    "Please submit the form manually, then type 'continue'."
                )
        else:
            logger.info("Submission cancelled by user.")

        body = await self.browser.get_text("body")
        return {
            "task": "grievance",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": body[:400] if body else "See screenshots",
        }

    async def check_complaint_status(self, **pre_params) -> dict:
        """
        Navigate to KRPH → Farmer Corner → Complaint Status.
        Authenticate via Mobile OTP, then extract and display complaint list.

        FINDING: Complaint Status requires the SAME mobile OTP flow as
        Crop Loss Intimation (not a reference-number lookup as might be expected).
        """
        logger.section("KRPH — Complaint Status Check")
        logger.info(f"Navigating to KRPH portal: {self.KRPH_URL}\n")

        page = self.browser.page
        await self.browser.navigate(self.KRPH_URL)
        await asyncio.sleep(5)

        # Open Farmer Corner dropdown
        logger.step("Opening 'Farmer Corner' menu in KRPH...")
        try:
            farmer_corner = page.locator(
                "button:has-text('Farmer Corner'), a:has-text('Farmer Corner')"
            )
            await farmer_corner.first.wait_for(state="visible", timeout=10000)
            await farmer_corner.first.click()
            await asyncio.sleep(2)
            logger.success("Farmer Corner menu opened")
        except Exception as e:
            logger.error(f"Could not open Farmer Corner menu: {e}")
            await self.browser.handoff_to_user(
                "Please click 'Farmer Corner' in the KRPH navigation menu, "
                "then type 'continue'."
            )

        # Click "Complaint Status"
        logger.step("Clicking 'Complaint Status'...")
        try:
            complaint_link = page.locator(
                "text=Complaint Status, "
                "[class*='dropdown'] a:has-text('Complaint'), "
                "li:has-text('Complaint Status') a"
            )
            await complaint_link.first.wait_for(state="visible", timeout=6000)
            await complaint_link.first.click()
            await asyncio.sleep(3)
            logger.success("Complaint Status selected")
        except Exception as e:
            logger.warning(f"Complaint Status click error: {e}")
            await self.browser.handoff_to_user(
                "Please click 'Complaint Status' in the Farmer Corner dropdown, "
                "then type 'continue'."
            )

        # Mobile OTP authentication (same flow as crop loss intimation)
        logger.section("Mobile OTP Authentication")
        mobile = pre_params.get("mobile") or prompt_user(
            "Your registered mobile number (10 digits)"
        )
        if mobile:
            await self.browser.handle_otp_flow(
                mobile=mobile,
                mobile_selector="input#mobile-number",
                captcha_input_selector="input[placeholder='Enter Captcha Code']",
                otp_btn_selector=".get-otpN",
            )

        # Extract complaint status list
        await asyncio.sleep(3)
        result_text = ""
        for sel in [
            "table",
            "[class*='complaint']",
            "[class*='status']",
            "main",
            "body",
        ]:
            try:
                txt = await page.inner_text(sel)
                if txt and len(txt.strip()) > 30:
                    result_text = txt.strip()
                    break
            except Exception:
                continue

        if result_text:
            logger.section("Complaint Status Results")
            for line in result_text.split("\n")[:25]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning("Could not auto-extract complaints — check the browser window.")

        await self.browser.screenshot("complaint_status_result")

        return {
            "task": "grievance",
            "action": "check_complaint_status",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": result_text[:600] if result_text else "See complaint_status_result.png",
        }
