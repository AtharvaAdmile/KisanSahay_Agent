"""
CROPIC (Collection of Real-time Observations and Photographs of Crops) task handler.
Based on live exploration of https://pmfby.gov.in/cropic/ — 2026-02-20.

KEY FINDINGS:
- Portal URL: https://pmfby.gov.in/cropic/
- Auth: Mobile Number + Password + CAPTCHA (id=':r2:', ':r3:', ':r4:')
- Submit: .first-btn
- Photo upload requires Policy ID / Aadhaar / Mobile linkage
- Status tracking: Reference ID-based, available post-login
"""

import asyncio

from browser.controller import PMFBYBrowser
from utils import logger
from utils.helpers import prompt_user, prompt_confirm

CROPIC_URL = "https://pmfby.gov.in/cropic/"


class CROPICAccessTask:
    """Handles CROPIC photo upload and status tracking."""

    def __init__(self, browser: PMFBYBrowser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self, **pre_params) -> dict:
        """
        Log in to CROPIC.
        Fields:
          Mobile  → id=':r2:' (React-generated dynamic id, use placeholder/type fallback)
          Password → id=':r3:'
          Captcha  → id=':r4:'
          Submit   → .first-btn
        Note: React dynamic ids may change; use placeholder/label selectors as fallback.
        """
        logger.section("CROPIC — Login")
        page = self.browser.page

        await self.browser.navigate(CROPIC_URL)
        await asyncio.sleep(5)

        # Mobile Number
        mobile = (
            pre_params.get("cropic_mobile")
            or pre_params.get("mobile")
            or prompt_user("CROPIC Registered Mobile Number")
        )
        if mobile:
            # Try dynamic React id first, then fallback to type/label
            await self.browser.vision_fill(
                "input[type='tel'], input[placeholder*='Mobile'], input[id=':r2:']",
                mobile,
                "the Mobile Number input in CROPIC login"
            )

        # Password
        password = pre_params.get("cropic_password") or prompt_user("CROPIC Password")
        if password:
            await self.browser.vision_fill(
                "input[type='password'], input[id=':r3:']",
                password,
                "the Password input in CROPIC login"
            )

        # CAPTCHA — image-based, handoff required
        await asyncio.sleep(2)
        if await self.browser.detect_captcha():
            await self.browser.handle_captcha()
        else:
            # CROPIC captcha may not be image-based — try to find text captcha
            captcha_val = prompt_user("Enter the CAPTCHA code shown in the CROPIC browser")
            if captcha_val:
                await self.browser.vision_fill(
                    "input[placeholder*='aptcha'], input[id=':r4:']",
                    captcha_val,
                    "the CAPTCHA input field in CROPIC"
                )

        # Submit login
        try:
            submit = page.locator(".first-btn, button[type='submit']:has-text('Login')")
            await submit.first.wait_for(state="visible", timeout=8000)
            await submit.first.click()
            await asyncio.sleep(5)
            logger.success("CROPIC login submitted")
        except Exception as e:
            logger.error(f"Login submit failed: {e}")
            await self.browser.handoff_to_user(
                "Please click the Login button in CROPIC manually, then type 'continue'."
            )

        await self.browser.screenshot("cropic_login_result")

        body = await self.browser.get_text("body")
        return {
            "task": "cropic_access",
            "action": "login",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": body[:400] if body else "See cropic_login_result.png",
        }

    # ── Photo Upload ──────────────────────────────────────────────────────────

    async def upload_photo(self, **pre_params) -> dict:
        """
        Upload crop photo(s) after logging in.
        Requires: Policy ID / Aadhaar / Mobile to link the photo to insurance record.
        Note: Actual file upload via file picker requires --no-headless mode.
        """
        logger.section("CROPIC — Crop Photo Upload")
        logger.info("Pre-requisite: must be logged in. Run login() first.\n")

        page = self.browser.page

        # Look for the Upload / Submit Photo section
        try:
            upload_link = page.locator(
                "a:has-text('Upload'), button:has-text('Upload Photo'), "
                "[class*='upload'], a:has-text('Submit')"
            )
            if await upload_link.count() > 0:
                await upload_link.first.click()
                await asyncio.sleep(3)
        except Exception:
            logger.warning("Could not auto-navigate to upload section — continuing")

        # Policy/Application linkage
        policy_id = (
            pre_params.get("policy_id")
            or pre_params.get("receipt_number")
            or prompt_user("Policy ID / Application Number for photo linkage")
        )
        if policy_id:
            await self.browser.vision_fill(
                "input[placeholder*='Policy'], input[placeholder*='Application'], "
                "input[placeholder*='policy']",
                policy_id,
                "the Policy ID or Application Number input"
            )
            # Search/Fetch button
            try:
                search_btn = page.locator(
                    "button:has-text('Search'), button:has-text('Fetch'), "
                    "button:has-text('Find')"
                )
                if await search_btn.count() > 0:
                    await search_btn.first.click()
                    await asyncio.sleep(4)
                    logger.success("Policy details fetched")
            except Exception:
                pass

        # File upload — requires headed mode
        logger.warning(
            "Photo file upload requires the browser in headed (visible) mode. "
            "Please use --no-headless and complete the file picker manually."
        )
        screenshot_path = await self.browser.screenshot("cropic_upload_form")
        await self.browser.handoff_to_user(
            "Please:\n"
            "  1. Select the photo file(s) using the file picker shown\n"
            "  2. Fill any remaining location/description fields\n"
            "  3. Click Submit/Upload\n"
            "  Then type 'continue'."
        )

        await self.browser.screenshot("cropic_upload_result")

        body = await self.browser.get_text("body")
        return {
            "task": "cropic_access",
            "action": "upload_photo",
            "policy_id": policy_id or "",
            "status": "completed",
            "result_preview": body[:400] if body else "See cropic_upload_result.png",
        }

    # ── Track Status ──────────────────────────────────────────────────────────

    async def track_status(self, **pre_params) -> dict:
        """
        Track crop photo submission status post-login.
        Uses Reference ID or Policy ID to look up assessment status.
        """
        logger.section("CROPIC — Photo Submission Status")
        logger.info("Pre-requisite: must be logged in. Run login() first.\n")

        page = self.browser.page

        # Navigate to status section
        try:
            status_link = page.locator(
                "a:has-text('Status'), a:has-text('Track'), "
                "button:has-text('Check Status'), [class*='status']"
            )
            if await status_link.count() > 0:
                await status_link.first.click()
                await asyncio.sleep(3)
        except Exception:
            pass

        # Reference / Policy ID
        ref_id = (
            pre_params.get("reference_id")
            or pre_params.get("policy_id")
            or prompt_user("Enter Reference ID or Policy ID to track")
        )
        if ref_id:
            await self.browser.vision_fill(
                "input[placeholder*='Reference'], input[placeholder*='Policy']",
                ref_id,
                "the Reference ID or Policy ID input field"
            )
            try:
                search_btn = page.locator("button:has-text('Search'), button:has-text('Track')")
                if await search_btn.count() > 0:
                    await search_btn.first.click()
                    await asyncio.sleep(4)
            except Exception:
                pass

        # Extract result
        result_text = ""
        for sel in ["table", "[class*='result']", "[class*='status']", "main"]:
            try:
                txt = await page.inner_text(sel)
                if txt and len(txt.strip()) > 20:
                    result_text = txt.strip()
                    break
            except Exception:
                continue

        if result_text:
            logger.section("Photo Submission Status")
            for line in result_text.split("\n")[:20]:
                if line.strip():
                    logger.info(f"  {line.strip()}")
        else:
            logger.warning("Could not auto-extract status — check the browser window.")

        await self.browser.screenshot("cropic_status_result")

        return {
            "task": "cropic_access",
            "action": "track_status",
            "reference_id": ref_id or "",
            "status": "completed",
            "result_preview": result_text[:600] if result_text else "See cropic_status_result.png",
        }
