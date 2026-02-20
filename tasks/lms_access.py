"""
LMS (Learning Management System) task handler.
Based on live exploration of https://pmfby.gov.in/lms/ — 2026-02-20.

KEY FINDINGS:
- Portal URL: https://pmfby.gov.in/lms/
- Nav: Home, About Us, Contact Us, Login, Register
- Registration: Mobile No, Password, Confirm Password + personal/location fields
- Login: Mobile No + Password + CAPTCHA (no OTP — fully password-based)
- Post-login: 16+ courses available, certificates downloadable
"""

import asyncio

from browser.controller import PMFBYBrowser
from utils import logger
from utils.helpers import prompt_user, prompt_confirm

LMS_URL = "https://pmfby.gov.in/lms/"


class LMSAccessTask:
    """Handles LMS registration, login, and course browsing."""

    def __init__(self, browser: PMFBYBrowser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    # ── Registration ─────────────────────────────────────────────────────────

    async def register(self, **pre_params) -> dict:
        """
        Register a new LMS account.
        Form: First Name, Last Name, Email (optional), Mobile No, Password,
              Confirm Password, State, District, Organization, Designation.
        No OTP — password-based only.
        """
        logger.section("LMS — New User Registration")
        page = self.browser.page

        await self.browser.navigate(LMS_URL)
        await asyncio.sleep(3)

        # Click "Register" in the top nav
        try:
            reg_btn = page.locator("a.nav-link:has-text('Register'), a:has-text('Register')")
            await reg_btn.first.wait_for(state="visible", timeout=8000)
            await reg_btn.first.click()
            await asyncio.sleep(3)
            logger.success("Opened Registration form")
        except Exception as e:
            logger.error(f"Could not open registration form: {e}")
            await self.browser.handoff_to_user(
                "Please click 'Register' in the top navigation of the LMS portal, "
                "then type 'continue'."
            )

        # Collect registration details
        first_name = pre_params.get("first_name") or prompt_user("First Name")
        last_name  = pre_params.get("last_name")  or prompt_user("Last Name")
        email      = pre_params.get("email")       or prompt_user("Email (optional, press Enter to skip)")
        mobile     = pre_params.get("lms_mobile") or pre_params.get("mobile") or prompt_user("Mobile Number")
        password   = pre_params.get("lms_password") or prompt_user("Password (min 8 chars)")
        state      = pre_params.get("state")       or prompt_user("State")
        district   = pre_params.get("district")    or prompt_user("District")

        # Fill fields (using text/placeholder selectors — LMS has proper HTML structure)
        fields = [
            ("input[placeholder*='First Name'], input[name='firstName']", first_name, "First Name"),
            ("input[placeholder*='Last Name'],  input[name='lastName']",  last_name,  "Last Name"),
            ("input[placeholder*='Email'],       input[name='email']",     email,      "Email"),
            ("input[placeholder*='Mobile'],      input[name='mobile']",    mobile,     "Mobile"),
            ("input[name='password'],            input[type='password']",  password,   "Password"),
        ]

        for selector, value, label in fields:
            if not value:
                continue
            try:
                await self.browser.vision_fill(
                    selector.split(",")[0].strip(), value,
                    f"the {label} input field in the LMS registration form"
                )
            except Exception as e:
                logger.warning(f"Could not fill {label}: {e}")

        # Confirm Password
        try:
            await self.browser.vision_fill(
                "input[name='confirmPassword'], input[placeholder*='Confirm']",
                password,
                "the Confirm Password field"
            )
        except Exception:
            pass

        # State dropdown
        if state:
            try:
                await self.browser.vision_click(
                    "select[name='state'], select[id*='state']",
                    "the State dropdown in the LMS registration form"
                )
                await asyncio.sleep(1)
                await self.browser.select_option(
                    "select[name='state'], select[id*='state']", label=state
                )
                await asyncio.sleep(2)
            except Exception as e:
                logger.warning(f"State selection failed: {e}")

        # District dropdown (loads after state)
        if district:
            try:
                await asyncio.sleep(2)
                await self.browser.select_option(
                    "select[name='district'], select[id*='district']", label=district
                )
            except Exception as e:
                logger.warning(f"District selection failed: {e}")

        await self.browser.screenshot("lms_registration_filled")
        logger.info("Screenshot saved — review details before submitting.")

        if prompt_confirm("Submit LMS registration?", default=False):
            try:
                submit = page.locator("button[type='submit']:has-text('Register'), button:has-text('Sign Up')")
                await submit.first.click()
                await asyncio.sleep(5)
                await self.browser.screenshot("lms_registration_result")
                logger.success("LMS registration form submitted!")
            except Exception as e:
                logger.error(f"Submit failed: {e}")
                await self.browser.handoff_to_user(
                    "Please submit the registration form manually, then type 'continue'."
                )
        else:
            logger.info("Registration cancelled.")

        body = await self.browser.get_text("body")
        return {
            "task": "lms_access",
            "action": "register",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": body[:400] if body else "See screenshot",
        }

    # ── Login ─────────────────────────────────────────────────────────────────

    async def login(self, **pre_params) -> dict:
        """
        Log in to LMS using Mobile No + Password + CAPTCHA.
        Auth: password-based (no mobile OTP).
        CAPTCHA: image-based — requires user handoff.
        """
        logger.section("LMS — Farmer Login")
        page = self.browser.page

        await self.browser.navigate(LMS_URL)
        await asyncio.sleep(3)

        # Click "Login" in nav
        try:
            login_btn = page.locator(".hightligh-link.nav-link, a.nav-link:has-text('Login')")
            await login_btn.first.wait_for(state="visible", timeout=8000)
            await login_btn.first.click()
            await asyncio.sleep(3)
            logger.success("Opened LMS Login form")
        except Exception as e:
            logger.error(f"Could not open Login form: {e}")
            await self.browser.handoff_to_user(
                "Please click 'Login' in the LMS portal navigation, then type 'continue'."
            )

        # Mobile number
        mobile = (
            pre_params.get("lms_mobile")
            or pre_params.get("mobile")
            or prompt_user("LMS Registered Mobile Number")
        )
        if mobile:
            await self.browser.vision_fill(
                "input[name='mobile'], input[placeholder*='Mobile']",
                mobile,
                "Mobile Number input in LMS login form"
            )

        # Password
        password = pre_params.get("lms_password") or prompt_user("LMS Password")
        if password:
            await self.browser.vision_fill(
                "input[name='password'], input[type='password']",
                password,
                "Password input in LMS login form"
            )

        # CAPTCHA — image-based, always requires handoff
        captcha_present = await self.browser.detect_captcha()
        if captcha_present:
            await self.browser.handle_captcha()
        else:
            # Fill captcha field manually if image was not auto-detected
            captcha_val = prompt_user("Enter the CAPTCHA code shown in the browser")
            if captcha_val:
                await self.browser.vision_fill(
                    "input[placeholder*='aptcha'], input[placeholder*='captcha']",
                    captcha_val,
                    "the CAPTCHA input field"
                )

        # Submit login
        try:
            submit = page.locator("button[type='submit']:has-text('Login'), button:has-text('Sign In')")
            await submit.first.click()
            await asyncio.sleep(5)
            logger.success("LMS login submitted")
        except Exception as e:
            logger.error(f"Login submit failed: {e}")
            await self.browser.handoff_to_user("Please click the Login button manually, then type 'continue'.")

        await self.browser.screenshot("lms_login_result")

        body = await self.browser.get_text("body")
        return {
            "task": "lms_access",
            "action": "login",
            "mobile": mobile or "",
            "status": "completed",
            "result_preview": body[:400] if body else "See lms_login_result.png",
        }

    # ── Browse Courses ────────────────────────────────────────────────────────

    async def browse_courses(self, **pre_params) -> dict:
        """
        After login, list available courses.
        Pre-condition: user must already be logged in.
        """
        logger.section("LMS — Available Courses")
        page = self.browser.page

        # Try to navigate to courses section
        try:
            courses_link = page.locator(
                "a:has-text('Courses'), a:has-text('My Courses'), a[href*='course']"
            )
            if await courses_link.count() > 0:
                await courses_link.first.click()
                await asyncio.sleep(3)
        except Exception:
            pass

        # Extract course titles
        course_titles = await self.browser.get_all_text(
            ".course-title, .card-title, h3, h4, [class*='course'] [class*='title']"
        )
        course_titles = [t.strip() for t in course_titles if t.strip() and len(t.strip()) > 5]

        if course_titles:
            logger.section("Available Courses")
            for i, title in enumerate(course_titles[:20], 1):
                logger.info(f"  {i}. {title}")
        else:
            logger.warning("Could not auto-extract course list — check the browser window.")

        await self.browser.screenshot("lms_courses")

        return {
            "task": "lms_access",
            "action": "browse_courses",
            "status": "completed",
            "courses": course_titles[:20],
        }
