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
    user_name = cfg.get("user_name", "Student")

    from openmind.banner import print_banner
    from openmind.tools.profile import load_profile, save_profile

    from openmind.universities import spirit

    print_banner(console)
    console.print(f"  Hey {user_name}! {spirit()}")
    console.print("  [dim]Type your question, /help for commands, or /quit to exit.[/dim]")

    # Nudge personalization if profile is empty
    profile = load_profile()
    has_profile = any(v for v in profile.values())
    if not has_profile:
        console.print()
        console.print("  [dim]\U0001f4a1 Pro tip: I can give way better advice if I know you[/dim]")
        console.print("  [dim]   Run [cyan]openmind setup profile[/cyan] \u2014 major, goals, interests[/dim]")
        console.print("  [dim]   Drop your resume and I'll do skill-gap analysis[/dim]")
    console.print()

    # Consume pending resume import from setup wizard
    pending_resume = profile.get("_pending_resume")
    if pending_resume:
        from pathlib import Path as _Path
        resume_path = _Path(str(pending_resume))
        if resume_path.exists():
            console.print(f"  [dim]Extracting resume from {resume_path.name}...[/dim]")
            try:
                import pymupdf
                pdf_doc = pymupdf.open(str(resume_path))
                resume_text = "\n".join(page.get_text() for page in pdf_doc)
                pdf_doc.close()

                if resume_text.strip():
                    # Store raw text — the LLM will parse it on first interaction via import_resume tool
                    profile["_resume_text"] = resume_text[:20000]
                    console.print("  [green]Resume extracted![/green] I'll analyze your skills on first chat.")
                else:
                    console.print("  [yellow]Could not extract text from resume PDF.[/yellow]")
            except Exception:
                logger.warning("Failed to extract pending resume", exc_info=True)
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
            console.print("\nPeace! \U0001f43b")
            break

        if not user_input:
            continue

        # Slash commands
        if user_input.startswith("/"):
            if user_input.lower().strip() in ("/quit", "/exit", "/q"):
                console.print("Later! Go Bears! \U0001f43b")
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
        except Exception as exc:
            logger.exception("REPL request failed")
            err_type = type(exc).__name__
            if "timeout" in err_type.lower() or "Timeout" in str(exc):
                console.print("[red]Timed out \u2014 the model's taking too long. Try again or try a shorter question.[/red]")
            elif "auth" in err_type.lower() or "401" in str(exc):
                console.print("[red]Auth error \u2014 your API key might be off. Run: openmind setup model[/red]")
            else:
                console.print("[red]Something broke \u2014 probably a network thing. Give it another shot.[/red]")
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
            "\n[bold]\U0001f43b What can I do?[/bold]\n"
            "\n"
            "  [bold]Learning[/bold]\n"
            "  /learn     \u2014 Socratic tutoring (e.g. /learn binary search trees)\n"
            "  /study     \u2014 Generate study guide PDF (10-25 pages)\n"
            "  /cheatsheet \u2014 Generate 2-page exam cheatsheet\n"
            "\n"
            "  [bold]Academics[/bold]\n"
            "  /grades    \u2014 Quick grade check\n"
            "  /gpa       \u2014 GPA calculator (or /gpa 3.5 for target)\n"
            "  /courses   \u2014 List your courses\n"
            "  /remind    \u2014 Set a reminder\n"
            "\n"
            "  [bold]Session[/bold]\n"
            "  /new       \u2014 Save context + start fresh\n"
            "  /clear     \u2014 Nuke conversation history\n"
            "  /config    \u2014 Show config path\n"
            "  /quit      \u2014 Exit\n"
        )
        return True, None

    if cmd == "/courses":
        courses = cfg.get("courses", {})
        for cid, name in courses.items():
            console.print(f"  {cid} | {name}")
        return True, None

    if cmd.startswith("/learn"):
        topic = cmd[6:].strip()
        if topic:
            return False, f"I want to learn about: {topic}. Teach me step by step using the Socratic method. Start by asking what I already know, then guide me through it — don't just explain. Use my course materials."
        return False, "I want to study something. What topic should we work on? Pick from my courses."

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
            console.print("[dim]Context saved. Fresh start \u2014 let's go.[/dim]")
        else:
            console.print("[dim]Already fresh.[/dim]")
        return True, None

    if cmd == "/clear":
        messages.clear()
        console.print("[dim]Cleared.[/dim]")
        return True, None

    if cmd.startswith("/study"):
        topic = cmd[6:].strip()
        if topic:
            return False, f"Generate a comprehensive study guide PDF for: {topic}. Read my course materials first, then create a detailed two-column LaTeX study guide (10-25 pages). Adapt the structure to the subject."
        return False, "Which course or topic should I make a study guide for?"

    if cmd.startswith("/cheatsheet"):
        topic = cmd[11:].strip()
        if topic:
            return False, f"Generate a dense 2-page exam cheatsheet PDF for: {topic}. Read my course materials first, then create an ultra-compact reference sheet."
        return False, "Which course or topic should I make a cheatsheet for?"

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
