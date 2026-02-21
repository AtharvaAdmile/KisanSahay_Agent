"""
SiteExplorerTask — BFS crawler for pmkisan.gov.in.
Explores up to a configurable depth and outputs a JSON sitemap.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
import json
from collections import deque
from pathlib import Path
from urllib.parse import urlparse, urljoin

from shared.browser.controller import Browser, BASE_URL
from shared.utils import logger
from shared.utils.helpers import save_json


class SiteExplorerTask:
    """BFS web crawler for discovering pmkisan.gov.in pages."""

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose
        self._visited: set = set()
        self._pages: list = []

    async def explore(
        self,
        start_url: str = BASE_URL,
        max_depth: int = 3,
        max_pages: int = 50,
        **_
    ) -> dict:
        """
        BFS crawl of pmkisan.gov.in starting at `start_url`.
        Stays within the pmkisan.gov.in domain.

        Args:
            start_url: Starting URL (default: homepage)
            max_depth: Maximum crawl depth (default: 3)
            max_pages: Maximum pages to visit (default: 50)
        """
        logger.section(f"PM-KISAN Site Explorer — BFS Crawl")
        logger.info(f"Starting URL: {start_url}")
        logger.info(f"Max depth: {max_depth}, Max pages: {max_pages}")

        self._visited = set()
        self._pages = []
        queue = deque([(start_url, 0)])  # (url, depth)

        while queue and len(self._visited) < max_pages:
            url, depth = queue.popleft()

            if url in self._visited or depth > max_depth:
                continue

            # Filter to pmkisan.gov.in domain only
            parsed = urlparse(url)
            if parsed.netloc and "pmkisan.gov.in" not in parsed.netloc:
                logger.debug(f"Skipping external URL: {url}", self.verbose)
                continue

            self._visited.add(url)
            logger.step(f"[Depth {depth}] Crawling: {url}")

            page_data = await self._crawl_page(url)
            if page_data:
                self._pages.append(page_data)
                logger.success(f"  → {page_data['title'] or '(no title)'} ({len(page_data['links'])} links)")

                # Enqueue child links at next depth
                if depth < max_depth:
                    for link in page_data["links"]:
                        child_url = link.get("href", "")
                        if child_url and child_url not in self._visited:
                            queue.append((child_url, depth + 1))

            await asyncio.sleep(2)  # Respectful crawl delay

        # Save sitemap
        sitemap = {
            "base_url": start_url,
            "total_pages": len(self._pages),
            "max_depth": max_depth,
            "pages": self._pages,
        }

        out_path = save_json(sitemap, "output/pmkisan_sitemap.json")
        logger.success(f"\nSite exploration complete!")
        logger.info(f"  Pages visited: {len(self._pages)}")
        logger.info(f"  Sitemap saved: {out_path}")

        # Print summary
        logger.section("Discovered Pages")
        for page in self._pages:
            logger.info(f"  [{page['depth']}] {page['url'][:80]}")
            if page["title"]:
                logger.info(f"       {page['title'][:60]}")

        return {
            "task": "traverse_site",
            "total_pages": len(self._pages),
            "sitemap_file": out_path,
            "status": "completed",
        }

    async def _crawl_page(self, url: str) -> dict | None:
        """Navigate to url, extract info, return page data dict."""
        try:
            await self.browser.navigate(url)
            await asyncio.sleep(2)

            info = await self.browser.get_page_info()
            title = info.get("title", "")

            # Extract links staying within pmkisan.gov.in
            raw_links = await self.browser.get_all_links()
            links = []
            for link in raw_links:
                href = link.get("href", "")
                if not href:
                    continue
                parsed = urlparse(href)
                # Normalize relative links
                if not parsed.scheme:
                    href = urljoin(BASE_URL, href)
                # Filter to domain
                if "pmkisan.gov.in" in href:
                    # Skip binary files
                    if any(href.lower().endswith(ext) for ext in
                           (".jpg", ".jpeg", ".png", ".gif", ".ico", ".css", ".js")):
                        continue
                    links.append({
                        "text": link.get("text", "")[:60],
                        "href": href,
                        "title": link.get("title", "")[:60],
                    })

            return {
                "url": url,
                "depth": url.count("/") - 2,  # approximate from path depth
                "title": title,
                "links": links[:20],  # cap at 20 links per page
            }

        except Exception as e:
            logger.warning(f"Failed to crawl {url[:60]}: {e}")
            return None
