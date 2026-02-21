"""
PM-KISAN Site Configuration.

Pradhan Mantri Kisan Samman Nidhi — https://pmkisan.gov.in

Site characteristics:
  - Slow page loads (15-25 seconds)
  - Homepage modal popup (BharatVistaar promo)
  - ASP.NET WebForms with __doPostBack
  - Multi-language support via #ddlLanguage
"""

from .base import SiteConfig, IntentDefinition, TaskHandler


class PMKISANConfig(SiteConfig):
    """Configuration for PM-KISAN (Pradhan Mantri Kisan Samman Nidhi)."""

    @property
    def site_id(self) -> str:
        return "pmkisan"

    @property
    def site_name(self) -> str:
        return "PM-KISAN"

    @property
    def base_url(self) -> str:
        return "https://pmkisan.gov.in"

    @property
    def banner_text(self) -> list[str]:
        return [
            "PM-KISAN AI Agent — Kisan Samman CLI",
            "Pradhan Mantri Kisan Samman Nidhi",
        ]

    @property
    def banner_color(self) -> str:
        return "green"

    @property
    def page_urls(self) -> dict[str, str]:
        return {
            "home": "/",
            "sitemap_page": "/Sitemap.aspx",
            "register": "/RegistrationFormupdated.aspx",
            "know_your_status": "/BeneficiaryStatus_New.aspx",
            "farmer_status": "/FarmerStatus.aspx",
            "know_reg_no": "/KnowYour_Registration.aspx",
            "edit_registration": "/SearchSelfRegisterfarmerDetailsnewUpdated.aspx",
            "beneficiary_list": "/Rpt_BeneficiaryStatus_pub.aspx",
            "ekyc": "/aadharekyc.aspx",
            "grievance": "/Grievance.aspx",
            "kcc_form": "/Documents/Kcc.pdf",
            "kcc_circular": "/Documents/finalKCCCircular.pdf",
            "aif_guidelines": (
                "/Documents/Operational%20Guidelines%20of%20Financing%20Facility"
                "%20under%20Agriculture%20Infrastructure%20Fund.pdf"
            ),
            "about": "/about.aspx",
            "guidelines": "/Operational_Guidelines.aspx",
            "circulars": "/CircularsLetter.aspx",
            "ekyc_info": "/eKYCProcess.aspx",
        }

    @property
    def intent_schema(self) -> dict[str, IntentDefinition]:
        return {
            "traverse_site": IntentDefinition(
                description="Explore the PM-KISAN website, build a sitemap, list available features",
                params=[],
            ),
            "register_pmkisan": IntentDefinition(
                description="New farmer self-registration for PM-KISAN scheme",
                params=["aadhaar", "mobile", "state", "district", "block", "village"],
            ),
            "check_beneficiary_status": IntentDefinition(
                description="Check PM-KISAN beneficiary status by registration number (Know Your Status)",
                params=["registration_no", "mobile"],
            ),
            "check_farmer_status": IntentDefinition(
                description="Check status of self-registered farmer using Aadhaar number",
                params=["aadhaar"],
            ),
            "know_registration_number": IntentDefinition(
                description="Find PM-KISAN registration number using mobile or Aadhaar",
                params=["mobile", "aadhaar"],
            ),
            "edit_registration": IntentDefinition(
                description="Edit or update existing PM-KISAN self-registration details",
                params=["aadhaar"],
            ),
            "get_beneficiary_list": IntentDefinition(
                description="Get list of PM-KISAN beneficiaries by geographical location",
                params=["state", "district", "sub_district", "block", "village"],
            ),
            "do_ekyc": IntentDefinition(
                description="Perform eKYC (Aadhaar authentication) for PM-KISAN",
                params=["aadhaar", "mobile"],
            ),
            "raise_helpdesk": IntentDefinition(
                description="Register a helpdesk query/complaint for PM-KISAN",
                params=["registration_no", "mobile"],
            ),
            "check_query_status": IntentDefinition(
                description="Check status of a helpdesk query/complaint",
                params=["registration_no", "mobile"],
            ),
            "access_kcc": IntentDefinition(
                description="Get information about Kisan Credit Card scheme, download KCC application form",
                params=[],
            ),
            "access_aif": IntentDefinition(
                description="Get information about Agriculture Infrastructure Fund, download AIF guidelines",
                params=[],
            ),
            "navigate_page": IntentDefinition(
                description="Navigate to a specific PM-KISAN page",
                params=["page_name"],
            ),
            "get_info": IntentDefinition(
                description="Get information about PM-KISAN scheme, eligibility, benefits",
                params=[],
            ),
            "setup_profile": IntentDefinition(
                description="Set up local farmer profile for form auto-filling",
                params=[],
            ),
        }

    @property
    def intent_routes(self) -> dict[str, str]:
        return {
            "register_pmkisan": "register",
            "check_beneficiary_status": "know_your_status",
            "check_farmer_status": "farmer_status",
            "know_registration_number": "know_reg_no",
            "edit_registration": "edit_registration",
            "get_beneficiary_list": "beneficiary_list",
            "do_ekyc": "ekyc",
            "raise_helpdesk": "grievance",
            "check_query_status": "grievance",
            "access_kcc": "home",
            "access_aif": "home",
            "traverse_site": "sitemap_page",
            "navigate_page": "home",
            "get_info": "home",
            "setup_profile": "home",
        }

    @property
    def task_handlers(self) -> dict[str, TaskHandler]:
        return {
            "registration": TaskHandler(
                name="registration",
                import_path="tasks.pmkisan.registration",
                class_name="FarmerRegistrationTask",
            ),
            "status_check": TaskHandler(
                name="status_check",
                import_path="tasks.pmkisan.status_check",
                class_name="StatusCheckTask",
            ),
            "beneficiary_list": TaskHandler(
                name="beneficiary_list",
                import_path="tasks.pmkisan.beneficiary_list",
                class_name="BeneficiaryListTask",
            ),
            "helpdesk": TaskHandler(
                name="helpdesk",
                import_path="tasks.pmkisan.helpdesk",
                class_name="HelpdeskTask",
            ),
            "kcc_access": TaskHandler(
                name="kcc_access",
                import_path="tasks.pmkisan.kcc_access",
                class_name="KCCAccessTask",
            ),
            "aif_access": TaskHandler(
                name="aif_access",
                import_path="tasks.pmkisan.aif_access",
                class_name="AIFAccessTask",
            ),
            "site_explorer": TaskHandler(
                name="site_explorer",
                import_path="tasks.pmkisan.site_explorer",
                class_name="SiteExplorerTask",
            ),
        }

    @property
    def system_prompt(self) -> str:
        return """You are an intent classifier for the PM-KISAN (Pradhan Mantri Kisan Samman Nidhi) Government of India portal.

Your task: Given a user's natural language request, return a JSON object with:
  - intent: one of the intent names listed below
  - params: a dict of extracted parameter values (only include if clearly stated)
  - confidence: float 0-1 (your confidence in this classification)

## Available Intents

| Intent | When to Use |
|---|---|
| traverse_site | Explore site, list features, search for pages |
| register_pmkisan | New farmer registration for PM-KISAN |
| check_beneficiary_status | Check status using registration number |
| check_farmer_status | Check status of self-registered farmer using Aadhaar |
| know_registration_number | Find registration number via mobile/Aadhaar |
| edit_registration | Update/correct existing registration |
| get_beneficiary_list | Browse beneficiaries by state/district/block/village |
| do_ekyc | Perform eKYC / Aadhaar authentication |
| raise_helpdesk | Register a helpdesk/dispute query |
| check_query_status | Check status of helpdesk query |
| access_kcc | Kisan Credit Card info/form |
| access_aif | Agriculture Infrastructure Fund info/guidelines |
| navigate_page | Go to a specific page |
| get_info | Information about PM-KISAN, eligibility, benefits |
| setup_profile | Set up local profile |

## Response Format (JSON ONLY — no markdown, no explanation)

{
  "intent": "<intent_name>",
  "params": {
    "aadhaar": "...",
    "mobile": "...",
    "registration_no": "...",
    "state": "...",
    "district": "...",
    "block": "...",
    "village": "..."
  },
  "confidence": 0.95
}

Only include params that are explicitly stated in the user's message.
Omit params that are not mentioned (do not guess)."""

    @property
    def few_shot_examples(self) -> list[dict]:
        return [
            {
                "user": "I want to register for PM KISAN scheme",
                "response": {"intent": "register_pmkisan", "params": {}, "confidence": 0.97},
            },
            {
                "user": "Check my PM-KISAN beneficiary status, my registration number is 1234567890",
                "response": {
                    "intent": "check_beneficiary_status",
                    "params": {"registration_no": "1234567890"},
                    "confidence": 0.98,
                },
            },
            {
                "user": "What is my PM KISAN registration number? My mobile is 9876543210",
                "response": {
                    "intent": "know_registration_number",
                    "params": {"mobile": "9876543210"},
                    "confidence": 0.96,
                },
            },
            {
                "user": "Get list of beneficiaries in Maharashtra, Pune district, Haveli block",
                "response": {
                    "intent": "get_beneficiary_list",
                    "params": {"state": "Maharashtra", "district": "Pune", "block": "Haveli"},
                    "confidence": 0.95,
                },
            },
            {
                "user": "Download the KCC form for Kisan Credit Card",
                "response": {"intent": "access_kcc", "params": {}, "confidence": 0.96},
            },
            {
                "user": "I want to raise a complaint/grievance about PM-KISAN payment not received",
                "response": {"intent": "raise_helpdesk", "params": {}, "confidence": 0.94},
            },
            {
                "user": "Check status of self registered farmer with aadhaar 123456789012",
                "response": {
                    "intent": "check_farmer_status",
                    "params": {"aadhaar": "123456789012"},
                    "confidence": 0.95,
                },
            },
            {
                "user": "Tell me about AIF Agriculture Infrastructure Fund",
                "response": {"intent": "access_aif", "params": {}, "confidence": 0.93},
            },
        ]

    @property
    def navigate_timeout(self) -> int:
        return 45000

    @property
    def navigate_delay(self) -> float:
        return 5.0

    @property
    def has_homepage_modal(self) -> bool:
        return True

    @property
    def uses_aspnet_postback(self) -> bool:
        return True

    @property
    def has_language_selector(self) -> bool:
        return True


PMKISAN_CONFIG = PMKISANConfig()
