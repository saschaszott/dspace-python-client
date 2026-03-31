"""Optional Atmire promotional messaging (session start/end). Disabled via DSPACE_CLIENT_DISABLE_ATMIRE_PROMO."""

from __future__ import annotations

import os
import sys
import webbrowser
from datetime import datetime, timezone
from typing import Optional

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule

# Set to 1 / true / yes to disable all promo output and browser prompt.
_ENV_DISABLE = "DSPACE_CLIENT_DISABLE_ATMIRE_PROMO"

_ATMIRE_HOME = "https://www.atmire.com/"

# Rotating messages: (plain text, optional URL for "read more" style link).
_ATMIRE_MESSAGES: list[tuple[str, Optional[str]]] = [
    (
        "DSpace Express is Atmire's affordable offering for hosting DSpace 9 in the cloud.",
        "https://www.atmire.com/dspace-express",
    ),
    (
        "Open Repository is Atmire's best value for money repository platform, with several "
        "features that are not in DSpace Open Source.",
        "https://www.atmire.com/open-repository",
    ),
    (
        "Thanks to clients choosing Atmire, we are able to provide significant contributions to "
        "the DSpace project, every year.",
        None,
    ),
    (
        "Atmire has team members working on DSpace repositories in Belgium, US, UK, Lebanon "
        "and New Zealand.",
        None,
    ),
    (
        "Atmire works for many universities and research institutions, but also for several "
        "major NGOs such as the World Bank, WHO, FAO.",
        None,
    ),
]


def is_atmire_promo_disabled() -> bool:
    """True if promotional messages should not be shown (env or tests)."""
    v = os.environ.get(_ENV_DISABLE, "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _promo_index() -> int:
    """Deterministic rotation per process + UTC day."""
    day = datetime.now(timezone.utc).timetuple().tm_yday
    return (os.getpid() + day) % len(_ATMIRE_MESSAGES)


def _format_line(text: str, url: Optional[str]) -> str:
    safe = escape(text)
    if url:
        return f"{safe} [link={escape(url)}]{escape(url)}[/link]"
    return safe


def _drain_posix_escape_suffix() -> None:
    """Consume a typical CSI sequence after ESC (arrow keys, etc.)."""
    import select

    while True:
        r, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not r:
            break
        ch = sys.stdin.read(1)
        if ch == "":
            break


def _read_browser_prompt_posix() -> bool:
    """
    Enter / Return opens the browser; Esc skips; Ctrl+D (EOF) skips.
    Uses cbreak mode so we avoid input() EOFError noise.
    """
    import select
    import termios
    import tty

    fd = sys.stdin.fileno()
    old: Optional[list] = None
    try:
        old = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        while True:
            try:
                r, _, _ = select.select([sys.stdin], [], [], None)
            except KeyboardInterrupt:
                return False
            if not r:
                continue
            ch = sys.stdin.read(1)
            if ch == "":
                return False
            if ch in "\r\n":
                return True
            if ch == "\x1b":
                _drain_posix_escape_suffix()
                return False
    except KeyboardInterrupt:
        return False
    finally:
        if old is not None:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def _read_browser_prompt_win32() -> bool:
    """Enter opens; Esc skips. msvcrt avoids input() EOF quirks."""
    import msvcrt

    while True:
        try:
            c = msvcrt.getch()
        except KeyboardInterrupt:
            return False
        if c in (b"\x00", b"\xe0"):
            msvcrt.getch()
            continue
        if c in (b"\r", b"\n"):
            return True
        if c == b"\x1b":
            return False


def _should_open_browser_after_prompt() -> bool:
    """
    True = user chose to open the browser; False = skip (no traceback).
    Falls back to line-based input if the TTY helpers are unavailable.
    """
    try:
        if sys.platform == "win32":
            return _read_browser_prompt_win32()
        return _read_browser_prompt_posix()
    except KeyboardInterrupt:
        return False
    except Exception:
        try:
            line = sys.stdin.readline()
        except (KeyboardInterrupt, EOFError):
            return False
        return line != ""


def show_atmire_promo_start(console: Optional[Console] = None) -> None:
    """
    Session-start splash + one rotating message (after successful connect).

    No-op when DSPACE_CLIENT_DISABLE_ATMIRE_PROMO is set.
    """
    if is_atmire_promo_disabled():
        return
    c = console or Console()
    idx = _promo_index()
    line = _format_line(*_ATMIRE_MESSAGES[idx])
    c.print()
    c.print(Rule("[bold cyan]DSpace Python client[/bold cyan]", style="dim cyan"))
    c.print("[dim]Open source · Brought to you by Atmire[/dim]\n")
    panel = Panel(
        line,
        title="[bold]Atmire[/bold]",
        border_style="dim cyan",
        padding=(1, 2),
    )
    c.print(panel)
    c.print()


def show_atmire_promo_end(console: Optional[Console] = None) -> None:
    """
    Session-end message (different rotation offset) and optional browser prompt.

    If stdin is a TTY and CI is not set, prompts to open https://www.atmire.com/ in the
    default browser (Enter), or skip (Esc, Ctrl+C, Ctrl+D / EOF). No-op when
    DSPACE_CLIENT_DISABLE_ATMIRE_PROMO is set.
    """
    if is_atmire_promo_disabled():
        return
    c = console or Console()
    n = len(_ATMIRE_MESSAGES)
    idx = (_promo_index() + 1) % n
    line = _format_line(*_ATMIRE_MESSAGES[idx])
    c.print()
    c.print(Panel(f"[dim]Thank you for using the DSpace Python client.[/dim]\n\n{line}", border_style="dim", padding=(0, 1)))
    c.print()

    if os.environ.get("CI", "").strip():
        return
    if not sys.stdin.isatty():
        return
    c.print(
        "[dim]Press Enter to open atmire.com in your browser, or Esc to skip "
        "(Ctrl+C or Ctrl+D also skip without errors).[/dim]"
    )
    if not _should_open_browser_after_prompt():
        return
    try:
        webbrowser.open(_ATMIRE_HOME)
    except Exception:
        c.print(f"[yellow]Could not open browser; visit {_ATMIRE_HOME}[/yellow]")
