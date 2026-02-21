"""
KCCAccessTask — Kisan Credit Card information and form download.

Key findings:
  - No online application portal for KCC on pmkisan.gov.in
  - Application form PDF: https://pmkisan.gov.in/Documents/Kcc.pdf
  - Saturation campaign circular: https://pmkisan.gov.in/Documents/finalKCCCircular.pdf
  - General info accessible via the homepage KCC section
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import os
from pathlib import Path

import requests

from shared.browser.controller import Browser, BASE_URL
from shared.utils import logger
from shared.utils.helpers import prompt_confirm


KCC_FORM_URL = f"{BASE_URL}/Documents/Kcc.pdf"
KCC_CIRCULAR_URL = f"{BASE_URL}/Documents/finalKCCCircular.pdf"


class KCCAccessTask:
    """Provides KCC information and downloads official forms."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def access_kcc(self, **pre_params) -> dict:
        """
        Provide KCC information and download the official application form.

        Flow:
          1. Navigate to homepage, scroll to KCC section
          2. Extract KCC info text
          3. Download KCC PDF form
          4. Offer to download saturation campaign circular
        """
        logger.section("Kisan Credit Card (KCC)")
        page = self.browser.page

        # Display scheme info
        logger.info(
            "\nKisan Credit Card (KCC) — Overview:\n"
            "  • Provides short-term credit to farmers for agricultural needs\n"
            "  • Interest rate subvention: 2% p.a. (effective rate ~4-7%)\n"
            "  • Credit limit: Based on land holdings and crop requirements\n"
            "  • Converted from PM-KISAN eligible farmers via Saturation Campaign\n"
            "  • Apply at your nearest bank with: land record, Aadhaar, Photo\n"
            "  • No separate online registration portal on pmkisan.gov.in\n"
        )

        # Navigate to homepage to find KCC section
        logger.step("Scrolling to KCC section on homepage...")
        try:
            # Try to find KCC section text
            kcc_text = await self.browser.get_text(
                "text=Kisan Credit, [id*='kcc'], [class*='kcc'], "
                "section:has-text('KCC'), div:has-text('Kisan Credit Card')"
            )
            if kcc_text:
                logger.info(f"KCC section found:\n{kcc_text[:300]}")
        except Exception:
            pass

        await self.browser.screenshot("kcc_homepage_section")

        # Download KCC form PDF
        logger.step("Downloading KCC Application Form PDF...")
        form_path = await self._download_pdf(KCC_FORM_URL, "output/kcc_application_form.pdf")

        # Offer circular download
        circular_path = ""
        if prompt_confirm("Also download the KCC Saturation Campaign Circular?", default=False):
            circular_path = await self._download_pdf(
                KCC_CIRCULAR_URL, "output/kcc_saturation_circular.pdf"
            )

        return {
            "task": "access_kcc",
            "info": "KCC application must be submitted at your nearest bank. No online portal.",
            "kcc_form_pdf": form_path,
            "circular_pdf": circular_path,
            "kcc_form_url": KCC_FORM_URL,
            "status": "completed",
        }

    async def _download_pdf(self, url: str, dest: str) -> str:
        """Download a PDF from `url`, save to `dest`, return path."""
        try:
            logger.info(f"Downloading: {url}")
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            response = requests.get(url, headers=headers, timeout=30)
            response.raise_for_status()

            dest_path = Path(dest)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(response.content)

            size_kb = len(response.content) // 1024
            logger.success(f"Downloaded ({size_kb} KB): {dest_path.resolve()}")
            return str(dest_path.resolve())

        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            logger.info(f"You can manually download from: {url}")
            return ""
