"""
Planner — maps intents to step-by-step action plans.
Uses site configuration for URL routing and task handler registration.
"""

from ..config.base import SiteConfig
from ..utils import logger


def create_plan(config: SiteConfig, intent: str, params: dict) -> list[dict]:
    """Map an intent to a sequence of actions for the executor."""
    logger.info(f"Building plan for intent: {intent}")

    planners = _get_planners(config)
    planner_fn = planners.get(intent, _plan_get_info)
    plan = planner_fn(config, params)

    logger.info(f"Plan created: {len(plan)} step(s)")
    for i, step in enumerate(plan, 1):
        action = step.get("action", "?")
        detail = step.get("url") or step.get("handler") or step.get("selector", "")
        logger.debug(f"  {i}. {action}: {detail}", verbose=True)

    return plan


def _get_planners(config: SiteConfig) -> dict:
    """Get planner functions indexed by intent name."""
    return {
        "traverse_site": _plan_traverse_site,
        "navigate_page": _plan_navigate_page,
        "get_info": _plan_get_info,
        "setup_profile": _plan_setup_profile,
    }


def _plan_traverse_site(config: SiteConfig, params: dict) -> list[dict]:
    return [
        {"action": "navigate", "url": config.get_url("home")},
        {"action": "dismiss_modal"},
        {
            "action": "task",
            "handler": "site_explorer",
            "method": "explore",
            "params": {**params, "start_url": config.get_url("home")},
        },
    ]


def _plan_navigate_page(config: SiteConfig, params: dict) -> list[dict]:
    page_name = params.get("page_name", params.get("page", "")).lower()
    url = config.get_url(page_name) if page_name else config.get_url("home")
    return [
        {"action": "navigate", "url": url},
        {"action": "screenshot", "filename": f"page_{page_name}"},
        {"action": "extract_page_info"},
    ]


def _plan_get_info(config: SiteConfig, params: dict) -> list[dict]:
    return [
        {"action": "navigate", "url": config.get_url("home")},
        {"action": "dismiss_modal"},
        {"action": "extract_page_info"},
        {"action": "screenshot", "filename": f"{config.site_id}_home"},
    ]


def _plan_setup_profile(config: SiteConfig, params: dict) -> list[dict]:
    return [{"action": "setup_profile"}]


def create_plan_for_intent(config: SiteConfig, intent: str, params: dict) -> list[dict]:
    """
    Create a plan for any intent, falling back to intent_routes for navigation.
    This is a more generic planner that works for site-specific intents.
    """
    target_url = config.get_target_page(intent)
    page_key = config.intent_routes.get(intent, "home")
    
    base_plan = [
        {"action": "navigate", "url": target_url},
        {"action": "screenshot", "filename": f"{page_key}_form"},
    ]
    
    handler_name = _get_handler_for_intent(config, intent)
    if handler_name:
        method_name = _get_method_for_intent(intent)
        base_plan.append({
            "action": "task",
            "handler": handler_name,
            "method": method_name,
            "params": params,
        })
    elif intent in ["register_account", "calculate_premium"]:
        if intent == "calculate_premium":
            base_plan.extend([
                {
                    "action": "click",
                    "selector": "#ciList > li.farmerCardList.card-1.newHeader__card1___3F634",
                    "vision": True,
                    "description": "Insurance Premium Calculator card button"
                },
                {"action": "wait", "seconds": 2}
            ])
        base_plan.append({"action": "agentic_loop"})
    else:
        base_plan.append({"action": "extract_page_info"})
    
    return base_plan


def _get_handler_for_intent(config: SiteConfig, intent: str) -> str | None:
    """Map an intent to a task handler name."""
    intent_to_handler = {
        "register_pmkisan": "registration",
        "check_beneficiary_status": "status_check",
        "check_farmer_status": "status_check",
        "know_registration_number": "status_check",
        "edit_registration": "registration",
        "get_beneficiary_list": "beneficiary_list",
        "raise_helpdesk": "helpdesk",
        "check_query_status": "helpdesk",
        "access_kcc": "kcc_access",
        "access_aif": "aif_access",
        "apply_insurance": "farmer_registration",
        # "calculate_premium": "premium_calculator", # Handled via generic agentic_loop now
        "check_status": "application_status",
        "raise_grievance": "grievance",
        "check_complaint": "grievance",
        "access_lms": "lms_access",
        "view_weather": "winds_access",
        "upload_crop_photo": "cropic_access",
        "track_cropic": "cropic_access",
        "access_yestech": "yestech_access",
    }
    return intent_to_handler.get(intent)


def _get_method_for_intent(intent: str) -> str:
    """Map an intent to a task handler method name."""
    intent_to_method = {
        "register_pmkisan": "fill_form",
        "check_beneficiary_status": "check_beneficiary_status",
        "check_farmer_status": "check_farmer_status",
        "know_registration_number": "know_registration_number",
        "edit_registration": "edit_registration",
        "get_beneficiary_list": "get_list",
        "raise_helpdesk": "raise_query",
        "check_query_status": "check_status",
        "access_kcc": "access_kcc",
        "access_aif": "access_aif",
        "apply_insurance": "fill_form",
        # "calculate_premium": "calculate", # Handled via generic agentic_loop now
        "check_status": "check_status",
        "raise_grievance": "file_grievance",
        "check_complaint": "check_complaint_status",
        "access_lms": "login",
        "view_weather": "view_public_data",
        "upload_crop_photo": "login",
        "track_cropic": "login",
        "access_yestech": "navigate",
    }
    return intent_to_method.get(intent, "execute")
