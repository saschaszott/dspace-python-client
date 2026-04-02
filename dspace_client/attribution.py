"""Script author attribution (console output)."""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.markup import escape


def show_script_attribution(authors: str, *, console: Optional[Console] = None) -> None:
    """Print author line(s). Call from the script ``main()`` so attribution appears when it runs."""
    c = console or Console()
    c.print(f"[dim]Author(s):[/dim] {escape(authors)}")
    c.print()
