"""
Logging utilities with Rich-based colored output.
Banner text and color are configurable via the site config.
"""

from rich.console import Console
from rich.theme import Theme
from typing import Optional

custom_theme = Theme(
    {
        "info": "cyan",
        "success": "bold green",
        "warning": "bold yellow",
        "error": "bold red",
        "step": "bold magenta",
        "prompt": "bold white",
        "dim": "dim white",
    }
)

console = Console(theme=custom_theme)


def info(msg: str):
    console.print(f"[info]ℹ  {msg}[/info]")


def success(msg: str):
    console.print(f"[success]✓  {msg}[/success]")


def warning(msg: str):
    console.print(f"[warning]⚠  {msg}[/warning]")


def error(msg: str):
    console.print(f"[error]✗  {msg}[/error]")


def step(msg: str):
    console.print(f"[step]→  {msg}[/step]")


def debug(msg: str, verbose: bool = False):
    if verbose:
        console.print(f"[dim]   {msg}[/dim]")


def banner(lines: list[str], color: str = "green"):
    """Print a formatted banner with the given lines and color."""
    console.print(
        f"\n[bold {color}]╔══════════════════════════════════════════╗[/bold {color}]"
    )
    for line in lines[:-1]:
        console.print(f"[bold {color}]║[/bold {color}]   [bold white]{line}[/bold white]   [bold {color}]║[/bold {color}]")
    if lines:
        console.print(f"[bold {color}]║[/bold {color}]   [dim]{lines[-1]}[/dim]   [bold {color}]║[/bold {color}]")
    console.print(
        f"[bold {color}]╚══════════════════════════════════════════╝[/bold {color}]\n"
    )


def section(title: str, style: str = "green"):
    console.rule(f"[bold]{title}[/bold]", style=style)
