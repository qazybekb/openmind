"""Run the terminal REPL for OpenMind."""

from __future__ import annotations

import logging
import os
import stat
from typing import Any, TypeAlias

from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown

from openmind.config import CONFIG_DIR, ConfigDict
from openmind.llm import chat_stream, create_client
from openmind.memory import consolidate_conversation

logger = logging.getLogger(__name__)

ChatMessage: TypeAlias = dict[str, Any]

console: Console = Console()


def run_repl(cfg: ConfigDict) -> None:
    """Run the interactive terminal REPL."""
    uni = cfg.get("university", {})
    user_name = cfg.get("user_name", "Student")

    from openmind.banner import print_banner
    from openmind.tools.profile import load_profile, save_profile

    print_banner(console)
    console.print(f"  Hey {user_name}! {uni.get('spirit', '')}")
    console.print("  [dim]Type your question, /help for commands, or /quit to exit.[/dim]")

    # Nudge personalization if profile is empty
    profile = load_profile()
    has_profile = any(v for v in profile.values())
    if not has_profile:
        console.print()
        console.print("  [dim]\U0001f4a1 Tip: Make OpenMind smarter about YOU:[/dim]")
        console.print("  [dim]   openmind setup profile[/dim]  [dim]\u2014 add your major, goals, interests[/dim]")
        console.print("  [dim]   Upload your resume for skill-gap analysis & tailored advice[/dim]")
    console.print()

    # Consume pending resume import from setup wizard
    pending_resume = profile.get("_pending_resume")
    if pending_resume:
        from pathlib import Path as _Path
        resume_path = _Path(str(pending_resume))
        if resume_path.exists():
            console.print(f"  [dim]Importing resume from {resume_path.name}...[/dim]")
            try:
                from openmind.tools.profile import execute_profile_tool
                result = execute_profile_tool("import_resume", {"pdf_path": str(resume_path)}, cfg)
                import json as _json
                parsed = _json.loads(result)
                if "error" not in parsed:
                    console.print("  [green]Resume imported![/green] Skills and experience added to your profile.")
                else:
                    console.print(f"  [yellow]Resume import: {parsed.get('error', 'failed')}[/yellow]")
            except Exception:
                logger.warning("Failed to import pending resume", exc_info=True)
            # Clear the pending flag
            profile.pop("_pending_resume", None)
            save_profile(profile)

    history_file = CONFIG_DIR / "repl_history"
    history_file.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(history_file.parent, stat.S_IRWXU)
    history_file.touch(exist_ok=True)
    os.chmod(history_file, stat.S_IRUSR | stat.S_IWUSR)
    session: PromptSession[str] = PromptSession(history=FileHistory(str(history_file)))
    client = create_client(cfg)
    messages: list[ChatMessage] = []

    while True:
        try:
            user_input = session.prompt("You \u2192 ").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\nBye! \U0001f43b")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            if user_input.lower().strip() in ("/quit", "/exit", "/q"):
                console.print(f"Bye! {uni.get('spirit', '')} {uni.get('mascot', '')}")
                break
            handled, synthetic = _handle_command(user_input, cfg, messages)
            if handled:
                continue
            if synthetic:
                user_input = synthetic

        messages.append({"role": "user", "content": user_input})

        try:
            console.print()
            console.rule(style="dim")
            console.print()

            collected: list[str] = []
            streaming = False

            def _on_token(text: str) -> None:
                nonlocal streaming
                if not streaming:
                    streaming = True
                collected.append(text)
                console.print(text, end="", highlight=False)

            try:
                with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                    response = chat_stream(cfg, messages, client=client, on_token=_on_token)
            except KeyboardInterrupt:
                console.print("\n[dim]Cancelled.[/dim]")
                messages.pop()
                continue

            # If we streamed, add a newline; if not, render as markdown
            if streaming:
                console.print()
            else:
                console.print(Markdown(response))
            console.print()
        except Exception:
            logger.exception("REPL request failed")
            console.print("[red]Something went wrong while handling that request.[/red]")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": response})


def _handle_command(
    cmd: str,
    cfg: ConfigDict,
    messages: list[ChatMessage],
) -> tuple[bool, str | None]:
    """Handle a slash command and return whether it consumed the input."""
    cmd = cmd.lower().strip()

    if cmd == "/help":
        console.print(
            "\n[bold]Commands:[/bold]\n"
            "  /help      \u2014 Show this help\n"
            "  /courses   \u2014 List your courses\n"
            "  /grades    \u2014 Quick grade check\n"
            "  /gpa       \u2014 Calculate your GPA (or /gpa 3.5 for target)\n"
            "  /new       \u2014 Start a new conversation (saves context)\n"
            "  /clear     \u2014 Clear conversation history\n"
            "  /remind    \u2014 Set a reminder\n"
            "  /config    \u2014 Show config path\n"
            "  /quit      \u2014 Exit\n"
        )
        return True, None

    if cmd == "/courses":
        courses = cfg.get("courses", {})
        for cid, name in courses.items():
            console.print(f"  {cid} | {name}")
        return True, None

    if cmd == "/grades":
        return False, "What are my grades across all courses?"

    if cmd == "/gpa" or cmd.startswith("/gpa "):
        target = cmd[4:].strip()
        if target:
            return False, f"Calculate my GPA and what I need to get a {target} GPA."
        return False, "Calculate my current GPA across all courses."

    if cmd == "/new":
        if messages:
            consolidate_conversation(messages)
            messages.clear()
            console.print("[dim]Conversation saved to memory and cleared. Starting fresh![/dim]")
        else:
            console.print("[dim]Already a fresh conversation.[/dim]")
        return True, None

    if cmd == "/clear":
        messages.clear()
        console.print("[dim]Conversation cleared.[/dim]")
        return True, None

    if cmd.startswith("/remind"):
        # Pass to LLM as a natural language reminder request
        reminder_text = cmd[7:].strip()
        if reminder_text:
            return False, f"Set a reminder: {reminder_text}"
        return False, "I want to set a reminder. Ask me what and when."

    if cmd == "/config":
        console.print(f"Config: {CONFIG_DIR}")
        return True, None

    return False, None
