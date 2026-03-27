"""CLI entry point — openmind command."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from openmind.config import CONFIG_DIR, ConfigDict, config_exists, config_valid, load_config

logger = logging.getLogger(__name__)

def _version_callback(value: bool) -> None:
    if value:
        from openmind.banner import print_banner
        print_banner()
        raise typer.Exit()


app: typer.Typer = typer.Typer(
    name="openmind",
    help="AI-powered Canvas LMS study buddy for UC Berkeley.",
    add_completion=False,
    no_args_is_help=False,
)
console: Console = Console()


def _run_setup_action(action: Callable[[], None]) -> None:
    """Run a setup action and convert local persistence failures into user-friendly CLI errors."""
    try:
        action()
    except OSError:
        logger.exception("OpenMind setup failed while reading or writing local files.")
        console.print("[red]OpenMind could not update files in ~/.openmind.[/red]")
        console.print("Check file permissions and available disk space, then try again.")
        raise typer.Exit(1)


def _ensure_config() -> ConfigDict:
    """Load config, running first-time setup if needed."""
    if not config_exists():
        from openmind.setup_wizard import run_first_setup

        _run_setup_action(run_first_setup)
        if not config_exists():
            raise typer.Exit(1)

    cfg = load_config()
    if not config_valid(cfg):
        console.print("[yellow]Config is incomplete.[/yellow]")
        console.print("Running setup...\n")
        from openmind.setup_wizard import run_first_setup

        _run_setup_action(run_first_setup)
        cfg = load_config()
        if not config_valid(cfg):
            console.print("[red]Setup incomplete. Run: openmind setup[/red]")
            raise typer.Exit(1)

    return cfg


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", "-v", callback=_version_callback, is_eager=True, help="Show version and exit"),
) -> None:
    """Launch openmind. Runs setup on first use, then starts the bot."""
    if ctx.invoked_subcommand is not None:
        return

    cfg = _ensure_config()

    if cfg.get("telegram", {}).get("enabled"):
        try:
            from openmind.bot import run_bot

            import threading
            bot_thread = threading.Thread(target=run_bot, args=(cfg,), daemon=True)
            bot_thread.start()
        except ImportError:
            logger.warning("Telegram extras unavailable.", exc_info=True)
            console.print("[yellow]Telegram requires: pip install 'openmind-berkeley[telegram]'[/yellow]")

    from openmind.repl import run_repl

    run_repl(cfg)


@app.command()
def setup(
    integration: Optional[str] = typer.Argument(None, help="Integration to set up: telegram, gmail, calendar, slack, todoist, obsidian, model, profile"),
) -> None:
    """Set up OpenMind or a specific integration.

    Examples:
        openmind setup              # Full setup (all settings)
        openmind setup telegram     # Just Telegram
        openmind setup gmail        # Just Gmail
        openmind setup model        # Change LLM model
        openmind setup profile      # Edit your academic profile
    """
    if integration:
        from openmind.setup_wizard import setup_single_integration

        _run_setup_action(lambda: setup_single_integration(integration))
    else:
        from openmind.setup_wizard import run_full_setup

        _run_setup_action(run_full_setup)


@app.command()
def config() -> None:
    """Show current configuration."""
    if not config_exists():
        console.print("[red]No config found.[/red] Run: openmind")
        raise typer.Exit(1)

    cfg = load_config()
    university = cfg.get("university", {})
    courses = cfg.get("courses", {})

    # Build config display
    lines: list[str] = []
    lines.append(f"[bold]University[/bold]    {university.get('name', 'Unknown')}")
    lines.append(f"[bold]Canvas[/bold]        {university.get('canvas_name', 'Canvas')}")
    lines.append(f"[bold]Model[/bold]         {cfg.get('model', 'not set')}")
    lines.append(f"[bold]Courses[/bold]        {len(courses)}")
    lines.append("")

    # Integrations with status indicators
    lines.append("[bold]Integrations[/bold]")
    all_integrations = ("telegram", "gmail", "calendar", "slack", "todoist", "obsidian")
    for name in all_integrations:
        enabled = cfg.get(name, {}).get("enabled", False)
        icon = "[green]\u2705[/green]" if enabled else "[dim]\u2b1c[/dim]"
        lines.append(f"  {icon} {name.capitalize()}")

    # Profile status
    from openmind.tools.profile import load_profile
    p = load_profile()
    has_profile = any(v for v in p.values())
    profile_icon = "[green]\u2705[/green]" if has_profile else "[dim]\u2b1c[/dim]"
    lines.append(f"\n[bold]Profile[/bold]       {profile_icon} {'Set up' if has_profile else 'Not set up'}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="\U0001f43b OpenMind Configuration",
        border_style="yellow",
        padding=(1, 2),
    ))

    # Courses table
    if courses:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("ID", style="dim")
        table.add_column("Course")
        for cid, name in courses.items():
            table.add_row(cid, name)
        console.print(table)

    # Hints
    disabled = [n for n in all_integrations if not cfg.get(n, {}).get("enabled")]
    if disabled:
        console.print("\n  [dim]Add integrations:[/dim] [cyan]openmind setup <name>[/cyan]")
    if not has_profile:
        console.print("  [dim]Set up profile:[/dim]   [cyan]openmind setup profile[/cyan]")
    console.print(f"  [dim]Config path:[/dim]      {CONFIG_DIR}\n")


@app.command()
def chat() -> None:
    """Start the terminal REPL (local chat, no Telegram)."""
    cfg = _ensure_config()
    from openmind.repl import run_repl

    run_repl(cfg)


@app.command()
def profile() -> None:
    """View your student profile."""
    from openmind.tools.profile import PROFILE_FILE, load_profile

    p = load_profile()
    has_data = any(v for v in p.values())
    if not has_data:
        console.print()
        console.print(Panel(
            "[yellow]No profile data yet.[/yellow]\n\n"
            "Add yours: [cyan]openmind setup profile[/cyan]",
            title="\U0001f43b Profile",
            border_style="yellow",
            padding=(1, 2),
        ))
        return

    lines: list[str] = []

    if p.get("level"):
        lines.append(f"[bold]Level[/bold]          {p['level']}")
    if p.get("major"):
        school = f" ({p['school']})" if p.get("school") else ""
        year = f", {p['year']}" if p.get("year") else ""
        lines.append(f"[bold]Major[/bold]          {p['major']}{school}{year}")
    if p.get("expected_graduation"):
        lines.append(f"[bold]Graduation[/bold]     {p['expected_graduation']}")
    if p.get("interests"):
        val = p["interests"]
        lines.append(f"[bold]Interests[/bold]      {', '.join(val) if isinstance(val, list) else val}")
    if p.get("career_goals"):
        val = p["career_goals"]
        lines.append(f"[bold]Career goals[/bold]   {', '.join(val) if isinstance(val, list) else val}")
    if p.get("dream_companies"):
        lines.append(f"[bold]Target co's[/bold]    {', '.join(p['dream_companies'])}")
    if p.get("gpa_goal"):
        lines.append(f"[bold]GPA goal[/bold]       {p['gpa_goal']}")

    resume = p.get("resume", {})
    if isinstance(resume, dict) and resume:
        lines.append("")
        if resume.get("skills"):
            lines.append(f"[bold]Skills[/bold]         {', '.join(resume['skills'][:10])}")
        if resume.get("experience"):
            for exp in resume["experience"][:3]:
                if isinstance(exp, dict):
                    lines.append(f"[bold]Experience[/bold]     {exp.get('role', '')} @ {exp.get('company', '')}")

    console.print()
    console.print(Panel(
        "\n".join(lines),
        title="\U0001f43b Student Profile",
        border_style="yellow",
        padding=(1, 2),
    ))
    console.print("  [dim]Edit:[/dim] [cyan]openmind setup profile[/cyan]")
    console.print(f"  [dim]File:[/dim] {PROFILE_FILE}\n")


@app.command()
def privacy() -> None:
    """Show what data stays local vs what goes to the LLM."""
    console.print()

    # Local
    console.print(Panel(
        "[green]\u2705[/green] ~/.openmind/config.json (API tokens, settings)\n"
        "[green]\u2705[/green] ~/.openmind/profile.json (academic profile)\n"
        "[green]\u2705[/green] ~/.openmind/state/ (heartbeat state)\n"
        "[green]\u2705[/green] ~/.openmind/repl_history (terminal history)\n"
        "[green]\u2705[/green] Resume PDF (never uploaded)",
        title="[green]Stays on your machine[/green]",
        border_style="green",
        padding=(1, 2),
    ))

    # Sent to LLM
    console.print(Panel(
        "[yellow]\u26a0\ufe0f[/yellow]  Your name, course list, and profile fields\n"
        "   (major, interests, goals, skills, GPA target)\n"
        "[yellow]\u26a0\ufe0f[/yellow]  Resume-extracted data (skills, experience, projects)\n"
        "[yellow]\u26a0\ufe0f[/yellow]  Canvas data fetched during the conversation\n"
        "[yellow]\u26a0\ufe0f[/yellow]  Your messages and the bot's responses\n"
        "[yellow]\u26a0\ufe0f[/yellow]  Gmail/Slack/Calendar content when you ask about it",
        title="[yellow]Sent to your LLM provider (OpenRouter)[/yellow]",
        border_style="yellow",
        padding=(1, 2),
    ))

    # Never sent
    console.print(Panel(
        "\U0001f6ab API tokens (sent only to their own service for auth)\n"
        "\U0001f6ab Raw resume PDF file\n"
        "\U0001f6ab Heartbeat state files\n"
        "\U0001f6ab Terminal command history",
        title="[red]Never sent to the LLM[/red]",
        border_style="red",
        padding=(1, 2),
    ))

    console.print("  [dim]OpenMind runs on your machine. There is no OpenMind server.[/dim]")
    console.print("  [dim]Profile fields are embedded in the AI's instructions for personalization.[/dim]")
    console.print(f"\n  Delete everything: [cyan]rm -rf {CONFIG_DIR}[/cyan]\n")
