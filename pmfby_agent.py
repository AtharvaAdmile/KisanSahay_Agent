#!/usr/bin/env python3
"""
PMFBY AI Agent — CLI Entry Point
Pradhan Mantri Fasal Bima Yojana (Crop Insurance) Browser Automation Agent.

Usage:
    python pmfby_agent.py --prompt "help me fill the application form"
    python pmfby_agent.py --prompt "check my status using ABC123" --no-headless
    python pmfby_agent.py --prompt "explore the site" --verbose
"""

import argparse
import asyncio
import sys
import os

# Ensure project root is in the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from agent.intent_parser import IntentParser
from agent.planner import create_plan
from agent.executor import Executor
from browser.controller import PMFBYBrowser
from utils import logger
from utils.helpers import display_result, save_json


async def run(prompt: str, headless: bool = True, verbose: bool = False) -> dict:
    """Main agent loop: parse → plan → execute → report."""

    # Step 1: Parse intent
    logger.section("Intent Classification")
    parser = IntentParser(verbose=verbose)
    intent_result = parser.parse(prompt)

    intent = intent_result["intent"]
    params = intent_result["params"]
    confidence = intent_result["confidence"]

    if confidence < 0.4:
        logger.warning(
            f"Low confidence ({confidence:.0%}) on intent '{intent}'. "
            "The agent may not perform the desired action."
        )

    # Step 2: Create plan
    logger.section("Action Planning")
    plan = create_plan(intent, params)

    # Step 3: Launch browser and execute
    browser = PMFBYBrowser(headless=headless, verbose=verbose)
    results = {}

    try:
        await browser.launch()
        executor = Executor(browser, verbose=verbose)
        results = await executor.execute(plan)

        # Take final screenshot
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

    # Step 4: Display results
    logger.section("Results")
    if results:
        display_result(results)
        # Save results to JSON
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
        description="PMFBY AI Agent — Crop Insurance Website Automation",
        epilog=(
            "Examples:\n"
            '  python pmfby_agent.py --prompt "help me fill the application form"\n'
            '  python pmfby_agent.py --prompt "check status using receipt ABC123" --no-headless\n'
            '  python pmfby_agent.py --prompt "calculate premium for wheat in Kharif"\n'
            '  python pmfby_agent.py --prompt "explore the pmfby site" --verbose\n'
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--prompt", "-p",
        required=True,
        help="Natural language task description (e.g., 'fill the insurance application')",
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

    args = parser.parse_args()

    logger.banner()
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
