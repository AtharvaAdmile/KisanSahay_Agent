"""
LLM-powered intent parser for PMFBY Agent.
Uses any OpenAI-compatible API endpoint configured via .env.
Classifies user prompts into structured intents with extracted parameters.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

from utils import logger

load_dotenv()

INTENT_SCHEMA = {
    "traverse_site":      "Explore pages, build sitemap, list links",
    "apply_insurance":    "Fill farmer registration / crop insurance form",
    "calculate_premium":  "Calculate insurance premium for a crop",
    "check_status":       "Check application status using receipt/policy number",
    "raise_grievance":    "File a complaint or report crop loss via KRPH",
    "check_complaint":    "Check KRPH complaint/crop-loss intimation status",
    "access_lms":         "Register or log in to PMFBY LMS for training courses",
    "view_weather":       "View weather data on the WINDS portal",
    "upload_crop_photo":  "Upload a crop photo via the CROPIC portal",
    "track_cropic":       "Track crop photo submission status on CROPIC",
    "access_yestech":     "Navigate to the YES-TECH yield estimation portal",
    "navigate_page":      "Navigate to a specific page (FAQ, contact, sitemap, etc.)",
    "get_info":           "Get information about the PMFBY scheme, documents, or eligibility",
    "setup_profile":      "Set up or update the local farmer profile for form pre-filling",
}

SYSTEM_PROMPT = """You are an intent classifier for the PMFBY (Pradhan Mantri Fasal Bima Yojana) crop insurance website agent.

Given a user's natural language prompt, classify it into ONE of these intents:
- traverse_site: exploring the site, listing pages, building a sitemap
- apply_insurance: filling crop insurance application, farmer registration
- calculate_premium: calculating insurance premium for a crop/season/area
- check_status: checking application status with a receipt or policy number
- raise_grievance: filing complaints, reporting crop loss, KRPH grievance
- check_complaint: checking KRPH complaint status or crop loss intimation status
- access_lms: register or log in to PMFBY LMS for training or courses
- view_weather: view weather data / WINDS portal
- upload_crop_photo: upload crop photo via CROPIC portal
- track_cropic: track crop photo submission status on CROPIC
- access_yestech: navigate to YES-TECH yield estimation portal
- navigate_page: opening a specific page (FAQ, contact, sitemap, feedback)
- get_info: asking about the PMFBY scheme, required documents, eligibility
- setup_profile: set up or update the local farmer profile for form auto-filling

Also extract any parameters mentioned in the prompt. Common parameters:
- receipt_number / policy_id: for status checks
- crop: crop name (wheat, rice, cotton, etc.)
- season: Kharif, Rabi, or Zaid
- state: Indian state name
- district: district name
- area: area in hectares
- mobile: mobile phone number
- reference_id: reference ID for CROPIC tracking
- page: specific page name (faq, contact, sitemap, feedback, etc.)

Respond with ONLY a JSON object (no markdown, no explanation):
{
    "intent": "intent_name",
    "params": {"key": "value"},
    "confidence": 0.0 to 1.0,
    "explanation": "brief reason for classification"
}"""

FEW_SHOT_EXAMPLES = [
    {
        "role": "user",
        "content": "help me fill the application form on pmfby site"
    },
    {
        "role": "assistant",
        "content": '{"intent": "apply_insurance", "params": {}, "confidence": 0.95, "explanation": "User wants to fill the crop insurance application form"}'
    },
    {
        "role": "user",
        "content": "check my application status using reference number ABC123"
    },
    {
        "role": "assistant",
        "content": '{"intent": "check_status", "params": {"receipt_number": "ABC123"}, "confidence": 0.98, "explanation": "User wants to check status with a specific receipt number"}'
    },
    {
        "role": "user",
        "content": "calculate premium for wheat in Kharif season for Rajasthan, 5 hectares"
    },
    {
        "role": "assistant",
        "content": '{"intent": "calculate_premium", "params": {"crop": "wheat", "season": "Kharif", "state": "Rajasthan", "area": "5"}, "confidence": 0.97, "explanation": "User wants to calculate insurance premium with specific crop details"}'
    },
    {
        "role": "user",
        "content": "show me all the pages on the pmfby website"
    },
    {
        "role": "assistant",
        "content": '{"intent": "traverse_site", "params": {}, "confidence": 0.92, "explanation": "User wants to explore and list all pages on the site"}'
    },
    {
        "role": "user",
        "content": "I want to report crop loss in my field"
    },
    {
        "role": "assistant",
        "content": '{"intent": "raise_grievance", "params": {}, "confidence": 0.93, "explanation": "User wants to report crop loss through the grievance portal"}'
    },
    {
        "role": "user",
        "content": "open the FAQ page"
    },
    {
        "role": "assistant",
        "content": '{"intent": "navigate_page", "params": {"page": "faq"}, "confidence": 0.96, "explanation": "User wants to navigate to the FAQ page"}'
    },
    {
        "role": "user",
        "content": "access LMS for training on crop insurance"
    },
    {
        "role": "assistant",
        "content": '{"intent": "access_lms", "params": {}, "confidence": 0.95, "explanation": "User wants to access the LMS portal for training courses"}'
    },
    {
        "role": "user",
        "content": "check my complaint status on KRPH"
    },
    {
        "role": "assistant",
        "content": '{"intent": "check_complaint", "params": {}, "confidence": 0.94, "explanation": "User wants to view their complaint status on the KRPH portal"}'
    },
    {
        "role": "user",
        "content": "show me the weather data on WINDS"
    },
    {
        "role": "assistant",
        "content": '{"intent": "view_weather", "params": {}, "confidence": 0.96, "explanation": "User wants to view weather information on the WINDS portal"}'
    },
    {
        "role": "user",
        "content": "upload crop photo for insurance assessment"
    },
    {
        "role": "assistant",
        "content": '{"intent": "upload_crop_photo", "params": {}, "confidence": 0.95, "explanation": "User wants to upload a crop photo via CROPIC"}'
    },
    {
        "role": "user",
        "content": "track my CROPIC photo submission status using reference ABC456"
    },
    {
        "role": "assistant",
        "content": '{"intent": "track_cropic", "params": {"reference_id": "ABC456"}, "confidence": 0.97, "explanation": "User wants to track their crop photo submission status on CROPIC"}'
    },
    {
        "role": "user",
        "content": "open YES-TECH yield estimation portal"
    },
    {
        "role": "assistant",
        "content": '{"intent": "access_yestech", "params": {}, "confidence": 0.95, "explanation": "User wants to navigate to the YES-TECH portal"}'
    },
    {
        "role": "user",
        "content": "set up my farmer profile"
    },
    {
        "role": "assistant",
        "content": '{"intent": "setup_profile", "params": {}, "confidence": 0.97, "explanation": "User wants to configure their local farmer profile for form auto-filling"}'
    },
]


class IntentParser:
    """Parses natural language prompts into structured intents via LLM."""

    def __init__(self, verbose: bool = False):
        api_key = os.getenv("LLM_API_KEY")
        base_url = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1")
        self.model = os.getenv("LLM_MODEL_ID", "gpt-4o-mini")
        self.verbose = verbose

        if not api_key:
            raise ValueError(
                "LLM_API_KEY not found in .env file. "
                "Please create a .env file with LLM_API_KEY, LLM_BASE_URL, and LLM_MODEL_ID."
            )

        self.client = OpenAI(api_key=api_key, base_url=base_url)
        logger.debug(f"LLM client initialized: model={self.model}, base={base_url}", verbose)

    def parse(self, prompt: str) -> dict:
        """
        Parse a user prompt into an intent dict.
        Returns: {"intent": str, "params": dict, "confidence": float, "explanation": str}
        """
        logger.step(f"Parsing intent from: \"{prompt}\"")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            *FEW_SHOT_EXAMPLES,
            {"role": "user", "content": prompt},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.1,
                max_tokens=300,
            )
            raw = response.choices[0].message.content.strip()
            logger.debug(f"LLM raw response: {raw}", self.verbose)

            # Parse JSON — handle markdown code blocks if LLM wraps them
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
                raw = raw.strip()

            result = json.loads(raw)

            # Validate structure
            if "intent" not in result:
                raise ValueError("Missing 'intent' key in LLM response")

            result.setdefault("params", {})
            result.setdefault("confidence", 0.5)
            result.setdefault("explanation", "")

            logger.success(
                f"Intent: {result['intent']} (confidence: {result['confidence']:.0%})"
            )
            if result["params"]:
                logger.info(f"Extracted params: {result['params']}")

            return result

        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            return {
                "intent": "get_info",
                "params": {"raw_prompt": prompt},
                "confidence": 0.3,
                "explanation": "Fallback — LLM response was not valid JSON",
            }
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise
