#!/usr/bin/env python3
"""
PM-KISAN AI Agent — CLI Entry Point
Pradhan Mantri Kisan Samman Nidhi Browser Automation Agent.

Usage:
    python pmkisan_agent.py --prompt "register for PM-KISAN"
    python pmkisan_agent.py --prompt "check my beneficiary status" --no-headless
    python pmkisan_agent.py --prompt "download KCC form" --verbose
    python pmkisan_agent.py --setup-profile
"""

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from shared.config.pmkisan import PMKISAN_CONFIG
from shared.agent.intent_parser import IntentParser
from shared.agent.planner import create_plan_for_intent
from shared.agent.executor import Executor
from shared.browser.controller import Browser
from shared.utils import logger
from shared.utils.helpers import display_result, save_json
from shared.utils.user_profile import UserProfile


async def run(prompt: str, headless: bool = True, verbose: bool = False) -> dict:
    """Main agent loop: parse → plan → execute → report."""
    config = PMKISAN_CONFIG

    logger.section("Intent Classification", style=config.banner_color)
    parser = IntentParser(config, verbose=verbose)
    intent_result = parser.parse(prompt)

    intent = intent_result["intent"]
    params = intent_result["params"]
    confidence = intent_result["confidence"]

    if confidence < 0.4:
        logger.warning(
            f"Low confidence ({confidence:.0%}) on intent '{intent}'. "
            "The agent may not perform the desired action."
        )

    profile = UserProfile(
        profile_path=config.profile_path,
        sensitive_keys=config.sensitive_keys,
        keyring_service=config.keyring_service,
    )
    if not profile.is_empty():
        profile_params = profile.to_params()
        merged = {**profile_params, **params}
        if verbose:
            new_fields = {k: v for k, v in profile_params.items() if k not in params}
            if new_fields:
                logger.info(f"Pre-filled from profile: {list(new_fields.keys())}")
        params = merged
        intent_result["params"] = params
    else:
        logger.debug("No profile found — run with --setup-profile to save your details.", verbose)

    logger.section("Action Planning", style=config.banner_color)
    plan = create_plan_for_intent(config, intent, params)

    browser = Browser(config, headless=headless, verbose=verbose)
    results = {}

    try:
        await browser.launch()
        executor = Executor(browser, config, verbose=verbose)
        executor.set_intent(intent)
        results = await executor.execute(plan)

        try:
            ss_path = await browser.screenshot("final_result")
            results["final_screenshot"] = ss_path
        except Exception:
            pass

    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
    except Exception as e:
        logger.error(f"Execution failed: {e}")
        results["error"] = str(e)
    finally:
        await browser.close()

    logger.section("Results", style=config.banner_color)
    if results:
        display_result(results)
        try:
            out_path = save_json(results, "output/last_run.json")
            logger.info(f"Results saved to: {out_path}")
        except Exception:
            pass
    else:
        logger.info("No structured results returned.")

    return results


def main():
    parser = argparse.ArgumentParser(
        description="PM-KISAN AI Agent — Kisan Samman Nidhi Website Automation",
        epilog=(
            "Examples:\n"
            '  python pmkisan_agent.py --prompt "register for PM-KISAN"\n'
            '  python pmkisan_agent.py --prompt "check my beneficiary status" --no-headless\n'
            '  python pmkisan_agent.py --prompt "get beneficiary list for Maharashtra, Pune district"\n'
            '  python pmkisan_agent.py --prompt "download KCC form" --verbose\n'
            '  python pmkisan_agent.py --setup-profile\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--prompt", "-p",
        required=False,
        default=None,
        help="Natural language task description",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        default=False,
        help="Run browser in visible (headed) mode for debugging or manual steps",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Enable verbose/debug output",
    )
    parser.add_argument(
        "--setup-profile",
        action="store_true",
        default=False,
        help="Interactively set up your farmer profile for form auto-filling",
    )

    args = parser.parse_args()

    if args.setup_profile:
        logger.banner(PMKISAN_CONFIG.banner_text, PMKISAN_CONFIG.banner_color)
        from shared.utils.user_profile import run_setup_wizard
        run_setup_wizard(
            profile_path=PMKISAN_CONFIG.profile_path,
            sensitive_keys=PMKISAN_CONFIG.sensitive_keys,
            keyring_service=PMKISAN_CONFIG.keyring_service,
            site_name=PMKISAN_CONFIG.site_name,
            include_crop_fields=False,
            include_portal_credentials=False,
        )
        return

    if not args.prompt:
        parser.error("--prompt is required unless --setup-profile is specified")

    logger.banner(PMKISAN_CONFIG.banner_text, PMKISAN_CONFIG.banner_color)
    logger.info(f"Prompt: \"{args.prompt}\"")
    logger.info(f"Mode:   {'Headed (visible)' if args.no_headless else 'Headless'}")
    logger.info(f"Verbose: {args.verbose}\n")

    headless = not args.no_headless

    try:
        asyncio.run(run(args.prompt, headless=headless, verbose=args.verbose))
    except KeyboardInterrupt:
        logger.warning("\nAgent terminated by user.")
        sys.exit(1)


if __name__ == "__main__":
    main()
