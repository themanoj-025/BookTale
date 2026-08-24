"""
utils.py - CLI utility functions using the Rich library
"""

import os
import re
from datetime import datetime

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

console = Console()


def clear() -> None:
    """Clear the terminal screen safely via subprocess."""
    import subprocess

    cmd = "cls" if os.name == "nt" else "clear"
    subprocess.run([cmd], check=False, shell=False)


def header(title: str) -> None:
    """Display a styled header."""
    console.print()
    console.rule(f"[bold cyan]{title}[/bold cyan]", style="cyan")
    console.print()


def pause() -> None:
    """Wait for user to press Enter."""
    console.print("\n[yellow]  Press Enter to continue...[/yellow]")
    input()


def confirm(prompt_text: str) -> bool:
    """Ask for a yes/no confirmation."""
    return Confirm.ask(f"  {prompt_text}", default=False)


def validate_email(email: str) -> bool:
    """Validate email format."""
    return bool(re.match(r"^[\w\.\+\-]+@[\w\-]+\.[a-z]{2,}$", email, re.IGNORECASE))


def validate_phone(phone: str) -> bool:
    """Validate phone number format."""
    return bool(re.match(r"^\+?[\d\s\-]{7,15}$", phone))


def validate_isbn(isbn: str) -> bool:
    """Validate ISBN-10 or ISBN-13 format."""
    clean = isbn.replace("-", "").replace(" ", "")
    return len(clean) in (10, 13) and clean.isdigit()


def format_date(iso_str: str) -> str:
    """Format ISO date string to human-readable format."""
    try:
        return datetime.fromisoformat(iso_str).strftime("%d %b %Y %H:%M")
    except Exception:
        return iso_str


def colored(text: str, code: str) -> str:
    """Simple ANSI color helper (kept for backward compatibility)."""
    codes = {
        "red": "\033[91m",
        "green": "\033[92m",
        "yellow": "\033[93m",
        "blue": "\033[94m",
        "cyan": "\033[96m",
        "bold": "\033[1m",
        "reset": "\033[0m",
    }
    return f"{codes.get(code, '')}{text}{codes['reset']}"


def menu(title: str, options: list, subtitle: str = "") -> str:
    """Display a Rich-styled menu and return the user's choice."""
    console.print()
    panel = Panel(
        Text(title, justify="center", style="bold cyan"),
        box=box.ROUNDED,
        border_style="cyan",
        subtitle=subtitle or None,
    )
    console.print(panel)

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column("#", style="cyan", width=4)
    table.add_column("Option", style="white")
    for i, opt in enumerate(options, 1):
        table.add_row(str(i), opt)
    console.print(table)
    console.print()

    while True:
        choice = Prompt.ask("  Enter choice", default="1")
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return choice
        console.print("[red]  ❌ Invalid choice. Try again.[/red]")


def print_success(message: str) -> None:
    """Print a success message."""
    console.print(f"[green]  ✅ {message}[/green]")


def print_error(message: str) -> None:
    """Print an error message."""
    console.print(f"[red]  ❌ {message}[/red]")


def print_warning(message: str) -> None:
    """Print a warning message."""
    console.print(f"[yellow]  ⚠️  {message}[/yellow]")


def print_info(message: str) -> None:
    """Print an info message."""
    console.print(f"[cyan]  ℹ️  {message}[/cyan]")


def create_table(title: str, columns: list[str], rows: list[list[str]]) -> Table:
    """Create a Rich table with the given title, columns, and rows."""
    table = Table(
        title=title,
        box=box.ROUNDED,
        border_style="cyan",
        title_style="bold cyan",
        header_style="bold white",
    )
    for col in columns:
        table.add_column(col)
    for row in rows:
        table.add_row(*row)
    return table
