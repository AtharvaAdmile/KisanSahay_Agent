"""
AIFAccessTask — Agriculture Infrastructure Fund information and guideline download.

Key findings:
  - No online application portal on pmkisan.gov.in
  - Operational Guidelines PDF:
    https://pmkisan.gov.in/Documents/Operational%20Guidelines%20of%20Financing%20Facility%20under%20Agriculture%20Infrastructure%20Fund.pdf
  - Homepage has an informational section on AIF
  - Applications via banks/financial institutions, not directly via the portal
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from pathlib import Path

import requests

from shared.browser.controller import Browser, BASE_URL
from shared.utils import logger
from shared.utils.helpers import prompt_confirm


AIF_GUIDELINES_URL = (
    f"{BASE_URL}/Documents/Operational%20Guidelines%20of%20Financing%20Facility"
    f"%20under%20Agriculture%20Infrastructure%20Fund.pdf"
)


class AIFAccessTask:
    """Provides AIF information and downloads official guidelines."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def access_aif(self, **pre_params) -> dict:
        """
        Provide AIF information and download operational guidelines PDF.

        Flow:
          1. Display scheme overview
          2. Navigate homepage to find AIF section
          3. Download guidelines PDF
        """
        logger.section("Agriculture Infrastructure Fund (AIF)")
        page = self.browser.page

        # Display overview
        logger.info(
            "\nAgriculture Infrastructure Fund (AIF) — Overview:\n"
            "  • Rs 1 lakh crore fund for post-harvest infrastructure creation\n"
            "  • Interest subvention: 3% p.a. (up to Rs 2 crore per project)\n"
            "  • Credit Guarantee: CGTMSE for loans up to Rs 2 crore\n"
            "  • Eligible entities: FPOs, PACS, Agri-entrepreneurs, Startups, etc.\n"
            "  • Apply online at agriinfra.dac.gov.in (not pmkisan.gov.in)\n"
            "  • Operational Guidelines available as PDF download below\n"
        )

        # Scroll to AIF section on homepage
        logger.step("Looking for AIF section on homepage...")
        try:
            aif_text = await self.browser.get_text(
                "text=Agriculture Infrastructure, [id*='aif'], [class*='aif'], "
                "section:has-text('AIF'), div:has-text('Agriculture Infrastructure Fund')"
            )
            if aif_text:
                logger.info(f"AIF section text:\n{aif_text[:300]}")
        except Exception:
            pass

        await self.browser.screenshot("aif_homepage_section")

        # Download guidelines
        logger.step("Downloading AIF Operational Guidelines PDF...")
        guidelines_path = await self._download_pdf(
            AIF_GUIDELINES_URL, "output/aif_operational_guidelines.pdf"
        )

        return {
            "task": "access_aif",
            "info": "AIF applications are made via agriinfra.dac.gov.in (not pmkisan.gov.in).",
            "guidelines_pdf": guidelines_path,
            "guidelines_url": AIF_GUIDELINES_URL,
            "aif_portal": "https://agriinfra.dac.gov.in",
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
            response = requests.get(url, headers=headers, timeout=60)
            response.raise_for_status()

            dest_path = Path(dest)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest_path.write_bytes(response.content)

            size_kb = len(response.content) // 1024
            logger.success(f"Downloaded ({size_kb} KB): {dest_path.resolve()}")
            return str(dest_path.resolve())

        except Exception as e:
            logger.error(f"Download failed for {url}: {e}")
            logger.info(f"You can manually access the PDF at:\n  {url}")
            return ""
