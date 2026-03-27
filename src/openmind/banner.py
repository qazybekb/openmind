"""Terminal banner — ASCII art branding for OpenMind."""

from __future__ import annotations

from rich.console import Console

# Hardcoded slant font — no pyfiglet dependency needed.
# "Open" in bold white, "Mind" in bold yellow (Cal Gold).
_BANNER = """\
[bold white]   ____                  [/bold white][bold yellow] __  ___  _           __[/bold yellow]
[bold white]  / __ \\____  ___  ____ [/bold white][bold yellow]/  |/  (_)___  ____/ /[/bold yellow]
[bold white] / / / / __ \\/ _ \\/ __ \\[/bold white][bold yellow]/ /|_/ / / __ \\/ __  /[/bold yellow]
[bold white]/ /_/ / /_/ /  __/ / / [/bold white][bold yellow]/ /  / / / / / / /_/ /[/bold yellow]
[bold white]\\____/ .___/\\___/_/ /_[/bold white][bold yellow]/_/  /_/_/_/ /_/\\__,_/[/bold yellow]
[bold white]    /_/[/bold white]"""


def print_banner(console: Console | None = None, *, show_info: bool = True) -> None:
    """Print the OpenMind ASCII banner."""
    if console is None:
        console = Console()

    console.print()
    console.print(_BANNER)

    if show_info:
        from openmind import __version__

        console.print()
        console.print(
            f"  [dim]\U0001f43b AI study buddy for UC Berkeley \u00b7 v{__version__} \u00b7 Go Bears![/dim]"
        )
    console.print()
