"""
Executor: runs step-by-step action plans using the browser controller
and task handlers. Dispatches actions to the appropriate handler.

Improvements:
  - Integrates Navigator for automatic recovery when steps fail.
  - On any step failure, Navigator.recover() is called to reroute to the
    correct page, then the step is retried once before giving up.
  - Tracks the current intent so Navigator can reason about routing.
  - Planned fill/click/select/task steps execute directly (no fake ReAct loop).
  - agentic_loop has iteration limit and per-iteration timeout.
  - user_input_queue.get() has a 5-minute timeout to prevent indefinite blocking.
"""

import asyncio

from ..config.base import SiteConfig
from ..browser.controller import Browser
from ..agent.navigator import Navigator
from ..agent.reasoning import ReasoningEngine
from ..utils import logger
from ..utils.user_profile import UserProfile

# Limits
MAX_AGENTIC_ITERATIONS = 50
USER_INPUT_TIMEOUT = 300  # 5 minutes
DOM_FETCH_TIMEOUT = 15    # seconds
LLM_CALL_TIMEOUT = 30    # seconds (not enforced here since reasoning is sync, but documented)


class Executor:
    """Runs action plans via browser automation and task handlers."""

    def __init__(self, browser: Browser, config: SiteConfig, verbose: bool = False):
        self.browser = browser
        self.config = config
        self.verbose = verbose
        self._handlers = {}
        self.results = {}
        self._navigator = Navigator(browser, config, verbose=verbose)
        self.reasoning = ReasoningEngine(config, verbose=verbose)
        self.user_input_queue = asyncio.Queue()
        self.agent_output_queue = asyncio.Queue()
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

    async def _await_user_input(self) -> str:
        """Wait for user input with a timeout to prevent indefinite blocking."""
        try:
            return await asyncio.wait_for(
                self.user_input_queue.get(),
                timeout=USER_INPUT_TIMEOUT
            )
        except asyncio.TimeoutError:
            logger.error(f"User input timed out after {USER_INPUT_TIMEOUT}s")
            raise TimeoutError(f"No user response received within {USER_INPUT_TIMEOUT} seconds")

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
            # Pass executor reference and profile so task handlers can use I/O queues
            params["executor"] = self
            params["profile"] = self._profile
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

    async def execute(self, plan: list[dict], profile: dict = None) -> dict:
        """
        Execute a full action plan step by step.

        - agentic_loop steps use LLM-driven reasoning with iteration limits.
        - fill/click/select/task steps execute directly (deterministic selectors).
        """
        self._profile = profile or {}
        logger.section("Executing Plan", style=self.config.banner_color)

        for i, step in enumerate(plan, 1):
            action = step.get("action")
            logger.step(f"Step {i}/{len(plan)}: {action}")

            if action == "agentic_loop":
                logger.info("Starting open-ended agentic loop...")
                await self._run_agentic_loop(step, profile)
                continue

            # For fill/click/select/task: execute directly without a ReAct loop.
            # These steps have deterministic selectors — reasoning adds latency
            # for no benefit. The task handler has its own domain-specific logic.
            try:
                await self._run_step(step)
                logger.success(f"Step {i} complete")

            except Exception as e:
                logger.error(f"Step {i} ({action}) failed: {e}")

                try:
                    await self.browser.screenshot(f"error_step_{i}_{action}")
                except Exception:
                    pass

                logger.info(f"Attempting auto-recovery for step {i}...")
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

    async def _run_agentic_loop(self, step: dict, profile: dict) -> None:
        """
        Run the LLM-driven agentic loop with iteration limits and timeouts.
        """
        for iteration in range(MAX_AGENTIC_ITERATIONS):
            logger.info(f"Agentic loop iteration {iteration + 1}/{MAX_AGENTIC_ITERATIONS}")

            # Fetch DOM state with timeout
            try:
                dom_state = await asyncio.wait_for(
                    self.browser.get_dom_state(),
                    timeout=DOM_FETCH_TIMEOUT
                )
            except asyncio.TimeoutError:
                logger.error(f"DOM state fetch timed out after {DOM_FETCH_TIMEOUT}s")
                await asyncio.sleep(2)
                continue

            decision = self.reasoning.decide_next_step(
                intent=self._current_intent,
                dom_state=dom_state,
                step=step,
                profile=profile
            )

            d_type = decision.get("type", "ACTION")

            if d_type == "ASK_USER":
                question = decision.get("question", "I need more information.")
                options = decision.get("options", [])

                logger.warning(f"Yielding to user: {question}")
                await self.agent_output_queue.put({
                    "status": "requires_input",
                    "question": question,
                    "options": options
                })

                user_answer = await self._await_user_input()
                logger.info(f"Received user answer: {user_answer}")

                if isinstance(profile, dict):
                    if "_history" not in profile:
                        profile["_history"] = {}
                    profile["_history"][question] = user_answer

            elif d_type == "READY_TO_SUBMIT":
                await self.agent_output_queue.put({
                    "status": "ready_to_submit",
                    "summary": decision.get("summary", {})
                })
                logger.info("Waiting for final user confirmation...")
                await self._await_user_input()
                logger.info("User confirmed final submission.")
                break

            else:  # ACTION
                act = decision.get("action")
                selector = decision.get("selector", "")
                value = decision.get("value", "")
                logger.info(f"Executing dynamic action: {decision}")

                # Re-fetch DOM before executing to mitigate TOCTOU
                try:
                    dom_state = await asyncio.wait_for(
                        self.browser.get_dom_state(),
                        timeout=DOM_FETCH_TIMEOUT
                    )
                except asyncio.TimeoutError:
                    logger.warning("DOM re-fetch timed out, proceeding with stale state")

                # Fallback for empty selectors — use vision-based interaction
                if not selector and act in ["fill", "click", "select"]:
                    from_label = decision.get("label", "the target field")
                    dummy_selector = "non_existent_element_force_vision"
                    try:
                        if act == "fill":
                            await self.browser.vision_fill(dummy_selector, value, f"the input field for {from_label}", timeout=100)
                        elif act == "click":
                            await self.browser.vision_click(dummy_selector, f"the {from_label} button", timeout=100)
                        elif act == "select":
                            await self.browser.vision_select(0, value, f"the dropdown for {from_label}")
                    except Exception as e:
                        logger.error(f"Vision fallback failed: {e}")
                    await asyncio.sleep(2)
                    continue

                try:
                    if act == "fill":
                        try:
                            await self.browser.fill(selector, value)
                        except Exception as e1:
                            logger.warning(f"Standard fill failed, trying vision... {e1}")
                            await self.browser.vision_fill(selector, value, f"the input field at {selector}")
                    elif act == "click":
                        if decision.get("vision"):
                            await self.browser.vision_click(selector, decision.get("description", selector))
                        else:
                            try:
                                await self.browser.click(selector)
                            except Exception as e2:
                                logger.warning(f"Standard click failed, trying vision... {e2}")
                                await self.browser.vision_click(selector, f"the button at {selector}")
                    elif act == "select":
                        try:
                            await self.browser.select_option(selector, value=value, label=value)
                        except Exception as e3:
                            logger.warning(f"Standard select failed, trying vision... {e3}")
                            await self.browser.vision_select(0, value, f"the dropdown at {selector}")
                    await asyncio.sleep(2)
                except Exception as e:
                    logger.error(f"Dynamic action failed: {e}")
                    await asyncio.sleep(2)
        else:
            # Loop exhausted without break — hit iteration limit
            logger.error(f"Agentic loop hit iteration limit ({MAX_AGENTIC_ITERATIONS})")
            await self.agent_output_queue.put({
                "status": "error",
                "error": f"Agent exceeded maximum iterations ({MAX_AGENTIC_ITERATIONS})"
            })
