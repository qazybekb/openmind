"""Progressive setup — minimal first run, add integrations later."""

from __future__ import annotations

import logging
import os
import stat
import shutil
from pathlib import Path
from typing import Any, Final

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from openmind.config import CONFIG_DIR, ConfigDict, GMAIL_CREDS_DIR, load_config, save_config
from openmind.universities import get_university

logger = logging.getLogger(__name__)

DEFAULT_MODEL: Final[str] = "google/gemini-2.5-pro"
MAX_COURSE_NICKNAME_LENGTH: Final[int] = 35
OPENROUTER_MODELS_URL: Final[str] = "https://openrouter.ai/api/v1/models"
REQUEST_TIMEOUT_S: Final[float] = 15.0
TELEGRAM_API_BASE: Final[str] = "https://api.telegram.org"
TELEGRAM_VALIDATE_TIMEOUT_S: Final[float] = 10.0

console: Console = Console()


def _mask_key(key: str) -> str:
    """Show first 6 and last 4 chars of a key, mask the rest."""
    if len(key) <= 12:
        return key[:3] + "****"
    return key[:6] + "****" + key[-4:]


def _ensure_private_dir(path: Path) -> None:
    """Create a directory with owner-only permissions."""
    path.mkdir(parents=True, exist_ok=True)
    os.chmod(path, stat.S_IRWXU)


def _restrict_file(path: Path) -> None:
    """Restrict a file to owner read/write when possible."""
    os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)


# ---------------------------------------------------------------------------
# First-run setup — only Canvas + OpenRouter (2 questions)
# ---------------------------------------------------------------------------


def run_first_setup() -> None:
    """Minimal first-run: Canvas token + OpenRouter key. Instant value."""
    university = get_university()

    from openmind.banner import print_banner
    print_banner(console)
    console.print("  [bold]Let's get you set up.[/bold]\n")

    cfg: ConfigDict = load_config()
    cfg["university"] = university

    # Step 1: Canvas
    console.print(Panel(
        "You'll need a bCourses access token.\n"
        "Go to: bCourses \u2192 click your profile icon (top-left) \u2192 Settings \u2192 + New Access Token\n\n"
        "[dim]Detailed guide: openmindbot.io/guides/bcourses[/dim]",
        title="[bold]Step 1 of 3[/bold] \u2014 Connect to bCourses",
        border_style="yellow",
        padding=(1, 2),
    ))
    canvas_token, user_name, courses = _setup_canvas(university["canvas_url"])
    cfg["canvas_token"] = canvas_token
    cfg["canvas_url"] = university["canvas_url"]
    cfg["user_name"] = user_name
    cfg["courses"] = courses

    # Step 2: Choose model
    console.print(Panel(
        "Pick the AI model that will power OpenMind.\n"
        "All models below support tool calling (required).\n"
        "You can change this later with: [cyan]openmind setup model[/cyan]",
        title="[bold]Step 2 of 3[/bold] \u2014 Choose your LLM",
        border_style="yellow",
        padding=(1, 2),
    ))

    console.print("    [cyan]1[/cyan]  google/gemini-2.5-pro           \u2014 smart, low cost [dim](default)[/dim]")
    console.print("    [cyan]2[/cyan]  xiaomi/mimo-v2-pro              \u2014 smart, very cheap")
    console.print("    [cyan]3[/cyan]  anthropic/claude-sonnet-4-6     \u2014 excellent reasoning")
    console.print("    [dim]Or type any OpenRouter model ID[/dim]")
    console.print()

    _model_choices = {
        "1": "google/gemini-2.5-pro",
        "2": "xiaomi/mimo-v2-pro",
        "3": "anthropic/claude-sonnet-4-6",
    }
    choice = Prompt.ask("  Enter 1, 2, 3, or a model ID", default="1")
    cfg["model"] = _model_choices.get(choice, choice)

    # Step 3: OpenRouter API key
    console.print(Panel(
        "You need an OpenRouter API key to connect to your chosen model.\n"
        "Get one at: [link=https://openrouter.ai/keys]openrouter.ai/keys[/link] (free credits available)\n\n"
        "[dim]Detailed guide: openmindbot.io/guides/openrouter[/dim]",
        title="[bold]Step 3 of 3[/bold] \u2014 Connect OpenRouter",
        border_style="yellow",
        padding=(1, 2),
    ))
    api_key = _setup_openrouter_key()
    cfg["openrouter_api_key"] = api_key

    # Optional integrations — show what's available, let them skip or enable
    console.print("\n[bold]Optional features[/bold] (press Enter to skip any)\n")

    cfg["telegram"] = _setup_telegram()
    cfg["gmail"] = _setup_gmail()
    cfg["calendar"] = _setup_calendar()
    cfg["slack"] = _setup_slack()
    cfg["todoist"] = _setup_todoist()
    cfg["obsidian"] = _setup_obsidian()

    console.print()
    if Confirm.ask("  Set up your academic profile? (major, interests, career goals)", default=False):
        _setup_profile()

    # Disable anything that wasn't explicitly enabled
    for integration in ("telegram", "todoist", "gmail", "calendar", "slack", "obsidian"):
        cfg.setdefault(integration, {"enabled": False})

    save_config(cfg)

    # Summary
    enabled = [name for name in ("telegram", "gmail", "calendar", "slack", "todoist", "obsidian")
               if cfg.get(name, {}).get("enabled")]

    # Summary
    summary_lines = [f"\U0001f389 [bold]You're ready![/bold] {university.get('mascot', '')}{university.get('colors', '')}"]
    summary_lines.append(f"\n  Model: {cfg.get('model', DEFAULT_MODEL)}")
    if enabled:
        summary_lines.append(f"  Integrations: {', '.join(enabled)}")
    summary_lines.append("")
    summary_lines.append("  [dim]Change anytime:[/dim]")
    summary_lines.append("    [cyan]openmind setup model[/cyan]     \u2014 change your LLM")
    summary_lines.append("    [cyan]openmind setup profile[/cyan]   \u2014 add your goals + interests")
    summary_lines.append("    [cyan]openmind setup <name>[/cyan]    \u2014 add/change any integration")

    console.print()
    console.print(Panel(
        "\n".join(summary_lines),
        border_style="green",
        padding=(1, 2),
    ))
    console.print()


# ---------------------------------------------------------------------------
# Full setup — re-run everything
# ---------------------------------------------------------------------------


def run_full_setup() -> None:
    """Full setup: Canvas + OpenRouter + profile + all integrations."""
    university = get_university()

    console.print(
        f"\n[bold]{university.get('mascot', '')} OpenMind Setup[/bold] "
        f"{university.get('spirit', '')} {university.get('colors', '')}"
    )
    console.print()

    cfg: ConfigDict = load_config()
    cfg["university"] = university

    # Canvas
    canvas_token, user_name, courses = _setup_canvas(university["canvas_url"])
    cfg["canvas_token"] = canvas_token
    cfg["canvas_url"] = university["canvas_url"]
    cfg["user_name"] = user_name
    cfg["courses"] = courses

    # OpenRouter
    api_key, model = _setup_openrouter_full()
    cfg["openrouter_api_key"] = api_key
    cfg["model"] = model

    # Profile
    _setup_profile()

    # Integrations
    console.print("\n[bold]Integrations[/bold] (all optional)\n")
    cfg["telegram"] = _setup_telegram()
    cfg["todoist"] = _setup_todoist()
    cfg["gmail"] = _setup_gmail()
    cfg["calendar"] = _setup_calendar()
    cfg["slack"] = _setup_slack()
    cfg["obsidian"] = _setup_obsidian()

    save_config(cfg)
    console.print(f"\n[green]Config saved to {CONFIG_DIR}[/green]")
    console.print(f"\n[bold]\U0001f389 Setup complete! Go Bears![/bold] {university.get('mascot', '')}{university.get('colors', '')}\n")


# ---------------------------------------------------------------------------
# Individual integration setup — `openmind setup <name>`
# ---------------------------------------------------------------------------


def setup_single_integration(name: str) -> None:
    """Set up a single integration by name."""
    cfg = load_config()

    handlers: dict[str, Any] = {
        "telegram": _setup_telegram,
        "todoist": _setup_todoist,
        "gmail": _setup_gmail,
        "calendar": _setup_calendar,
        "slack": _setup_slack,
        "obsidian": _setup_obsidian,
        "model": lambda: _setup_model_change(cfg),
    }

    if name == "profile":
        _setup_profile()
        return

    handler = handlers.get(name)
    if not handler:
        console.print(f"[red]Unknown integration: {name}[/red]")
        console.print(f"Available: {', '.join(handlers.keys())}, profile")
        return

    if name == "model":
        handler()
    else:
        result = handler()
        cfg[name] = result
        save_config(cfg)

    console.print("\n[green]Saved![/green]")


# ---------------------------------------------------------------------------
# Canvas setup
# ---------------------------------------------------------------------------


def _setup_canvas(canvas_url: str) -> tuple[str, str, dict[str, str]]:
    """Validate Canvas token and discover courses."""
    user_name = "Bear"
    while True:
        token = Prompt.ask("  Paste your bCourses token", password=True)
        if not token.strip():
            console.print("  [red]Token cannot be empty.[/red]")
            continue

        console.print(f"  [dim]Key: {_mask_key(token)}[/dim]")
        console.print("  Connecting...", end=" ")
        try:
            response = httpx.get(
                f"{canvas_url}/users/self/profile",
                headers={"Authorization": f"Bearer {token}"},
                timeout=REQUEST_TIMEOUT_S,
            )
            if response.status_code == 200:
                data = response.json()
                user_name = data.get("name", "Bear") if isinstance(data, dict) else "Bear"
                console.print(f"[green]Connected![/green] Hey {user_name} \U0001f43b")
                break
            console.print(_canvas_status_message(response.status_code))
        except httpx.HTTPError:
            console.print("[red]Connection error. Check your network.[/red]")

    # Discover courses
    console.print("  Finding your courses...", end=" ")
    courses: dict[str, str] = {}
    try:
        response = httpx.get(
            f"{canvas_url}/courses",
            params={"enrollment_state": "active", "per_page": 50},
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_S,
        )
        if response.status_code == 200:
            data = response.json()
            for course in data if isinstance(data, list) else []:
                if not isinstance(course, dict):
                    continue
                course_id = str(course.get("id", ""))
                raw_name = str(course.get("name", ""))
                nickname = raw_name.split(" - ")[-1].strip() if " - " in raw_name else raw_name
                if len(nickname) > MAX_COURSE_NICKNAME_LENGTH:
                    nickname = nickname[:MAX_COURSE_NICKNAME_LENGTH].rsplit(" ", 1)[0]
                courses[course_id] = nickname
            console.print(f"[green]{len(courses)} courses[/green]")
            for cid, cname in courses.items():
                console.print(f"    {cid} | {cname}")
        else:
            console.print("[yellow]Could not fetch courses.[/yellow]")
    except httpx.HTTPError:
        console.print("[yellow]Could not fetch courses.[/yellow]")

    return token, user_name, courses


# ---------------------------------------------------------------------------
# OpenRouter setup
# ---------------------------------------------------------------------------


def _setup_openrouter_key() -> str:
    """Validate OpenRouter key only."""
    while True:
        api_key = Prompt.ask("  Paste your OpenRouter key", password=True)
        if not api_key.strip():
            console.print("  [red]Key cannot be empty.[/red]")
            continue

        console.print(f"  [dim]Key: {_mask_key(api_key)}[/dim]")
        console.print("  Validating...", end=" ")
        try:
            response = httpx.get(
                OPENROUTER_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=REQUEST_TIMEOUT_S,
            )
            if response.status_code == 200:
                console.print("[green]OK[/green]")
                return api_key
            console.print(f"[red]Failed (HTTP {response.status_code})[/red]")
        except httpx.HTTPError:
            console.print("[red]Connection error.[/red]")


def _setup_openrouter_full() -> tuple[str, str]:
    """Validate OpenRouter key + choose model."""
    api_key = _setup_openrouter_key()

    console.print("\n  [bold]Choose your LLM model[/bold]")
    console.print("  [dim]All models below support tool calling (required for OpenMind)[/dim]\n")
    console.print("    [cyan]1[/cyan]  google/gemini-2.5-pro           \u2014 smart, low cost [dim](default)[/dim]")
    console.print("    [cyan]2[/cyan]  xiaomi/mimo-v2-pro              \u2014 smart, very cheap")
    console.print("    [cyan]3[/cyan]  anthropic/claude-sonnet-4-6     \u2014 excellent reasoning")
    console.print("    [dim]Or type any OpenRouter model ID[/dim]")

    _model_choices = {
        "1": "google/gemini-2.5-pro",
        "2": "xiaomi/mimo-v2-pro",
        "3": "anthropic/claude-sonnet-4-6",
    }
    choice = Prompt.ask("\n  Enter 1, 2, 3, or a model ID", default="1")
    model = _model_choices.get(choice, choice)
    return api_key, model


def _setup_model_change(cfg: ConfigDict) -> None:
    """Change the LLM model."""
    current = cfg.get("model", DEFAULT_MODEL)
    console.print(f"\n  Current model: [bold]{current}[/bold]\n")
    console.print("  [bold]Choose your LLM model[/bold]")
    console.print("  [dim]All models below support tool calling (required for OpenMind)[/dim]\n")
    console.print("    [cyan]1[/cyan]  google/gemini-2.5-pro           \u2014 smart, low cost")
    console.print("    [cyan]2[/cyan]  xiaomi/mimo-v2-pro              \u2014 smart, very cheap")
    console.print("    [cyan]3[/cyan]  anthropic/claude-sonnet-4-6     \u2014 excellent reasoning")
    console.print("    [dim]Or type any OpenRouter model ID[/dim]")

    _model_choices = {
        "1": "google/gemini-2.5-pro",
        "2": "xiaomi/mimo-v2-pro",
        "3": "anthropic/claude-sonnet-4-6",
    }
    choice = Prompt.ask("\n  Enter 1, 2, 3, or a model ID", default="1")
    cfg["model"] = _model_choices.get(choice, choice)
    save_config(cfg)
    console.print(f"  Model changed to: [bold]{cfg['model']}[/bold]")


# ---------------------------------------------------------------------------
# Profile setup
# ---------------------------------------------------------------------------


def _setup_profile() -> None:
    """Collect academic profile for personalized advice."""
    from openmind.tools.profile import load_profile, save_profile

    console.print("\n[bold]About you[/bold] (helps personalize advice \u2014 all optional, press Enter to skip)\n")

    profile = load_profile()

    level = Prompt.ask("  Undergraduate or graduate?", default=profile.get("level", ""))
    if level:
        profile["level"] = level.strip().lower()

    major = Prompt.ask("  Major/program", default=profile.get("major", ""))
    if major:
        profile["major"] = major

    year = Prompt.ask("  Year (e.g. junior, 2nd year)", default=profile.get("year", ""))
    if year:
        profile["year"] = year

    interests = Prompt.ask(
        "  Interests (comma-separated)",
        default=", ".join(profile.get("interests", [])) if isinstance(profile.get("interests"), list) else "",
    )
    if interests:
        profile["interests"] = [i.strip() for i in interests.split(",") if i.strip()]

    goals = Prompt.ask(
        "  Career goals",
        default=", ".join(profile.get("career_goals", [])) if isinstance(profile.get("career_goals"), list) else "",
    )
    if goals:
        profile["career_goals"] = [g.strip() for g in goals.split(",") if g.strip()]

    resume_path = Prompt.ask("  Resume PDF path (for skill extraction, or Enter to skip)", default="")
    if resume_path:
        resolved = Path(resume_path).expanduser()
        if resolved.exists() and resolved.suffix.lower() == ".pdf":
            profile["_pending_resume"] = str(resolved)
            console.print("  [green]Resume noted![/green] Skills will be extracted on your first chat.")
        elif resume_path.strip():
            console.print(f"  [yellow]File not found or not a PDF: {resolved}[/yellow]")

    # Only save if the user actually entered something
    meaningful_keys = [k for k, v in profile.items() if v]
    if meaningful_keys:
        save_profile(profile)
        console.print("\n  [green]Saved![/green] Edit anytime: [cyan]openmind profile[/cyan]\n")
    else:
        console.print("\n  [dim]Skipped. Add your profile later: [cyan]openmind setup profile[/cyan][/dim]\n")


# ---------------------------------------------------------------------------
# Integration setup functions
# ---------------------------------------------------------------------------


def _setup_telegram() -> dict[str, Any]:
    """Configure Telegram bot integration."""
    if not Confirm.ask("  Enable Telegram bot? (chat on your phone + push notifications)", default=False):
        return {"enabled": False}

    console.print()
    console.print("    1. Message @BotFather on Telegram \u2192 /newbot \u2192 copy the bot token")
    console.print("    2. Message @userinfobot on Telegram \u2192 copy your user ID")
    console.print("    [dim]Detailed guide: openmindbot.io/guides/telegram[/dim]")
    console.print()

    while True:
        bot_token = Prompt.ask("    Bot token", password=True)
        if not bot_token.strip():
            console.print("    [red]Token cannot be empty.[/red]")
            continue

        console.print(f"    [dim]Token: {_mask_key(bot_token)}[/dim]")
        user_id = Prompt.ask("    Your Telegram user ID")
        if not user_id.strip():
            console.print("    [red]User ID cannot be empty.[/red]")
            continue

        try:
            response = httpx.get(f"{TELEGRAM_API_BASE}/bot{bot_token}/getMe", timeout=TELEGRAM_VALIDATE_TIMEOUT_S)
            if response.status_code == 200:
                data = response.json()
                result = data.get("result", {}) if isinstance(data, dict) else {}
                bot_name = result.get("username", "unknown") if isinstance(result, dict) else "unknown"
                console.print(f"    [green]Connected to @{bot_name}[/green]")
                return {"enabled": True, "bot_token": bot_token, "user_id": user_id}

            console.print(f"    [red]Invalid bot token (HTTP {response.status_code})[/red]")
        except httpx.HTTPError:
            console.print("    [red]Could not reach Telegram. Check your network.[/red]")

        if not Confirm.ask("    Try again?", default=True):
            console.print("    [dim]Skipping Telegram.[/dim]")
            return {"enabled": False}


def _setup_todoist() -> dict[str, Any]:
    """Configure Todoist integration."""
    if not Confirm.ask("  Enable Todoist? (sync tasks from Canvas)", default=False):
        return {"enabled": False}

    console.print()
    console.print("    Go to: todoist.com/app/settings/integrations/developer")
    console.print("    Copy your API token.")
    console.print()
    token = Prompt.ask("    Paste your API token", password=True)
    if not token.strip():
        console.print("    [dim]Skipping Todoist.[/dim]")
        return {"enabled": False}

    console.print(f"    [dim]Token: {_mask_key(token)}[/dim]")
    console.print("    Validating...", end=" ")
    try:
        resp = httpx.get(
            "https://api.todoist.com/rest/v2/projects",
            headers={"Authorization": f"Bearer {token}"},
            timeout=REQUEST_TIMEOUT_S,
        )
        if resp.status_code == 200:
            console.print("[green]OK[/green]")
            return {"enabled": True, "token": token}
        console.print(f"[red]Failed (HTTP {resp.status_code})[/red]")
    except httpx.HTTPError:
        console.print("[red]Connection error.[/red]")

    return {"enabled": False}


def _setup_gmail() -> dict[str, Any]:
    """Configure Gmail integration."""
    if not Confirm.ask("  Enable Gmail? (read-only access to search professor emails)", default=False):
        return {"enabled": False}

    console.print()
    console.print("    You'll need a Google OAuth credentials file (credentials.json).")
    console.print("    Steps: Google Cloud Console \u2192 Create project \u2192 Enable Gmail API")
    console.print("           \u2192 OAuth consent screen \u2192 Credentials \u2192 Desktop app \u2192 Download JSON")
    console.print("    [dim]Detailed guide: openmindbot.io/guides/gmail[/dim]")
    console.print()
    creds_path = Prompt.ask("    Path to credentials.json (or Enter to skip)", default="")

    if creds_path:
        _ensure_private_dir(GMAIL_CREDS_DIR)
        try:
            destination = GMAIL_CREDS_DIR / "credentials.json"
            shutil.copy(Path(creds_path).expanduser(), destination)
            _restrict_file(destination)
            console.print("    [green]Credentials saved[/green]")
        except (OSError, shutil.SameFileError):
            logger.warning("Failed to copy Gmail credentials", exc_info=True)
            console.print("    [red]Failed to copy credentials.[/red]")
            return {"enabled": False}

    return {"enabled": True}


def _setup_calendar() -> dict[str, Any]:
    """Configure Google Calendar integration."""
    if not Confirm.ask("  Enable Google Calendar? (sync deadlines, block study time)", default=False):
        return {"enabled": False}

    creds_file = GMAIL_CREDS_DIR / "credentials.json"
    if creds_file.exists():
        console.print("    [green]OAuth credentials found (shared with Gmail)[/green]")
    else:
        console.print()
        console.print("    You'll need a Google OAuth credentials file (same as Gmail).")
        console.print("    If you already set up Gmail, you can reuse the same credentials.")
        console.print("    [dim]Detailed guide: openmindbot.io/guides/calendar[/dim]")
        console.print()
        creds_path = Prompt.ask("    Path to credentials.json (or Enter to skip)", default="")
        if creds_path:
            _ensure_private_dir(GMAIL_CREDS_DIR)
            try:
                shutil.copy(Path(creds_path).expanduser(), creds_file)
                _restrict_file(creds_file)
                console.print("    [green]Credentials saved[/green]")
            except (OSError, shutil.SameFileError):
                logger.warning("Failed to copy Calendar credentials", exc_info=True)
                console.print("    [red]Failed to copy credentials.[/red]")
                return {"enabled": False}

    return {"enabled": True}


def _setup_slack() -> dict[str, Any]:
    """Configure Slack integration (read-only)."""
    if not Confirm.ask("  Enable Slack? (read-only access to course channels)", default=False):
        return {"enabled": False}

    console.print()
    console.print("    1. Go to api.slack.com/apps \u2192 Create New App \u2192 From scratch")
    console.print("    2. OAuth & Permissions \u2192 Add scopes: channels:history, channels:read, search:read")
    console.print("    3. Install to Workspace \u2192 Copy the User OAuth Token (starts with xoxp-)")
    console.print("    [dim]Detailed guide: openmindbot.io/guides/slack[/dim]")
    console.print()
    token = Prompt.ask("    Paste your User OAuth Token (xoxp-...)", password=True)
    if token.strip():
        console.print(f"    [dim]Token: {_mask_key(token)}[/dim]")
    if not token.strip():
        return {"enabled": False}

    try:
        resp = httpx.get("https://slack.com/api/auth.test", headers={"Authorization": f"Bearer {token}"}, timeout=REQUEST_TIMEOUT_S)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, dict) and data.get("ok"):
                console.print(f"    [green]Connected to {data.get('team', '?')} as {data.get('user', '?')}[/green]")
            else:
                console.print(f"    [yellow]Validation failed: {data.get('error', 'unknown')}[/yellow]")
                return {"enabled": False}
    except httpx.HTTPError:
        console.print("    [yellow]Could not validate token.[/yellow]")

    return {"enabled": True, "token": token}


def _setup_obsidian() -> dict[str, Any]:
    """Configure Obsidian vault integration."""
    if not Confirm.ask("  Enable Obsidian? (save notes to your vault)", default=False):
        return {"enabled": False}

    console.print()
    console.print("    Enter the path to your Obsidian vault folder.")
    console.print("    [dim]This is the folder that contains your .obsidian/ directory.[/dim]")
    console.print()
    vault_path = Prompt.ask("    Vault path", default="~/Documents/Obsidian")
    resolved = Path(vault_path).expanduser()
    if not resolved.exists():
        console.print(f"    [yellow]Path not found: {resolved}[/yellow]")
        if not Confirm.ask("    Save anyway?", default=False):
            console.print("    [dim]Skipping Obsidian.[/dim]")
            return {"enabled": False}
    else:
        console.print(f"    [green]Found vault at {resolved}[/green]")

    return {"enabled": True, "vault_path": str(resolved)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _canvas_status_message(status_code: int, prefix: str = "  [red]Failed") -> str:
    """Return a user-facing Canvas API status message."""
    if status_code == 401:
        detail = "Token is invalid or expired. Generate a new one in bCourses."
    elif status_code == 403:
        detail = "Access denied. Check your token permissions."
    elif status_code == 429:
        detail = "Rate limited. Wait a minute and try again."
    else:
        detail = f"HTTP {status_code}"
    return f"{prefix} ({detail})[/]"
