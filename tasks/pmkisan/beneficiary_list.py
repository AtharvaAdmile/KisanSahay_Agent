"""
BeneficiaryListTask — gets PM-KISAN beneficiary list filtered by geography.

Live selectors (verified 2026-02-21 on /Rpt_BeneficiaryStatus_pub.aspx):
  State dropdown:       #ContentPlaceHolder1_DropDownState
  District dropdown:    #ContentPlaceHolder1_DropDownDistrict
  Sub-District dropdown:#ContentPlaceHolder1_DropDownSubDistrict
  Block dropdown:       #ContentPlaceHolder1_DropDownBlock  (not on all states)
  Village dropdown:     #ContentPlaceHolder1_DropDownVillage
  Get Report button:    #ContentPlaceHolder1_btnsubmit

IMPORTANT: All selects use ASP.NET __doPostBack. After each selection
call wait_for_postback() (not just asyncio.sleep) so subsequent
dropdowns are populated before interacting with them.
No CAPTCHA on this page — fully automatable.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import json
from pathlib import Path

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import prompt_user, prompt_confirm, save_json


class BeneficiaryListTask:
    """Fetches the beneficiary list by geographical location."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose

    async def get_list(self, **pre_params) -> dict:
        """
        Navigate /Rpt_BeneficiaryStatus_pub.aspx, fill location filters,
        click 'Get Report', extract beneficiary table, and save to JSON.

        Flow:
          1. Select State (dropdown)
          2. Fill District
          3. Fill Sub-District
          4. Fill Block
          5. Fill Village
          6. Click Get Report
          7. Extract table and save
        """
        logger.section("PM-KISAN Beneficiary List")
        page = self.browser.page

        # ── Step 1: State ─────────────────────────────────────────────────
        logger.step("Step 1: Select State")
        state = pre_params.get("state") or prompt_user("State (e.g., Maharashtra)")

        try:
            await self.browser.select_option("#ContentPlaceHolder1_DropDownState", label=state)
            logger.success(f"State selected: {state}")
        except Exception:
            logger.warning(f"Could not select state — trying vision")
            await self.browser.vision_select(0, state, "the State dropdown")

        # Wait for ASP.NET postback to populate district dropdown
        await self.browser.wait_for_postback()

        # ── Step 2: District ─────────────────────────────────────────────
        logger.step("Step 2: Enter District")
        district = pre_params.get("district") or prompt_user("District")
        if district:
            # Try select then fallback to fill
            filled = False
            try:
                await self.browser.select_option(
                    "#ContentPlaceHolder1_DropDownDistrict", label=district, timeout=5000
                )
                logger.success(f"District selected: {district}")
                filled = True
            except Exception:
                pass
            if not filled:
                await self.browser.vision_fill(
                    "#ContentPlaceHolder1_DropDownDistrict", district, "the District field"
                )
            await self.browser.wait_for_postback()

        # ── Step 3: Sub-District ─────────────────────────────────────────
        logger.step("Step 3: Enter Sub-District / Tehsil")
        sub_district = (
            pre_params.get("sub_district")
            or pre_params.get("subdistrict")
            or prompt_user("Sub-District / Tehsil (or press Enter to skip)")
        )
        if sub_district:
            try:
                await self.browser.select_option(
                    "#ContentPlaceHolder1_DropDownSubDistrict", label=sub_district, timeout=5000
                )
                logger.success(f"Sub-District: {sub_district}")
            except Exception:
                await self.browser.vision_fill(
                    "#ContentPlaceHolder1_DropDownSubDistrict", sub_district, "the Sub-District field"
                )
            await self.browser.wait_for_postback()

        # ── Step 4: Block ─────────────────────────────────────────────────
        logger.step("Step 4: Enter Block / Mandal")
        block = pre_params.get("block") or prompt_user("Block / Mandal (or press Enter to skip)")
        if block:
            try:
                await self.browser.select_option(
                    "#ContentPlaceHolder1_DropDownBlock", label=block, timeout=5000
                )
                logger.success(f"Block: {block}")
            except Exception:
                await self.browser.vision_fill(
                    "#ContentPlaceHolder1_DropDownBlock", block, "the Block field"
                )
            await self.browser.wait_for_postback()

        # ── Step 5: Village ───────────────────────────────────────────────
        logger.step("Step 5: Enter Village")
        village = pre_params.get("village") or prompt_user("Village (or press Enter to skip)")
        if village:
            try:
                await self.browser.select_option(
                    "#ContentPlaceHolder1_DropDownVillage", label=village, timeout=5000
                )
                logger.success(f"Village: {village}")
            except Exception:
                await self.browser.vision_fill(
                    "#ContentPlaceHolder1_DropDownVillage", village, "the Village field"
                )
            await self.browser.wait_for_postback()

        # ── Step 6: Get Report ────────────────────────────────────────────
        logger.step("Step 6: Clicking 'Get Report' to fetch beneficiary list...")
        try:
            await self.browser.click("#ContentPlaceHolder1_btnsubmit")
            logger.success("Get Report clicked")
        except Exception:
            await self.browser.vision_click(
                "#ContentPlaceHolder1_btnsubmit", "the 'Get Report' button"
            )
        await asyncio.sleep(5)

        # ── Step 7: Extract table ─────────────────────────────────────────
        logger.step("Step 7: Extracting beneficiary list...")
        await self.browser.screenshot("beneficiary_list_result")

        table_data = await self._extract_table()
        out_path = ""

        if table_data:
            logger.success(f"Extracted {len(table_data)} beneficiaries")
            out_path = save_json(
                {
                    "state": state,
                    "district": district,
                    "block": block,
                    "village": village,
                    "beneficiaries": table_data,
                },
                "output/beneficiary_list.json",
            )
            logger.success(f"Beneficiary list saved: {out_path}")
            # Show first 5
            for row in table_data[:5]:
                logger.info(f"  {row}")
        else:
            logger.warning(
                "Could not extract table data automatically. "
                "Check beneficiary_list_result.png"
            )

        return {
            "task": "get_beneficiary_list",
            "state": state,
            "district": district or "",
            "block": block or "",
            "village": village or "",
            "beneficiary_count": len(table_data),
            "output_file": out_path,
            "status": "completed",
        }

    async def _extract_table(self) -> list[dict]:
        """Extract table rows from the beneficiary list result page."""
        page = self.browser.page

        try:
            # Find the main data table
            tables = await page.query_selector_all("table")
            for table in tables:
                rows = await table.query_selector_all("tr")
                if len(rows) < 2:
                    continue

                headers = []
                header_row = rows[0]
                header_cells = await header_row.query_selector_all("th, td")
                for cell in header_cells:
                    headers.append((await cell.inner_text()).strip())

                if not headers or len(headers) < 2:
                    continue

                data_rows = []
                for row in rows[1:]:
                    cells = await row.query_selector_all("td")
                    if len(cells) >= 2:
                        row_data = {}
                        for idx, cell in enumerate(cells):
                            key = headers[idx] if idx < len(headers) else f"col_{idx}"
                            row_data[key] = (await cell.inner_text()).strip()
                        data_rows.append(row_data)

                if data_rows:
                    return data_rows

        except Exception as e:
            logger.warning(f"Table extraction failed: {e}")

        return []
