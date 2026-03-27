"""Terminal banner — ASCII art branding for OpenMind."""

from __future__ import annotations

from rich.console import Console
from rich.text import Text


def _build_banner() -> Text:
    """Build the ASCII banner with Open in white, Mind in Cal Gold."""
    # Slant font, hardcoded for consistency across environments.
    # Each line: (white_part, gold_part)
    lines = [
        ("   ____                  ", " __  ___  _           __"),
        ("  / __ \\____  ___  ____ ", "/  |/  (_)___  ____/ /"),
        (" / / / / __ \\/ _ \\/ __ \\", "/ /|_/ / / __ \\/ __  /"),
        ("/ /_/ / /_/ /  __/ / / ", "/ /  / / / / / / /_/ /"),
        ("\\____/ .___/\\___/_/ /_", "/_/  /_/_/_/ /_/\\__,_/"),
        ("    /_/", ""),
    ]

    banner = Text()
    for white_part, gold_part in lines:
        banner.append(white_part, style="bold white")
        if gold_part:
            banner.append(gold_part, style="bold yellow")
        banner.append("\n")

    return banner


def print_banner(console: Console | None = None, *, show_info: bool = True) -> None:
    """Print the OpenMind ASCII banner."""
    if console is None:
        console = Console()

    console.print()
    console.print(_build_banner(), end="")

    if show_info:
        from openmind import __version__

        console.print()
        console.print(
            f"  [dim]\U0001f43b AI study buddy for Cal \u00b7 v{__version__} \u00b7 Fiat Lux![/dim]"
        )
    console.print()
