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
        # Provide domain-specific schema maps to improve field filling accuracy
        schema_map = ""
        if intent == "apply_insurance":
            schema_map = """
The target "apply_insurance" form has the following specific sections and fields:
1. State, Scheme, Season, Year (Cascading dropdowns)
2. Farmer Details: Full Name, Passbook Name, Relationship, Relative Name, Mobile No, Age, Caste Category, Gender, Farmer Type, Farmer Category
3. Residential Details: State, District, Sub District, Village/Town, Address, Pin Code
4. Farmer ID: ID Type (e.g., UID), ID No (Verify button required)
5. Account Details: Have IFSC? (Radio Yes/No), IFSC, State, District, Bank Name, Bank Branch, Bank A/C No, Confirm A/C No
6. Final Actions: Captcha, Submit (Create User)

Use this schema as a guide when deciding what information needs to be ASK_USER vs ACTION.
"""
        elif intent == "calculate_premium":
            schema_map = """
The premium calculator is a modal on the standard Home Page.
1. FIRST, if the calculator modal is NOT open, find the 'Insurance Premium Calculator' card/button and click it.
2. Once the modal is open, fill the cascading dropdowns in order: Season -> Year -> Scheme -> State -> District -> Crop.
3. Then fill the 'Area (In Hectare)' input field.
4. Finally, click 'Calculate' and examine the result.

Use this schema as a guide to determine your next step.
"""

        # Build a cleaned profile view (exclude internal _history from display, explain it separately)
        display_profile = {k: v for k, v in profile.items() if k != "_history"}
        history = profile.get("_history", {})

        history_section = ""
        if history:
            history_section = f"""
Previously asked questions and the user's answers (use these to avoid re-asking):
{json.dumps(history, indent=2)}
"""

        # Field mapping guidance
        field_mapping_guide = """
Profile Field Mapping Guide (profile key → form field):
- "full_name" or "name" → Full Name input
- "mobile" → Mobile Number input
- "age" → Age input
- "gender" → Gender dropdown (Male/Female/Others)
- "caste" or "category" → Caste Category dropdown (GENERAL/OBC/SC/ST)
- "relationship" → Relationship dropdown (S/O/D/O/W/O/C/O)
- "relative_name" → Father/Husband Name input
- "state" → State dropdown (NOTE: there are multiple state dropdowns — residential AND bank)
- "district" → District dropdown (residential section)
- "taluka" or "sub_district" → Sub-District/Tehsil dropdown
- "village" → Village/Town dropdown
- "pincode" → PIN Code input
- "address" → Full Address input
- "aadhaar" → Aadhaar Number input
- "bank_name" → Bank Name dropdown (in Bank section)
- "bank_branch" → Branch dropdown (in Bank section)
- "bank_state" → Bank State dropdown (in Bank section, NOT residential)
- "bank_district" → Bank District dropdown (in Bank section)
- "account_no" → Bank Account Number input
- "season" → Season dropdown (Kharif/Rabi/Zaid)
- "crop_year" or "year" → Year dropdown
"""

        return f"""You are an expert PMFBY Registration Assistant.
Your goal is to complete the user's intent: {intent}.
You are currently evaluating the following planned step:
{json.dumps(step, indent=2)}
{schema_map}

You have access to the following user profile data:
{json.dumps(display_profile, indent=2)}
{history_section}
{field_mapping_guide}

You will receive the current DOM state of the form representing interactable elements.
Your task is to analyze the DOM state, the profile, and the planned step, then decide what to do next.

You MUST respond with a JSON object in one of three formats:

1. ACTION
If you have the data needed to fill a field, click a button, or select an option:
{{
    "type": "ACTION",
    "action": "fill",  // "fill", "click", "select"
    "selector": "CSS selector from the DOM state (Leave empty \"\" if unknown)",
    "label": "Human-readable label of the element, to be used by a Vision parser if the selector is empty. e.g. 'Insurance Premium Calculator'",
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
- For dropdowns (`<select>`), prefer checking if the profile matches any of the available options. Don't guess the option value; use the exact value from the DOM options OR the exact label text from the options dictionary.
- CRITICAL FOR DROPDOWNS: If you choose to emit an `ACTION` of type `select`, the `value` field in your JSON MUST tightly match either the `value` OR the `text` of one of the provided options in the DOM State array.
- IF THERE ARE UNFILLED FORM FIELDS visible in the DOM, prioritize filling them FIRST. DO NOT ask to solve the CAPTCHA until ALL other applicable fields have been filled.
- If you see a CAPTCHA image and NO OTHER unfilled interactable fields are remaining, then ask the user to solve it: {{"type": "ASK_USER", "question": "Please enter the CAPTCHA shown."}}
- If you see an OTP field, ask the user to provide the OTP (again, only if no other fields logically come first).
- VERY IMPORTANT: The CAPTCHA is always the *last* step on any page. Ignore the CAPTCHA completely until you have issued `ACTION` commands to fill out every other necessary field (name, state, district, dropdowns, etc.).
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
                max_tokens=1024,
            )
            
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty (None) content")
                
            raw = content.strip()
            logger.info(f"\n[BACKEND] Reasoning LLM Raw Response:\n{raw}\n")

            import re
            match = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.DOTALL | re.IGNORECASE)
            if match:
                raw = match.group(1).strip()
            elif not raw.startswith("{") and "{" in raw:
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
