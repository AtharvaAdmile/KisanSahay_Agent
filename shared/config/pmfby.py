"""
PMFBY Site Configuration.

Pradhan Mantri Fasal Bima Yojana (Crop Insurance) — https://pmfby.gov.in

Site characteristics:
  - Standard page loads
  - No homepage modal
  - Modern JS framework (no ASP.NET)
  - Multiple sub-portals (LMS, WINDS, CROPIC, YES-TECH)
"""

from .base import SiteConfig, IntentDefinition, TaskHandler


class PMFBYConfig(SiteConfig):
    """Configuration for PMFBY (Pradhan Mantri Fasal Bima Yojana)."""

    @property
    def site_id(self) -> str:
        return "pmfby"

    @property
    def site_name(self) -> str:
        return "PMFBY"

    @property
    def base_url(self) -> str:
        return "https://pmfby.gov.in"

    @property
    def banner_text(self) -> list[str]:
        return [
            "PMFBY AI Agent — Crop Insurance CLI",
            "Pradhan Mantri Fasal Bima Yojana",
        ]

    @property
    def banner_color(self) -> str:
        return "cyan"

    @property
    def page_urls(self) -> dict[str, str]:
        return {
            "home": "/",
            "faq": "/faq",
            "contact": "/contact",
            "sitemap": "/sitemap",
            "feedback": "/feedback",
            "rti": "/rti",
            "help": "/help",
            "terms": "/termsCondition",
            "privacy": "/privacyPolicy",
            "copyright": "/copyrightPolicy",
            "krph": "/krph/",
            "lms": "/lms/",
            "yestech": "/yestech/",
            "winds": "/winds/",
            "cropic": "/cropic/",
            "guidelines": "/guidelines",
            "farmer_registration": "/farmerRegistrationForm",
        }

    @property
    def intent_schema(self) -> dict[str, IntentDefinition]:
        return {
            "traverse_site": IntentDefinition(
                description="Explore pages, build sitemap, list links",
                params=[],
            ),
            "apply_insurance": IntentDefinition(
                description="Fill farmer registration / crop insurance form",
                params=["state", "district", "crop", "season", "area"],
            ),
            "calculate_premium": IntentDefinition(
                description="Calculate insurance premium for a crop",
                params=["crop", "season", "state", "district", "area"],
            ),
            "check_status": IntentDefinition(
                description="Check application status using receipt/policy number",
                params=["receipt_number", "policy_id"],
            ),
            "raise_grievance": IntentDefinition(
                description="File a complaint or report crop loss via KRPH",
                params=["mobile"],
            ),
            "check_complaint": IntentDefinition(
                description="Check KRPH complaint/crop-loss intimation status",
                params=["mobile"],
            ),
            "access_lms": IntentDefinition(
                description="Register or log in to PMFBY LMS for training courses",
                params=["mobile"],
            ),
            "view_weather": IntentDefinition(
                description="View weather data on the WINDS portal",
                params=[],
            ),
            "upload_crop_photo": IntentDefinition(
                description="Upload a crop photo via the CROPIC portal",
                params=["mobile"],
            ),
            "track_cropic": IntentDefinition(
                description="Track crop photo submission status on CROPIC",
                params=["reference_id"],
            ),
            "access_yestech": IntentDefinition(
                description="Navigate to the YES-TECH yield estimation portal",
                params=[],
            ),
            "navigate_page": IntentDefinition(
                description="Navigate to a specific page (FAQ, contact, sitemap, etc.)",
                params=["page"],
            ),
            "get_info": IntentDefinition(
                description="Get information about the PMFBY scheme, documents, or eligibility",
                params=[],
            ),
            "setup_profile": IntentDefinition(
                description="Set up or update the local farmer profile for form pre-filling",
                params=[],
            ),
        }

    @property
    def intent_routes(self) -> dict[str, str]:
        return {
            "apply_insurance": "farmer_registration",
            "calculate_premium": "home",
            "check_status": "home",
            "raise_grievance": "krph",
            "check_complaint": "krph",
            "access_lms": "lms",
            "view_weather": "winds",
            "upload_crop_photo": "cropic",
            "track_cropic": "cropic",
            "access_yestech": "yestech",
            "traverse_site": "home",
            "navigate_page": "home",
            "get_info": "faq",
            "setup_profile": "home",
        }

    @property
    def task_handlers(self) -> dict[str, TaskHandler]:
        return {
            "farmer_registration": TaskHandler(
                name="farmer_registration",
                import_path="tasks.pmfby.farmer_registration",
                class_name="FarmerRegistrationTask",
            ),
            "premium_calculator": TaskHandler(
                name="premium_calculator",
                import_path="tasks.pmfby.premium_calculator",
                class_name="PremiumCalculatorTask",
            ),
            "application_status": TaskHandler(
                name="application_status",
                import_path="tasks.pmfby.application_status",
                class_name="ApplicationStatusTask",
            ),
            "grievance": TaskHandler(
                name="grievance",
                import_path="tasks.pmfby.grievance",
                class_name="GrievanceTask",
            ),
            "site_explorer": TaskHandler(
                name="site_explorer",
                import_path="tasks.pmfby.site_explorer",
                class_name="SiteExplorerTask",
            ),
            "lms_access": TaskHandler(
                name="lms_access",
                import_path="tasks.pmfby.lms_access",
                class_name="LMSAccessTask",
            ),
            "winds_access": TaskHandler(
                name="winds_access",
                import_path="tasks.pmfby.winds_access",
                class_name="WINDSAccessTask",
            ),
            "cropic_access": TaskHandler(
                name="cropic_access",
                import_path="tasks.pmfby.cropic_access",
                class_name="CROPICAccessTask",
            ),
            "yestech_access": TaskHandler(
                name="yestech_access",
                import_path="tasks.pmfby.yestech_access",
                class_name="YESTECHAccessTask",
            ),
        }

    @property
    def system_prompt(self) -> str:
        return """You are an intent classifier for the PMFBY (Pradhan Mantri Fasal Bima Yojana) crop insurance website agent.

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

    @property
    def few_shot_examples(self) -> list[dict]:
        return [
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

    @property
    def sensitive_keys(self) -> set[str]:
        return {
            "personal.aadhaar",
            "bank.account_no",
            "portals.lms_password",
            "portals.cropic_password",
            "portals.winds_password",
        }

    @property
    def navigate_timeout(self) -> int:
        return 30000

    @property
    def navigate_delay(self) -> float:
        return 3.0

    @property
    def has_homepage_modal(self) -> bool:
        return False

    @property
    def uses_aspnet_postback(self) -> bool:
        return False

    @property
    def has_language_selector(self) -> bool:
        return False


PMFBY_CONFIG = PMFBYConfig()
