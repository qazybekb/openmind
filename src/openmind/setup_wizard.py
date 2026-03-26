"""Progressive setup — minimal first run, add integrations later."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any, Final

import httpx
from rich.console import Console
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


# ---------------------------------------------------------------------------
# First-run setup — only Canvas + OpenRouter (2 questions)
# ---------------------------------------------------------------------------


def run_first_setup() -> None:
    """Minimal first-run: Canvas token + OpenRouter key. Instant value."""
    university = get_university()

    console.print(
        f"\n[bold]{university.get('mascot', '')} Welcome to OpenMind![/bold] "
        f"{university.get('spirit', '')} {university.get('colors', '')}"
    )
    console.print("Your Cal study buddy. Let's get you set up.\n")

    cfg: ConfigDict = load_config()
    cfg["university"] = university

    # Step 1: Canvas
    console.print("[bold]Step 1 of 2[/bold] — Connect to bCourses\n")
    canvas_token, user_name, courses = _setup_canvas(university["canvas_url"])
    cfg["canvas_token"] = canvas_token
    cfg["canvas_url"] = university["canvas_url"]
    cfg["user_name"] = user_name
    cfg["courses"] = courses

    # Step 2: OpenRouter
    console.print(f"\n[bold]Step 2 of 2[/bold] — Connect an AI model\n")
    api_key = _setup_openrouter_key()
    cfg["openrouter_api_key"] = api_key
    cfg["model"] = DEFAULT_MODEL

    # Set all integrations to disabled by default
    for integration in ("telegram", "todoist", "gmail", "calendar", "slack", "obsidian"):
        cfg.setdefault(integration, {"enabled": False})

    save_config(cfg)

    console.print(f"\n[bold]\U0001f389 You're ready![/bold] {university.get('mascot', '')}{university.get('colors', '')}")
    console.print(f"\n  Using model: [dim]{DEFAULT_MODEL}[/dim]")
    console.print(f"  Change it anytime: [cyan]openmind setup model[/cyan]\n")
    console.print("  [dim]Add more features later:[/dim]")
    console.print("    [cyan]openmind profile[/cyan]    — personalize advice with your goals")
    console.print("    [cyan]openmind setup telegram[/cyan] — get alerts on your phone")
    console.print("    [cyan]openmind setup gmail[/cyan]    — check professor emails")
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

    console.print(f"\n[green]Saved![/green]")


# ---------------------------------------------------------------------------
# Canvas setup
# ---------------------------------------------------------------------------


def _setup_canvas(canvas_url: str) -> tuple[str, str, dict[str, str]]:
    """Validate Canvas token and discover courses."""
    console.print("  Get your bCourses token:")
    console.print("  bCourses \u2192 Profile \u2192 Settings \u2192 + New Access Token\n")

    user_name = "Bear"
    while True:
        token = Prompt.ask("  bCourses token", password=True)
        if not token.strip():
            console.print("  [red]Token cannot be empty.[/red]")
            continue

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
    """Validate OpenRouter key only — use default model (no model question)."""
    console.print("  Get your OpenRouter key:")
    console.print("  [link=https://openrouter.ai/keys]openrouter.ai/keys[/link] (free credits available)\n")

    while True:
        api_key = Prompt.ask("  OpenRouter key", password=True)
        if not api_key.strip():
            console.print("  [red]Key cannot be empty.[/red]")
            continue

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

    console.print("\n  Popular models:")
    console.print("    google/gemini-2.5-pro        \u2014 great all-rounder, low cost")
    console.print("    xiaomi/mimo-v2-pro           \u2014 very capable, very cheap")
    console.print("    openai/gpt-5-mini            \u2014 fast and capable")
    console.print("    anthropic/claude-sonnet-4    \u2014 excellent reasoning")

    model = Prompt.ask("\n  Model", default=DEFAULT_MODEL)
    return api_key, model


def _setup_model_change(cfg: ConfigDict) -> None:
    """Change the LLM model."""
    current = cfg.get("model", DEFAULT_MODEL)
    console.print(f"\n  Current model: [bold]{current}[/bold]\n")
    console.print("  Popular models:")
    console.print("    google/gemini-2.5-pro        \u2014 great all-rounder, low cost")
    console.print("    xiaomi/mimo-v2-pro           \u2014 very capable, very cheap")
    console.print("    openai/gpt-5-mini            \u2014 fast and capable")
    console.print("    anthropic/claude-sonnet-4    \u2014 excellent reasoning")

    model = Prompt.ask("\n  New model", default=current)
    cfg["model"] = model
    save_config(cfg)
    console.print(f"  Model changed to: [bold]{model}[/bold]")


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

    # Only save if the user actually entered something
    meaningful_keys = [k for k, v in profile.items() if v]
    if meaningful_keys:
        save_profile(profile)
        console.print(f"\n  [green]Saved![/green] Edit anytime: [cyan]openmind profile[/cyan]\n")
    else:
        console.print(f"\n  [dim]Skipped. Add your profile later: [cyan]openmind setup profile[/cyan][/dim]\n")


# ---------------------------------------------------------------------------
# Integration setup functions
# ---------------------------------------------------------------------------


def _setup_telegram() -> dict[str, Any]:
    """Configure Telegram bot integration."""
    if not Confirm.ask("  Enable Telegram bot?", default=False):
        return {"enabled": False}

    console.print("    1. Message @BotFather on Telegram \u2192 /newbot \u2192 copy the token")
    console.print("    2. Message @userinfobot \u2192 get your user ID")

    while True:
        bot_token = Prompt.ask("    Bot token", password=True)
        if not bot_token.strip():
            console.print("    [red]Token cannot be empty.[/red]")
            continue

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
    if not Confirm.ask("  Enable Todoist?", default=False):
        return {"enabled": False}
    token = Prompt.ask("    API token", password=True)
    return {"enabled": True, "token": token}


def _setup_gmail() -> dict[str, Any]:
    """Configure Gmail integration."""
    if not Confirm.ask("  Enable Gmail?", default=False):
        return {"enabled": False}

    console.print("    Google Cloud Console \u2192 Gmail API \u2192 OAuth 2.0 Client ID (Desktop app)")
    creds_path = Prompt.ask("    Path to OAuth JSON (or Enter to skip)", default="")

    if creds_path:
        GMAIL_CREDS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copy(Path(creds_path).expanduser(), GMAIL_CREDS_DIR / "credentials.json")
            console.print("    [green]Credentials saved[/green]")
        except (OSError, shutil.SameFileError):
            logger.warning("Failed to copy Gmail credentials", exc_info=True)
            console.print("    [red]Failed to copy credentials.[/red]")
            return {"enabled": False}

    return {"enabled": True}


def _setup_calendar() -> dict[str, Any]:
    """Configure Google Calendar integration."""
    if not Confirm.ask("  Enable Google Calendar?", default=False):
        return {"enabled": False}

    creds_file = GMAIL_CREDS_DIR / "credentials.json"
    if creds_file.exists():
        console.print("    [green]OAuth credentials found (shared with Gmail)[/green]")
    else:
        console.print("    Google Cloud Console \u2192 Calendar API \u2192 OAuth 2.0 Client ID")
        creds_path = Prompt.ask("    Path to OAuth JSON (or Enter to skip)", default="")
        if creds_path:
            GMAIL_CREDS_DIR.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy(Path(creds_path).expanduser(), creds_file)
                console.print("    [green]Credentials saved[/green]")
            except (OSError, shutil.SameFileError):
                logger.warning("Failed to copy Calendar credentials", exc_info=True)
                console.print("    [red]Failed to copy credentials.[/red]")
                return {"enabled": False}

    return {"enabled": True}


def _setup_slack() -> dict[str, Any]:
    """Configure Slack integration (read-only)."""
    if not Confirm.ask("  Enable Slack?", default=False):
        return {"enabled": False}

    console.print("    api.slack.com/apps \u2192 Create App \u2192 Add scopes: channels:history, channels:read, search:read")
    token = Prompt.ask("    User OAuth Token (xoxp-...)", password=True)
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
    if not Confirm.ask("  Enable Obsidian?", default=False):
        return {"enabled": False}

    vault_path = Prompt.ask("    Vault path", default="~/Documents/Obsidian")
    resolved = Path(vault_path).expanduser()
    if not resolved.exists():
        console.print("    [yellow]Path doesn't exist yet. Will be created when needed.[/yellow]")

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
