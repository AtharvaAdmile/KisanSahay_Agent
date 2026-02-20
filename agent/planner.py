"""
Action planner: maps classified intents into executable step sequences.
Each step is a dict with an action type and associated parameters.
"""

from utils import logger

# Page URL mappings for navigation
PAGE_URLS = {
    "faq":             "/faq",
    "contact":         "/contact",
    "sitemap":         "/sitemap",
    "feedback":        "/feedback",
    "rti":             "/rti",
    "help":            "/help",
    "terms":           "/termsCondition",
    "privacy":         "/privacyPolicy",
    "copyright":       "/copyrightPolicy",
    # Sub-portals
    "krph":            "/krph/",
    "lms":             "/lms/",
    "yestech":         "/yestech/",
    "winds":           "/winds/",
    "cropic":          "/cropic/",
    "guidelines":      "/guidelines",
    "grievance":       "/krph/",
}


def plan_traverse_site(params: dict) -> list[dict]:
    """Plan for exploring the entire site."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/"},
        {"action": "task", "handler": "site_explorer", "method": "explore"},
    ]


def plan_apply_insurance(params: dict) -> list[dict]:
    """Plan for filling the farmer registration form."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/farmerRegistrationForm"},
        {"action": "task", "handler": "farmer_registration", "method": "fill_form", "params": params},
    ]


def plan_calculate_premium(params: dict) -> list[dict]:
    """Plan for using the insurance premium calculator."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/"},
        {"action": "task", "handler": "premium_calculator", "method": "calculate", "params": params},
    ]


def plan_check_status(params: dict) -> list[dict]:
    """Plan for checking application status."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/"},
        {"action": "task", "handler": "application_status", "method": "check_status", "params": params},
    ]


def plan_raise_grievance(params: dict) -> list[dict]:
    """Plan for filing a crop loss grievance via KRPH."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/krph/"},
        {"action": "task", "handler": "grievance", "method": "file_grievance", "params": params},
    ]


def plan_check_complaint(params: dict) -> list[dict]:
    """Plan for checking KRPH complaint / crop-loss intimation status."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/krph/"},
        {"action": "task", "handler": "grievance", "method": "check_complaint_status", "params": params},
    ]


def plan_access_lms(params: dict) -> list[dict]:
    """Plan for accessing the LMS portal (login then browse courses)."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/lms/"},
        {"action": "task", "handler": "lms_access", "method": "login",          "params": params},
        {"action": "task", "handler": "lms_access", "method": "browse_courses", "params": params},
    ]


def plan_view_weather(params: dict) -> list[dict]:
    """Plan for viewing the WINDS weather map (no login required)."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/winds/"},
        {"action": "task", "handler": "winds_access", "method": "view_public_data", "params": params},
    ]


def plan_upload_crop_photo(params: dict) -> list[dict]:
    """Plan for uploading a crop photo via CROPIC."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/cropic/"},
        {"action": "task", "handler": "cropic_access", "method": "login",        "params": params},
        {"action": "task", "handler": "cropic_access", "method": "upload_photo", "params": params},
    ]


def plan_track_cropic(params: dict) -> list[dict]:
    """Plan for tracking crop photo submission status on CROPIC."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/cropic/"},
        {"action": "task", "handler": "cropic_access", "method": "login",         "params": params},
        {"action": "task", "handler": "cropic_access", "method": "track_status",  "params": params},
    ]


def plan_access_yestech(params: dict) -> list[dict]:
    """Plan for navigating to the YES-TECH portal."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/yestech/"},
        {"action": "task", "handler": "yestech_access", "method": "navigate", "params": params},
    ]


def plan_setup_profile(params: dict) -> list[dict]:
    """No browser needed — just trigger the interactive profile wizard."""
    return [
        {"action": "setup_profile"},
    ]


def plan_navigate_page(params: dict) -> list[dict]:
    """Plan for navigating to a specific page."""
    page = params.get("page", "").lower()
    url = PAGE_URLS.get(page, f"/{page}")
    return [
        {"action": "navigate", "url": f"https://pmfby.gov.in{url}"},
        {"action": "extract_page_info"},
    ]


def plan_get_info(params: dict) -> list[dict]:
    """Plan for getting general scheme information."""
    return [
        {"action": "navigate", "url": "https://pmfby.gov.in/faq"},
        {"action": "task", "handler": "site_explorer", "method": "extract_faq"},
    ]


# Intent → planner mapping
PLANNERS = {
    "traverse_site":     plan_traverse_site,
    "apply_insurance":   plan_apply_insurance,
    "calculate_premium": plan_calculate_premium,
    "check_status":      plan_check_status,
    "raise_grievance":   plan_raise_grievance,
    "check_complaint":   plan_check_complaint,
    "access_lms":        plan_access_lms,
    "view_weather":      plan_view_weather,
    "upload_crop_photo": plan_upload_crop_photo,
    "track_cropic":      plan_track_cropic,
    "access_yestech":    plan_access_yestech,
    "navigate_page":     plan_navigate_page,
    "get_info":          plan_get_info,
    "setup_profile":     plan_setup_profile,
}


def create_plan(intent: str, params: dict) -> list[dict]:
    """Generate an action plan for the given intent and parameters."""
    planner_fn = PLANNERS.get(intent)
    if not planner_fn:
        logger.warning(f"No planner for intent '{intent}', falling back to get_info")
        planner_fn = plan_get_info

    steps = planner_fn(params)
    logger.section("Execution Plan")
    for i, step in enumerate(steps, 1):
        action = step.get("action", "unknown")
        detail = step.get("handler", step.get("url", ""))
        logger.info(f"  Step {i}: {action} — {detail}")

    return steps
