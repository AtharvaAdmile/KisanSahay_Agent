"""
Executor: runs step-by-step action plans using the browser controller
and task handlers. Dispatches actions to the appropriate handler.

Improvements:
  - Integrates Navigator for automatic recovery when steps fail.
  - On any step failure, Navigator.recover() is called to reroute to the
    correct page, then the step is retried once before giving up.
  - Tracks the current intent so Navigator can reason about routing.
"""

import asyncio

from ..config.base import SiteConfig
from ..browser.controller import Browser
from ..agent.navigator import Navigator
from ..utils import logger
from ..utils.user_profile import UserProfile


class Executor:
    """Runs action plans via browser automation and task handlers."""

    def __init__(self, browser: Browser, config: SiteConfig, verbose: bool = False):
        self.browser = browser
        self.config = config
        self.verbose = verbose
        self._handlers = {}
        self.results = {}
        self._navigator = Navigator(browser, config, verbose=verbose)
        self._current_intent = "get_info"

    def set_intent(self, intent: str) -> None:
        """Inform the executor (and navigator) of the current intent."""
        self._current_intent = intent
        self._navigator.set_intent(intent)

    def _get_handler(self, name: str):
        """Lazy-load task handlers to avoid circular imports."""
        if name not in self._handlers:
            handler_config = self.config.task_handlers.get(name)
            if not handler_config:
                raise ValueError(f"Unknown task handler: {name}")

            module = __import__(
                handler_config.import_path,
                fromlist=[handler_config.class_name]
            )
            handler_class = getattr(module, handler_config.class_name)
            self._handlers[name] = handler_class(self.browser, self.verbose)
        return self._handlers[name]

    async def _run_step(self, step: dict) -> None:
        """Execute a single plan step. Called directly + on recovery retry."""
        action = step.get("action")

        if action == "navigate":
            await self.browser.navigate(step["url"])

        elif action == "dismiss_modal":
            await self.browser.dismiss_homepage_modal()

        elif action == "set_language":
            await self.browser.set_language(step.get("language", "English"))

        elif action == "setup_profile":
            from ..utils.user_profile import run_setup_wizard
            run_setup_wizard(
                profile_path=self.config.profile_path,
                sensitive_keys=self.config.sensitive_keys,
                keyring_service=self.config.keyring_service,
                site_name=self.config.site_name,
                include_crop_fields=self.config.site_id == "pmfby",
                include_portal_credentials=self.config.site_id == "pmfby",
            )
            self.results["profile_setup"] = "completed"

        elif action == "click":
            selector = step["selector"]
            if step.get("vision"):
                await self.browser.vision_click(
                    selector, step.get("description", selector)
                )
            else:
                await self.browser.click(selector)

        elif action == "fill":
            value = step.get("value", "")
            for key, val in self.results.items():
                value = value.replace(f"{{{key}}}", str(val))
            selector = step["selector"]
            if step.get("vision"):
                await self.browser.vision_fill(
                    selector, value, step.get("description", selector)
                )
            else:
                await self.browser.fill(selector, value)

        elif action == "task":
            handler = self._get_handler(step["handler"])
            method = getattr(handler, step["method"])
            params = step.get("params", {})
            result = await method(**params)
            if result:
                self.results.update(result)

        elif action == "extract_page_info":
            info = await self.browser.get_page_info()
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

    async def execute(self, plan: list[dict]) -> dict:
        """
        Execute a full action plan step by step.

        On failure, the Navigator attempts to reroute to the correct page
        for the current intent and retries the step once. If recovery also
        fails, the agent hands off to the user and re-raises.
        """
        logger.section("Executing Plan", style=self.config.banner_color)

        for i, step in enumerate(plan, 1):
            action = step.get("action")
            logger.step(f"Step {i}/{len(plan)}: {action}")

            try:
                await self._run_step(step)
                logger.success(f"Step {i} complete")

            except Exception as e:
                logger.error(f"Step {i} ({action}) failed: {e}")

                try:
                    await self.browser.screenshot(f"error_step_{i}_{action}")
                except Exception:
                    pass

                logger.info(f"⟳ Attempting auto-recovery for step {i}...")
                recovered = await self._navigator.recover(reason=str(e))

                if recovered:
                    logger.info(f"  Recovery succeeded — retrying step {i}")
                    try:
                        await self._run_step(step)
                        logger.success(f"Step {i} complete (after recovery)")
                        continue
                    except Exception as retry_err:
                        logger.error(f"  Retry also failed: {retry_err}")

                try:
                    await self.browser.handoff_to_user(
                        f"Step {i} ({action}) failed and auto-recovery didn't work.\n"
                        f"Error: {str(e)[:200]}\n\n"
                        f"Please check the browser window, navigate to the correct\n"
                        f"page manually if needed, then type 'continue' to resume."
                    )
                    await self._run_step(step)
                    logger.success(f"Step {i} complete (after user handoff)")
                except Exception as final_err:
                    logger.error(f"Step {i} permanently failed: {final_err}")
                    raise final_err

        logger.section("Execution Complete", style=self.config.banner_color)
        return self.results
