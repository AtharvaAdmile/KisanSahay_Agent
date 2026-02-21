"""
Reasoning Engine — The core ReAct loop component for the PMFBY Agent.
Evaluates the current DOM state, the user's intent, and the active profile,
then decides the next action: ACTION, ASK_USER, or READY_TO_SUBMIT.
"""

import json
import os
import sys

from openai import OpenAI
from dotenv import load_dotenv

from ..config.base import SiteConfig
from ..utils import logger

load_dotenv()


class ReasoningEngine:
    """Evaluates DOM state and decides the next action."""

    def __init__(self, config: SiteConfig, verbose: bool = False):
        self.config = config
        api_key = (os.getenv("LLM_API_KEY") or "").strip()
        base_url = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").strip()
        self.model_id = (os.getenv("LLM_MODEL_ID") or "gpt-4o-mini").strip()
        self.verbose = verbose

        if not api_key:
            logger.error(
                "LLM_API_KEY not set in .env file.\n"
                "ReasoningEngine requires an LLM."
            )
            sys.exit(1)

        try:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            logger.debug(f"Reasoning LLM ready: {self.model_id} at {base_url}", verbose)
        except Exception as e:
            logger.error(f"Could not initialise Reasoning LLM client: {e}")
            sys.exit(1)

    def _build_system_prompt(self, intent: str, profile: dict, step: dict) -> str:
        return f"""You are an expert PMFBY Registration Assistant.
Your goal is to complete the user's intent: {intent}.
You are currently evaluating the following planned step:
{json.dumps(step, indent=2)}

You have access to the following user profile data:
{json.dumps(profile, indent=2)}

You will receive the current DOM state of the form representing interactable elements.
Your task is to analyze the DOM state, the profile, and the planned step, then decide what to do next.

You MUST respond with a JSON object in one of three formats:

1. ACTION
If you have the data needed to fill a field, click a button, or select an option:
{{
    "type": "ACTION",
    "action": "fill",  // "fill", "click", "select"
    "selector": "CSS selector from the DOM state",
    "value": "Value to fill or select"
}}

2. ASK_USER
If you are missing data for a REQUIRED field that is currently visible in the DOM, 
or if there is a CAPTCHA or OTP challenge:
{{
    "type": "ASK_USER",
    "question": "Clear question asking the user for this specific data",
    "options": ["Option 1", "Option 2"] // Include if asking about a dropdown
}}

3. READY_TO_SUBMIT
If the form is completely filled and the only remaining action is the final Submit button:
{{
    "type": "READY_TO_SUBMIT",
    "summary": {{"Field 1": "Value", "Field 2": "Value"}}
}}

Important Instructions:
- Form fields often unlock in a cascading manner (e.g. State -> District -> Sub-District). Only ask for or fill fields that are currently visible and active in the DOM.
- For dropdowns (`<select>`), prefer checking if the profile matches any of the available options. Don't guess the option value; use the exact value from the DOM options.
- If you see a CAPTCHA image, ask the user to solve it: {{"type": "ASK_USER", "question": "Please enter the CAPTCHA shown."}}
- If you see an OTP field, ask the user to provide the OTP.
- Always output valid JSON. No markdown fences.
"""

    def decide_next_step(self, intent: str, dom_state: list[dict], step: dict, profile: dict = None) -> dict:
        """
        Ask the LLM what to do next based on the DOM state.
        Returns a dict indicating the chosen action.
        """
        if profile is None:
            profile = {}
            
        sys_prompt = self._build_system_prompt(intent, profile, step)
        user_message = f"Current DOM State:\n{json.dumps(dom_state, indent=2)}\n\nWhat is the next step?"

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_message}
        ]

        logger.info(f"ReasoningEngine evaluating DOM state... ({len(dom_state)} elements found)")

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=0.0,
                max_tokens=500,
            )
            
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty (None) content")
                
            raw = content.strip()
            logger.debug(f"Reasoning LLM raw response: {raw}", self.verbose)

            if raw.startswith("```"):
                lines = raw.split("\n")
                inner = [l for l in lines[1:] if l.strip() != "```"]
                raw = "\n".join(inner).strip()
            if not raw.startswith("{") and "{" in raw:
                start = raw.index("{")
                end   = raw.rindex("}") + 1
                raw   = raw[start:end]

            result = json.loads(raw)
            return result
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse Reasoning JSON response: {e}")
            logger.error(f"Raw response: {content[:500]}")
            # Fallback to asking user if parsing fails
            return {
                "type": "ASK_USER",
                "question": "I am having trouble understanding the page. How should I proceed?"
            }
        except Exception as e:
            logger.error(f"Reasoning LLM call failed: {e}")
            return {
                "type": "ASK_USER",
                "question": f"An error occurred: {e}. Cannot proceed automatically."
            }
