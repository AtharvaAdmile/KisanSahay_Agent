"""
Application Status task handler.
Revised based on live exploration — 2026-02-20.

KEY FINDINGS:
- Application Status is a MODAL on the homepage (NOT a separate page).
- Entry: Homepage → click service card[2] ('Application Status')
- Modal has 2 inputs: [0] Policy ID (no placeholder), [1] CAPTCHA (name='captcha')
- A CAPTCHA image is always shown — must use handoff_to_user.
- Submit button: button:has-text('Check Status')
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from playwright.async_api import Page

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import prompt_user


class ApplicationStatusTask:
    """Checks application status via PMFBY homepage modal."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def check_status(self, **pre_params) -> dict:
        """
        Open the 'Check Application Status' modal on the homepage,
        enter the Policy ID, hand off CAPTCHA to user, then extract result.
        """
        logger.section("Application Status Check")
        logger.info("Opening the Application Status modal on the homepage.\n")

        page = self.browser.page

        # ── Navigate and open modal ──────────────────────────────────────
        await self.browser.navigate("https://pmfby.gov.in/")
        await asyncio.sleep(3)

        logger.step("Clicking 'Application Status' service card (index 2)...")
        try:
            card = page.locator('[class*="ciListBtn"]').nth(2)
            await card.wait_for(state="visible", timeout=8000)
            await card.click()
            await asyncio.sleep(3)
            logger.success("Application Status modal opened")
        except Exception as e:
            logger.error(f"Could not open Application Status modal: {e}")
            return {"task": "check_status", "status": "failed", "error": str(e)}

        # Wait for modal to appear
        try:
            await page.wait_for_selector('.modal-dialog, [class*="InnerCalculator"]', timeout=8000)
        except Exception:
            logger.warning("Modal selector timeout — continuing")

        # ── Get receipt/policy number ────────────────────────────────────
        receipt_number = (
            pre_params.get("receipt_number")
            or pre_params.get("policy_id")
            or prompt_user("Enter Policy ID / Receipt Number")
        )
        if not receipt_number:
            logger.error("No Policy ID provided.")
            return {"task": "check_status", "status": "failed", "reason": "No Policy ID"}

        # ── Fill Policy ID (modal input index 0) ─────────────────────────
        logger.step(f"Entering Policy ID: {receipt_number}")
        try:
            # Policy ID input is the FIRST input inside the modal
            policy_input = page.locator('.modal-body input, [class*="InnerCalculator"] input').nth(0)
            await policy_input.wait_for(state="visible", timeout=8000)
            await policy_input.click()
            await policy_input.fill("")
            await policy_input.type(receipt_number, delay=60)
            logger.success(f"Entered Policy ID: {receipt_number}")
        except Exception as e:
            logger.warning(f"Could not fill Policy ID field: {e}")
            await self.browser.handoff_to_user(
                f"Please enter '{receipt_number}' in the Policy ID field, "
                "then type 'continue'."
            )

        # ── CAPTCHA — always requires user handoff ────────────────────────
        logger.warning("CAPTCHA is required for Application Status. Handing off to user.")
        await self.browser.screenshot("status_captcha")
        await self.browser.handoff_to_user(
            "Please solve the CAPTCHA displayed in the browser (a Security Code image), "
            "enter it in the CAPTCHA field, then type 'continue'."
        )

        # ── Click Check Status ────────────────────────────────────────────
        logger.step("Clicking 'Check Status' button...")
        try:
            check_btn = page.locator("button:has-text('Check Status')")
            await check_btn.wait_for(state="visible", timeout=6000)
            await check_btn.click()
            await asyncio.sleep(5)
            logger.success("Check Status submitted")
        except Exception as e:
            logger.warning(f"Check Status button error: {e}")
            await self.browser.handoff_to_user(
                "Please click 'Check Status' manually, then type 'continue'."
            )

        # ── Extract result ─────────────────────────────────────────────────
        await asyncio.sleep(3)
        result_text = ""
        result_selectors = [
            '.modal-body table',
            '[class*="InnerCalculator"] table',
            '.modal-body .result',
            '.modal-body',
        ]
        for sel in result_selectors:
            try:
                txt = await page.inner_text(sel)
                if txt and len(txt.strip()) > 20:
                    result_text = txt.strip()
                    break
            except Exception:
                continue

        if result_text:
            logger.section("Application Status Result")
            for line in result_text.split("\n")[:25]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning("Could not auto-extract result — check the browser window.")

        await self.browser.screenshot("application_status_result")

        return {
            "task": "check_status",
            "policy_id": receipt_number,
            "status": "completed",
            "result_preview": result_text[:500] if result_text else "See application_status_result.png",
        }
