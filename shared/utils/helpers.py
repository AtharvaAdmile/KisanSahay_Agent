"""
Helper utilities for CLI interaction, JSON output, and data display.
"""

import json
import getpass
from pathlib import Path
from tabulate import tabulate


def prompt_user(question: str, secret: bool = False, default: str = "") -> str:
    """Prompt the user for input via CLI. Uses getpass for sensitive fields."""
    suffix = f" [{default}]" if default else ""
    full_prompt = f"  📝 {question}{suffix}: "
    if secret:
        value = getpass.getpass(full_prompt)
    else:
        value = input(full_prompt)
    return value.strip() or default


def prompt_confirm(question: str, default: bool = True) -> bool:
    """Yes/no confirmation prompt."""
    suffix = "[Y/n]" if default else "[y/N]"
    answer = input(f"  ❓ {question} {suffix}: ").strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")


def wait_for_continue(reason: str = "") -> None:
    """
    Hand off control to user. Blocks until user types 'continue'.
    Used for CAPTCHA/OTP handoff.
    """
    if reason:
        print(f"\n  🔒 {reason}")
    print("  ⏸  The browser is now under YOUR control.")
    print("     Complete the required action, then type 'continue' here.\n")
    while True:
        cmd = input("  ▶  Type 'continue' when ready: ").strip().lower()
        if cmd == "continue":
            break
        print("     Please type 'continue' to proceed.")


def save_json(data: dict, path: str) -> str:
    """Save a dict as formatted JSON to file."""
    filepath = Path(path)
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    return str(filepath)


def display_table(data: list[dict], title: str = "") -> None:
    """Pretty-print a list of dicts as a table."""
    if not data:
        print("  (no data)")
        return
    if title:
        print(f"\n  📊 {title}")
    print(tabulate(data, headers="keys", tablefmt="rounded_grid", showindex=False))
    print()


def display_result(result: dict) -> None:
    """Display a key-value result dict in a readable format."""
    if not result:
        print("  (no result)")
        return
    max_key_len = max(len(str(k)) for k in result.keys())
    for key, value in result.items():
        print(f"  {str(key).ljust(max_key_len)} : {value}")
    print()
