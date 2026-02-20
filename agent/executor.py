"""
Executor: runs step-by-step action plans using the browser controller
and task handlers. Dispatches actions to the appropriate handler.
"""

import asyncio

from browser.controller import PMFBYBrowser
from utils import logger


class Executor:
    """Runs action plans via browser automation and task handlers."""

    def __init__(self, browser: PMFBYBrowser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose
        self._handlers = {}  # lazy loaded
        self.results = {}

    def _get_handler(self, name: str):
        """Lazy-load task handlers to avoid circular imports."""
        if name not in self._handlers:
            if name == "farmer_registration":
                from tasks.farmer_registration import FarmerRegistrationTask
                self._handlers[name] = FarmerRegistrationTask(self.browser, self.verbose)
            elif name == "premium_calculator":
                from tasks.premium_calculator import PremiumCalculatorTask
                self._handlers[name] = PremiumCalculatorTask(self.browser, self.verbose)
            elif name == "application_status":
                from tasks.application_status import ApplicationStatusTask
                self._handlers[name] = ApplicationStatusTask(self.browser, self.verbose)
            elif name == "grievance":
                from tasks.grievance import GrievanceTask
                self._handlers[name] = GrievanceTask(self.browser, self.verbose)
            elif name == "site_explorer":
                from tasks.site_explorer import SiteExplorerTask
                self._handlers[name] = SiteExplorerTask(self.browser, self.verbose)
            else:
                raise ValueError(f"Unknown task handler: {name}")
        return self._handlers[name]

    async def execute(self, plan: list[dict]) -> dict:
        """Execute a full action plan step by step."""
        logger.section("Executing Plan")

        for i, step in enumerate(plan, 1):
            action = step.get("action")
            logger.step(f"Step {i}/{len(plan)}: {action}")

            try:
                if action == "navigate":
                    await self.browser.navigate(step["url"])

                elif action == "click":
                    await self.browser.click(step["selector"])

                elif action == "fill":
                    value = step.get("value", "")
                    # Replace template variables with results
                    for key, val in self.results.items():
                        value = value.replace(f"{{{key}}}", str(val))
                    await self.browser.fill(step["selector"], value)

                elif action == "task":
                    handler = self._get_handler(step["handler"])
                    method = getattr(handler, step["method"])
                    params = step.get("params", {})
                    result = await method(**params)
                    if result:
                        self.results.update(result)

                elif action == "extract_page_info":
                    info = await self.browser.get_page_info()
                    # Also extract headings and main content
                    headings = await self.browser.get_all_text("h1, h2, h3")
                    body_text = await self.browser.get_text("main, .content, article, body")

                    self.results["page_info"] = info
                    self.results["headings"] = headings

                    logger.success(f"Page: {info['title']}")
                    logger.info(f"URL: {info['url']}")
                    if headings:
                        logger.info("Sections found:")
                        for h in headings[:15]:
                            if h.strip():
                                logger.info(f"  • {h.strip()[:80]}")
                    if body_text:
                        # Show first 500 chars of body
                        preview = body_text[:500].replace("\n", " ").strip()
                        if preview:
                            logger.info(f"\nContent preview:\n{preview}...")

                elif action == "screenshot":
                    name = step.get("filename", "result")
                    path = await self.browser.screenshot(name)
                    self.results["screenshot"] = path

                elif action == "wait":
                    seconds = step.get("seconds", 3)
                    await asyncio.sleep(seconds)

                else:
                    logger.warning(f"Unknown action: {action}")

                logger.success(f"Step {i} complete")

            except Exception as e:
                logger.error(f"Step {i} failed: {e}")
                # Take error screenshot
                try:
                    await self.browser.screenshot(f"error_step_{i}")
                except Exception:
                    pass
                raise

        logger.section("Execution Complete")
        return self.results
