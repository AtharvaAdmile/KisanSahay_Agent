"""
IntentParser — classifies natural language prompts into structured intents.
Uses an OpenAI-compatible LLM with a JSON response schema.

No keyword fallback — requires LLM_API_KEY to be configured.
Reports error and terminates if API key is missing or call fails.
"""

import json
import os
import sys

from openai import OpenAI
from dotenv import load_dotenv

from ..config.base import SiteConfig
from ..utils import logger

load_dotenv()


class IntentParser:
    """Classifies user prompts into structured intents using an LLM."""

    def __init__(self, config: SiteConfig, verbose: bool = False):
        self.config = config
        api_key = (os.getenv("LLM_API_KEY") or "").strip()
        base_url = (os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1").strip()
        self.model_id = (os.getenv("LLM_MODEL_ID") or "gpt-4o-mini").strip()
        self.verbose = verbose

        if not api_key:
            logger.error(
                "LLM_API_KEY not set in .env file.\n"
                "Please create a .env file with:\n"
                "  LLM_API_KEY=your-api-key\n"
                "  LLM_BASE_URL=https://api.openai.com/v1  (optional)\n"
                "  LLM_MODEL_ID=gpt-4o-mini  (optional)"
            )
            sys.exit(1)

        try:
            self.client = OpenAI(api_key=api_key, base_url=base_url)
            logger.debug(f"LLM ready: {self.model_id} at {base_url}", verbose)
        except Exception as e:
            logger.error(f"Could not initialise LLM client: {e}")
            sys.exit(1)

    def _build_messages(self, prompt: str) -> list[dict]:
        """Build the message list for the LLM call."""
        messages = [{"role": "system", "content": self.config.system_prompt}]
        
        for ex in self.config.few_shot_examples:
            if "user" in ex and "response" in ex:
                messages.append({"role": "user", "content": ex["user"]})
                messages.append({"role": "assistant", "content": json.dumps(ex["response"])})
            elif "role" in ex and "content" in ex:
                messages.append(ex)
        
        messages.append({"role": "user", "content": prompt})
        return messages

    def parse(self, prompt: str) -> dict:
        """
        Classify a user prompt and return:
          {"intent": str, "params": dict, "confidence": float}

        Raises SystemExit on failure.
        """
        logger.info(
            f"Classifying intent for: \"{prompt[:80]}...\"" if len(prompt) > 80
            else f"Classifying intent for: \"{prompt}\""
        )

        messages = self._build_messages(prompt)

        try:
            response = self.client.chat.completions.create(
                model=self.model_id,
                messages=messages,
                temperature=0.1,
                max_tokens=400,
                # NOTE: response_format={"type": "json_object"} is intentionally omitted.
                # NVIDIA NIM and most OSS models do NOT support this OpenAI-specific parameter.
                # We enforce JSON via the system prompt instead.
            )
            
            content = response.choices[0].message.content
            if content is None:
                raise ValueError("LLM returned empty (None) content")
                
            raw = content.strip()
            logger.debug(f"LLM raw response: {raw}", self.verbose)

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            logger.error(
                "Intent classification requires a working LLM API connection. "
                "Please check your API key and network connection."
            )
            sys.exit(1)

        try:
            # Strip markdown code fences that NVIDIA / OSS models often add.
            # e.g. ```json\n{...}\n``` or ```\n{...}\n```
            if raw.startswith("```"):
                lines = raw.split("\n")
                # Drop the opening fence line and the closing ```
                inner = [l for l in lines[1:] if l.strip() != "```"]
                raw = "\n".join(inner).strip()

            # Last-resort: extract the first JSON object/array even if there's surrounding text
            if not raw.startswith("{") and "{" in raw:
                start = raw.index("{")
                end   = raw.rindex("}") + 1
                raw   = raw[start:end]

            result = json.loads(raw)
        except json.JSONDecodeError as e:
            logger.error(f"Could not parse LLM JSON response: {e}")
            logger.error(f"Raw response: {raw[:500]}")
            sys.exit(1)

        intent = result.get("intent", "get_info")
        if intent not in self.config.intent_schema:
            logger.warning(f"Unknown intent '{intent}' — falling back to 'get_info'")
            intent = "get_info"

        params = result.get("params", {}) or {}
        confidence = float(result.get("confidence", 0.8))

        logger.success(f"Intent: {intent}  ({confidence:.0%} confidence)")
        if params:
            logger.info(f"Extracted params: {params}")

        return {"intent": intent, "params": params, "confidence": confidence}
