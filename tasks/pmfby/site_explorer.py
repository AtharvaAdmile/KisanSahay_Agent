"""
Site Explorer task handler.
Revised based on live exploration — 2026-02-20.

STRATEGY: BFS traversal starting from homepage. Filters to internal PMFBY links.
Many internal "links" are React card triggers (JS events), so the real crawlable
pages are the traditional href-based ones listed in footer and nav.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import asyncio
from collections import deque
from urllib.parse import urlparse

from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import save_json, display_table

# Known crawlable PMFBY pages (confirmed during live exploration)
KNOWN_PAGES = [
    "/",
    "/aboutUs",
    "/faq",
    "/contact",
    "/feedback",
    "/rti",
    "/help",
    "/sitemap",
    "/termsCondition",
    "/privacyPolicy",
    "/copyrightPolicy",
    "/guidelines",
    "/tender",
    "/gallery",
    "/compendium-files",
]


class SiteExplorerTask:
    """BFS exploration of PMFBY site to build a structured sitemap."""

    BASE_DOMAIN = "pmfby.gov.in"
    MAX_DEPTH = 2
    MAX_PAGES = 20  # conservative to avoid overloading the server

    def __init__(self, browser: Browser, verbose: bool = False):
        self.browser = browser
        self.verbose = verbose
        self.visited = set()
        self.sitemap = []

    async def explore(self, **kwargs) -> dict:
        """
        BFS exploration starting from homepage.
        Uses known pages list + discovered links for traversal.
        """
        logger.section("Site Explorer — BFS Traversal")
        logger.info(f"Max depth: {self.MAX_DEPTH} | Max pages: {self.MAX_PAGES}")
        logger.info("Starting from known key pages + BFS discovery.\n")

        # Seed queue with known pages
        start_url = "https://pmfby.gov.in/"
        queue = deque([(start_url, 0)])
        self.visited.add(self._normalize_url(start_url))

        while queue and len(self.sitemap) < self.MAX_PAGES:
            url, depth = queue.popleft()
            if depth > self.MAX_DEPTH:
                continue

            try:
                await self.browser.navigate(url)
                await self.browser.wait_for_network_idle(timeout=6000)

                page_info = await self.browser.get_page_info()
                links = await self.browser.get_all_links()

                # Filter to real internal HREF links (not JS event handlers)
                internal_links = [
                    l for l in links
                    if self._is_crawlable(l.get("href", ""))
                ]

                entry = {
                    "url": page_info["url"],
                    "title": page_info["title"][:80],
                    "depth": depth,
                    "links_found": len(internal_links),
                }
                self.sitemap.append(entry)
                logger.success(
                    f"[Depth {depth}] {page_info['title'][:50]} "
                    f"— {len(internal_links)} links"
                )

                if depth < self.MAX_DEPTH:
                    for link in internal_links:
                        normalized = self._normalize_url(link.get("href", ""))
                        if normalized and normalized not in self.visited:
                            self.visited.add(normalized)
                            queue.append((link["href"], depth + 1))

            except Exception as e:
                logger.warning(f"  Skipping {url}: {e}")
                continue

        # Also add known pages not yet visited
        if len(self.sitemap) < self.MAX_PAGES:
            for path in KNOWN_PAGES:
                full_url = f"https://pmfby.gov.in{path}"
                normalized = self._normalize_url(full_url)
                if normalized not in self.visited:
                    self.visited.add(normalized)
                    try:
                        await self.browser.navigate(full_url)
                        await asyncio.sleep(2)
                        page_info = await self.browser.get_page_info()
                        self.sitemap.append({
                            "url": page_info["url"],
                            "title": page_info["title"][:80],
                            "depth": 1,
                            "links_found": 0,
                            "source": "known_pages",
                        })
                        logger.success(f"[Known] {page_info['title'][:50]}")
                    except Exception as e:
                        logger.warning(f"  Could not fetch {full_url}: {e}")

        logger.section("Sitemap Results")
        display_table(self.sitemap, title=f"Discovered {len(self.sitemap)} pages")

        try:
            out_path = save_json(
                {"pages": self.sitemap, "total": len(self.sitemap)},
                "output/sitemap.json",
            )
            logger.info(f"Sitemap saved: {out_path}")
        except Exception:
            pass

        return {
            "task": "site_explorer",
            "pages_discovered": len(self.sitemap),
            "sitemap": self.sitemap,
        }

    async def extract_faq(self, **kwargs) -> dict:
        """Extract FAQ content from the /faq page."""
        logger.section("Extracting FAQ Content")

        current_url = self.browser.page.url
        if "/faq" not in current_url.lower():
            await self.browser.navigate("https://pmfby.gov.in/faq")
            await self.browser.wait_for_network_idle(timeout=6000)

        faq_items = []
        page = self.browser.page

        # Try accordion/panel patterns
        selectors_pairs = [
            (".panel-title", ".panel-body"),
            (".accordion-button, .accordion-header", ".accordion-body, .accordion-collapse"),
            (".faq-question", ".faq-answer"),
            ("dt", "dd"),
            ("h4, h5", "p"),
        ]

        for q_sel, a_sel in selectors_pairs:
            questions = await self.browser.get_all_text(q_sel)
            answers = await self.browser.get_all_text(a_sel)
            if questions:
                for i, q in enumerate(questions):
                    a = answers[i] if i < len(answers) else ""
                    faq_items.append({
                        "question": q.strip()[:200],
                        "answer": a.strip()[:500],
                    })
                break

        if not faq_items:
            body = await self.browser.get_text("main, .content, body")
            faq_items.append({"question": "FAQ Page", "answer": body[:2000]})

        logger.success(f"Extracted {len(faq_items)} FAQ items")
        try:
            save_json({"faq": faq_items}, "output/faq.json")
        except Exception:
            pass

        return {"task": "extract_faq", "items_found": len(faq_items), "faq": faq_items}

    def _normalize_url(self, url: str) -> str:
        """Normalize URL for deduplication."""
        try:
            parsed = urlparse(url)
            path = parsed.path.rstrip("/") or "/"
            return f"{parsed.scheme}://{parsed.netloc}{path}"
        except Exception:
            return ""

    def _is_crawlable(self, url: str) -> bool:
        """Check if URL is a real internal page (not JS event or external)."""
        try:
            parsed = urlparse(url)
            if self.BASE_DOMAIN not in parsed.netloc and not url.startswith("/"):
                return False
            # Skip anchors, downloads, external subdomains that are separate apps
            if any(url.endswith(ext) for ext in (".pdf", ".jpg", ".png", ".zip", ".doc")):
                return False
            if "javascript:" in url or url.endswith("#") or url == "":
                return False
            if any(sub in url for sub in ["/krph/", "/lms/", "/yestech/", "/winds/", "/cropic/"]):
                return False  # Separate SPAs — don't crawl
            return True
        except Exception:
            return False
