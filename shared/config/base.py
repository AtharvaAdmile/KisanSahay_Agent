"""
SiteConfig — Base configuration class for government scheme agents.

Each site (PMKISAN, PMFBY) extends this class with:
  - URLs and page mappings
  - Intent schemas and routing
  - Task handler registrations
  - Browser behavior flags
  - Profile paths and sensitive keys
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any


@dataclass
class IntentDefinition:
    """Definition of a single intent with its parameters."""
    description: str
    params: list[str] = field(default_factory=list)


@dataclass
class TaskHandler:
    """Registration for a task handler."""
    name: str
    import_path: str
    class_name: str


class SiteConfig(ABC):
    """Abstract base class for site-specific configuration."""

    @property
    @abstractmethod
    def site_id(self) -> str:
        """Unique identifier for this site (e.g., 'pmkisan', 'pmfby')."""
        pass

    @property
    @abstractmethod
    def site_name(self) -> str:
        """Human-readable site name (e.g., 'PM-KISAN')."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL for the site (e.g., 'https://pmkisan.gov.in')."""
        pass

    @property
    @abstractmethod
    def banner_text(self) -> list[str]:
        """Lines of text for the CLI banner."""
        pass

    @property
    @abstractmethod
    def banner_color(self) -> str:
        """Rich color name for the banner (e.g., 'green', 'cyan')."""
        pass

    @property
    @abstractmethod
    def page_urls(self) -> dict[str, str]:
        """Mapping of page keys to URLs (can be relative or absolute)."""
        pass

    @property
    @abstractmethod
    def intent_schema(self) -> dict[str, IntentDefinition]:
        """Mapping of intent names to their definitions."""
        pass

    @property
    @abstractmethod
    def intent_routes(self) -> dict[str, str]:
        """Mapping of intent names to page keys for navigation."""
        pass

    @property
    @abstractmethod
    def task_handlers(self) -> dict[str, TaskHandler]:
        """Mapping of handler names to their import details."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """System prompt for the intent classifier LLM."""
        pass

    @property
    @abstractmethod
    def few_shot_examples(self) -> list[dict]:
        """Few-shot examples for intent classification."""
        pass

    @property
    def profile_path(self) -> Path:
        """Path to the user profile JSON file."""
        return Path.home() / f".{self.site_id}_agent" / "profile.json"

    @property
    def sensitive_keys(self) -> set[str]:
        """Keys that should be masked in logs and stored securely."""
        return {"personal.aadhaar", "bank.account_no"}

    @property
    def keyring_service(self) -> str:
        """Service name for keyring storage."""
        return f"{self.site_id}_agent"

    @property
    def navigate_timeout(self) -> int:
        """Timeout for page navigation in milliseconds."""
        return 30000

    @property
    def navigate_delay(self) -> float:
        """Delay after navigation in seconds."""
        return 3.0

    @property
    def has_homepage_modal(self) -> bool:
        """Whether the site has a modal popup on homepage load."""
        return False

    @property
    def uses_aspnet_postback(self) -> bool:
        """Whether the site uses ASP.NET __doPostBack for dropdowns."""
        return False

    @property
    def has_language_selector(self) -> bool:
        """Whether the site has a language dropdown."""
        return False

    def get_url(self, key: str) -> str:
        """Get a full URL for a page key."""
        url = self.page_urls.get(key, "")
        if url.startswith("http"):
            return url
        return f"{self.base_url}{url}"

    def get_target_page(self, intent: str) -> str:
        """Get the target URL for an intent."""
        page_key = self.intent_routes.get(intent, "home")
        return self.get_url(page_key)

    def get_intent_description(self, intent: str) -> str:
        """Get the description for an intent."""
        definition = self.intent_schema.get(intent)
        return definition.description if definition else "Unknown intent"
