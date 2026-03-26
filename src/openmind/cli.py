"""CLI entry point — openmind command."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Optional

import typer
from rich.console import Console

from openmind.config import CONFIG_DIR, ConfigDict, config_exists, config_valid, load_config

logger = logging.getLogger(__name__)

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
def main(ctx: typer.Context) -> None:
    """Launch openmind. Runs setup on first use, then starts the bot."""
    if ctx.invoked_subcommand is not None:
        return

    cfg = _ensure_config()

    if cfg.get("telegram", {}).get("enabled"):
        try:
            from openmind.bot import run_bot

            run_bot(cfg)
        except ImportError:
            logger.warning("Telegram extras unavailable; falling back to REPL.", exc_info=True)
            console.print("[red]Telegram requires: pip install 'openmind[telegram]'[/red]")
            console.print("Falling back to terminal.\n")
            from openmind.repl import run_repl

            run_repl(cfg)
    else:
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
    integrations: list[str] = []

    for name in ("telegram", "todoist", "gmail", "calendar", "slack", "obsidian"):
        if cfg.get(name, {}).get("enabled"):
            integrations.append(name.capitalize())

    console.print(f"\n[bold]{university.get('name', 'Unknown')}[/bold] {university.get('mascot', '')}")
    console.print(f"Canvas: {university.get('canvas_name', 'Canvas')}")
    console.print(f"Model: {cfg.get('model', 'not set')}")
    console.print(f"Courses: {len(courses)}")
    for cid, name in courses.items():
        console.print(f"  {cid} | {name}")
    console.print(f"Integrations: {', '.join(integrations) if integrations else 'none'}")
    console.print(f"\nConfig: {CONFIG_DIR}")

    # Show available integrations that aren't enabled
    disabled = [n for n in ("telegram", "gmail", "calendar", "slack", "todoist", "obsidian") if not cfg.get(n, {}).get("enabled")]
    if disabled:
        console.print("\n[dim]Add integrations: openmind setup <name>[/dim]")
        console.print(f"[dim]Available: {', '.join(disabled)}[/dim]")
    console.print()


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
        console.print("\n[yellow]No profile data yet.[/yellow]")
        console.print("Add yours: [cyan]openmind setup profile[/cyan]\n")
        return

    console.print("\n[bold]Your profile[/bold] \U0001f43b\n")

    if p.get("level"):
        console.print(f"  Level: {p['level']}")
    if p.get("major"):
        school = f" ({p['school']})" if p.get("school") else ""
        year = f", {p['year']}" if p.get("year") else ""
        console.print(f"  Major: {p['major']}{school}{year}")
    if p.get("expected_graduation"):
        console.print(f"  Graduation: {p['expected_graduation']}")
    if p.get("interests"):
        val = p["interests"]
        console.print(f"  Interests: {', '.join(val) if isinstance(val, list) else val}")
    if p.get("career_goals"):
        val = p["career_goals"]
        console.print(f"  Career goals: {', '.join(val) if isinstance(val, list) else val}")
    if p.get("dream_companies"):
        console.print(f"  Dream companies: {', '.join(p['dream_companies'])}")
    if p.get("gpa_goal"):
        console.print(f"  GPA goal: {p['gpa_goal']}")

    resume = p.get("resume", {})
    if isinstance(resume, dict) and resume:
        if resume.get("skills"):
            console.print(f"  Skills: {', '.join(resume['skills'][:10])}")
        if resume.get("experience"):
            for exp in resume["experience"][:3]:
                if isinstance(exp, dict):
                    console.print(f"  Experience: {exp.get('role', '')} @ {exp.get('company', '')}")

    console.print("\n  Edit: [cyan]openmind setup profile[/cyan]")
    console.print(f"  File: {PROFILE_FILE}\n")


@app.command()
def privacy() -> None:
    """Show what data stays local vs what goes to the LLM."""
    console.print("\n[bold]\U0001f512 Privacy summary[/bold]\n")
    console.print("  [dim]OpenMind runs on your machine. There is no OpenMind server.[/dim]")
    console.print()

    console.print("  [bold]Files that stay on your machine:[/bold]")
    console.print("    \u2705 ~/.openmind/config.json (API tokens, settings)")
    console.print("    \u2705 ~/.openmind/profile.json (your academic profile)")
    console.print("    \u2705 ~/.openmind/state/ (heartbeat notification state)")
    console.print("    \u2705 ~/.openmind/repl_history (terminal command history)")
    console.print("    \u2705 Resume PDF (never uploaded)")
    console.print()

    console.print("  [bold]Sent to the LLM on every request (via OpenRouter):[/bold]")
    console.print("    \u26a0\ufe0f  Your name and course list")
    console.print("    \u26a0\ufe0f  Profile fields when present: level, major, school, year,")
    console.print("       expected graduation, interests, career goals, dream companies,")
    console.print("       GPA goal, strengths, areas to improve, study/learning preferences")
    console.print("    \u26a0\ufe0f  Resume-extracted data: skills, experience, projects")
    console.print("       (if you imported a resume)")
    console.print("    \u26a0\ufe0f  Tool results used in the conversation: Canvas data, PDFs,")
    console.print("       web pages, and any other fetched content")
    console.print("    \u26a0\ufe0f  Your messages and the bot's responses")
    console.print()

    console.print("  [bold]Sent to external services when needed:[/bold]")
    console.print("    \u26a0\ufe0f  Canvas token \u2192 bCourses")
    console.print("    \u26a0\ufe0f  OpenRouter API key \u2192 OpenRouter")
    console.print("    \u26a0\ufe0f  Telegram bot token \u2192 Telegram (if enabled)")
    console.print("    \u26a0\ufe0f  Slack/Todoist/Google tokens \u2192 their own APIs (if enabled)")
    console.print()

    console.print("  [bold]Sent to the LLM only when you explicitly ask:[/bold]")
    console.print("    \u26a0\ufe0f  Gmail message content (when you ask about email)")
    console.print("    \u26a0\ufe0f  Slack message content (when you ask about Slack)")
    console.print("    \u26a0\ufe0f  Google Calendar events (when you ask about calendar)")
    console.print("    \u26a0\ufe0f  Todoist task content (when you ask about tasks)")
    console.print("    \u26a0\ufe0f  Obsidian note content (when you ask about notes)")
    console.print()

    console.print("  [bold]Never sent to the LLM or an OpenMind server:[/bold]")
    console.print("    \U0001f6ab API tokens themselves")
    console.print("    \U0001f6ab Raw resume PDF file")
    console.print("    \U0001f6ab Heartbeat state")
    console.print("    \U0001f6ab Terminal history")
    console.print()

    console.print("  [dim]Your profile fields are embedded in the AI's instructions so it[/dim]")
    console.print("  [dim]can personalize responses. The files themselves stay local.[/dim]")
    console.print()
    console.print(f"  Delete everything: rm -rf {CONFIG_DIR}\n")
