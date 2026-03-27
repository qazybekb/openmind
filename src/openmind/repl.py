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
    print_banner(console)
    console.print(f"  Hey {user_name}! {uni.get('spirit', '')}")
    console.print("  [dim]Type your question, /help for commands, or /quit to exit.[/dim]\n")

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

            with console.status("[dim]Thinking...[/dim]", spinner="dots"):
                response = chat_stream(cfg, messages, client=client, on_token=_on_token)

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
