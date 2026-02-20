"""
Logging utilities with Rich-based colored output for the PMFBY Agent CLI.
"""

from rich.console import Console
from rich.theme import Theme

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


def banner():
    console.print(
        "\n[bold cyan]╔══════════════════════════════════════════╗[/bold cyan]"
    )
    console.print(
        "[bold cyan]║[/bold cyan]   [bold white]PMFBY AI Agent[/bold white] — Crop Insurance CLI   [bold cyan]║[/bold cyan]"
    )
    console.print(
        "[bold cyan]║[/bold cyan]   [dim]Pradhan Mantri Fasal Bima Yojana[/dim]      [bold cyan]║[/bold cyan]"
    )
    console.print(
        "[bold cyan]╚══════════════════════════════════════════╝[/bold cyan]\n"
    )


def section(title: str):
    console.rule(f"[bold]{title}[/bold]", style="cyan")
