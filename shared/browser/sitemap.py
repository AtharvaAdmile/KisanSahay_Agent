"""
Sitemap — Page identification and routing for navigation recovery.

Provides page matching utilities used by Navigator for auto-recovery
when a step fails due to being on the wrong page.
"""

from ..config.base import SiteConfig


class Sitemap:
    """Manages page identification and routing based on site configuration."""

    def __init__(self, config: SiteConfig):
        self.config = config
        self._page_urls = config.page_urls
        self._intent_routes = config.intent_routes
        self._base_url = config.base_url

    def find_route(self, intent: str) -> str:
        """Return the target URL for a given intent."""
        return self.config.get_target_page(intent)

    def match_current_page(self, url: str) -> str:
        """
        Identify which known page the agent is currently on from the URL.
        Returns the page key (e.g., 'register') or 'unknown'.
        """
        url_lower = url.lower()
        for key, known_url in self._page_urls.items():
            path = known_url.lower().split(self._base_url.lower())[-1]
            if path and path != "/" and path in url_lower:
                return key
        if self._base_url.lower() in url_lower:
            return "home"
        return "unknown"

    def describe_site(self) -> str:
        """Return a text description of the site pages."""
        lines = [f"{self.config.site_name} site pages:"]
        for key, url in self._page_urls.items():
            full_url = url if url.startswith("http") else f"{self._base_url}{url}"
            lines.append(f"  {key:28s} → {full_url}")
        return "\n".join(lines)
