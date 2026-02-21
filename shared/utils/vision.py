"""
VisionHelper — VLM-powered visual element locator.

Uses a Vision Language Model to visually inspect a screenshot and return
pixel coordinates of a described UI element.

This is a FALLBACK mechanism — only invoked when standard Playwright
selectors fail. When used, it's logged clearly in the CLI.

Configuration (in .env):
    VISION_API_KEY   — API key (defaults to LLM_API_KEY if not set)
    VISION_MODEL_ID  — Model ID (default: meta/llama-4-maverick-17b-128e-instruct)
    VISION_API_URL   — API endpoint (default: NVIDIA NIM)
"""

import base64
import json
import os
import re

import requests
from dotenv import load_dotenv

from . import logger

load_dotenv()

_NVIDIA_URL = "https://integrate.api.nvidia.com/v1/chat/completions"
_DEFAULT_MODEL = "meta/llama-4-maverick-17b-128e-instruct"

_COORD_PROMPT = """\
You are a precise UI element locator. You will be shown a screenshot of a webpage.
Your task: find the UI element that best matches the description and return its
center pixel coordinates.

Element to find: {description}

Rules:
1. Visually scan the page for the element.
2. Return ONLY a single line in this exact format as your FINAL output:
   COORDINATES: x,y
   Where x = horizontal pixel, y = vertical pixel of the element center.
3. If you cannot find the element, return:
   COORDINATES: NOT_FOUND
4. Do NOT include any other text after the COORDINATES line.

What element are you looking for? {description}
"""


def _read_image_b64(path: str) -> str:
    """Read an image file and return its base64-encoded string."""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def _parse_coordinates(text: str) -> tuple[int, int] | None:
    """
    Extract (x, y) from VLM response text.
    Looks for the last line matching 'COORDINATES: x,y'.
    """
    matches = re.findall(r"COORDINATES:\s*(\d+)\s*,\s*(\d+)", text, re.IGNORECASE)
    if matches:
        x, y = matches[-1]
        return int(x), int(y)
    if "NOT_FOUND" in text.upper():
        return None
    return None


def _stream_vlm_response(api_key: str, model: str, api_url: str,
                          image_b64: str, prompt: str, verbose: bool) -> str:
    """
    Make a streaming request to the VLM API and return the accumulated text.
    Handles thinking tokens from reasoning models (strips <think...</think).
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "text/event-stream",
    }
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b64}"
                        },
                    },
                    {
                        "type": "text",
                        "text": prompt,
                    },
                ],
            }
        ],
        "max_tokens": 512,
        "temperature": 0.1,
        "top_p": 0.9,
        "stream": True,
    }

    full_text = ""
    try:
        response = requests.post(
            api_url, headers=headers, json=payload, stream=True, timeout=60
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if not line:
                continue
            decoded = line.decode("utf-8")
            if decoded.startswith("data: "):
                data_str = decoded[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {})
                    content = delta.get("content", "")
                    if content:
                        full_text += content
                        if verbose:
                            print(content, end="", flush=True)
                except json.JSONDecodeError:
                    continue

        if verbose:
            print()

    except requests.exceptions.RequestException as e:
        logger.error(f"VLM API request failed: {e}")
        return ""

    full_text = re.sub(r"<think.*?</think ", "", full_text, flags=re.DOTALL).strip()
    return full_text


class VisionHelper:
    """
    VLM-powered visual element locator.
    Sends a screenshot to a Vision Language Model and asks it to locate
    a described UI element, returning its pixel coordinates.
    """

    def __init__(self, verbose: bool = False):
        self.api_key = os.getenv("VISION_API_KEY") or os.getenv("LLM_API_KEY")
        self.model = os.getenv("VISION_MODEL_ID", _DEFAULT_MODEL)
        self.api_url = os.getenv("VISION_API_URL", _NVIDIA_URL)
        self.verbose = verbose
        self._available = bool(self.api_key)

        if not self._available:
            logger.warning(
                "VisionHelper: No VISION_API_KEY or LLM_API_KEY found. "
                "Vision fallback will not be available."
            )

    @property
    def available(self) -> bool:
        return self._available

    def locate_element(
        self, screenshot_path: str, description: str,
        page_width: int = 1280, page_height: int = 900
    ) -> tuple[int, int] | None:
        """
        Ask the VLM to locate an element described in natural language.

        Args:
            screenshot_path: Path to a PNG screenshot of the current page.
            description: Human-readable description of the element to find.
            page_width, page_height: Browser viewport dimensions for validation.

        Returns:
            (x, y) pixel coordinates of the element center, or None if not found.
        """
        if not self._available:
            return None

        logger.warning(
            f"👁  Vision Fallback Activated — asking VLM to locate: \"{description}\""
        )
        logger.info(f"   Model: {self.model}")
        logger.info(f"   Screenshot: {screenshot_path}")

        try:
            image_b64 = _read_image_b64(screenshot_path)
        except FileNotFoundError:
            logger.error(f"VisionHelper: Screenshot not found: {screenshot_path}")
            return None

        prompt = _COORD_PROMPT.format(description=description)

        if self.verbose:
            logger.debug("   VLM streaming response:", verbose=True)

        response_text = _stream_vlm_response(
            self.api_key, self.model, self.api_url,
            image_b64, prompt, self.verbose
        )

        if not response_text:
            logger.error("VisionHelper: Empty response from VLM.")
            return None

        logger.debug(f"   VLM response: {response_text[:200]}", verbose=self.verbose)

        coords = _parse_coordinates(response_text)
        if coords is None:
            logger.warning(f"👁  Vision Fallback: element not found by VLM — \"{description}\"")
            return None

        x, y = coords
        if not (0 <= x <= page_width and 0 <= y <= page_height):
            logger.warning(
                f"👁  Vision Fallback: VLM returned out-of-bounds coords "
                f"({x}, {y}) for viewport {page_width}×{page_height} — discarding"
            )
            return None

        logger.success(f"👁  Vision Fallback: located \"{description}\" at ({x}, {y})")
        return x, y
