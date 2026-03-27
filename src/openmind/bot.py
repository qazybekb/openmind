"""Telegram bot — message handling + background heartbeat."""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
import threading
from pathlib import Path
from typing import Any, Final, TypeAlias

from telegram import ChatAction, InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from rich.console import Console

from openmind.config import ConfigDict
from openmind.heartbeat import HEARTBEAT_INTERVAL, start_heartbeat
from openmind.llm import chat, create_client

ChatMessage: TypeAlias = dict[str, Any]

MAX_CONVERSATION_MESSAGES: Final[int] = 60
MESSAGE_CHUNK_SIZE: Final[int] = 4_000

console: Console = Console()
logger = logging.getLogger(__name__)

# Per-user conversation state
_conversations: dict[str, list[ChatMessage]] = {}


def _quick_action_keyboard() -> InlineKeyboardMarkup:
    """Build the inline keyboard with quick-action buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f4cc Deadlines", callback_data="deadlines"),
            InlineKeyboardButton("\U0001f4ca Grades", callback_data="grades"),
            InlineKeyboardButton("\U0001f393 GPA", callback_data="gpa"),
        ],
        [
            InlineKeyboardButton("\U0001f9e0 Learn", callback_data="learn"),
            InlineKeyboardButton("\U0001f4d6 Study Plan", callback_data="study_plan"),
            InlineKeyboardButton("\U0001f4e2 Announcements", callback_data="announcements"),
        ],
    ])


def _after_response_keyboard() -> InlineKeyboardMarkup:
    """Compact keyboard shown after each response."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("\U0001f4cc Deadlines", callback_data="deadlines"),
            InlineKeyboardButton("\U0001f4ca Grades", callback_data="grades"),
            InlineKeyboardButton("\U0001f9e0 Learn", callback_data="learn"),
            InlineKeyboardButton("\u2753 Menu", callback_data="menu"),
        ],
    ])


def _sanitize_markdown(text: str) -> str:
    """Clean up markdown that Telegram can't handle.

    Telegram Markdown V1 is limited — unmatched *, **, `, and _ cause parse errors.
    This does best-effort cleanup without losing all formatting.
    """
    # Fix unmatched backticks (code blocks)
    if text.count("```") % 2 != 0:
        text += "\n```"
    # Fix unmatched inline backticks
    if text.count("`") % 2 != 0:
        text = text.rstrip("`") + "`"
    # Fix unmatched bold
    if text.count("**") % 2 != 0:
        text += "**"
    # Fix unmatched italic (single *)  — tricky, just remove trailing lone *
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        # Count unescaped * that aren't part of ** or ***
        single_stars = len(re.findall(r'(?<!\*)\*(?!\*)', line))
        if single_stars % 2 != 0:
            line = line.rstrip("*")
        cleaned.append(line)
    return "\n".join(cleaned)


def _prune_conversation(messages: list[ChatMessage]) -> None:
    """Keep conversation within bounds to prevent memory bloat."""
    if len(messages) > MAX_CONVERSATION_MESSAGES:
        # Keep the most recent messages, always in pairs
        del messages[: len(messages) - MAX_CONVERSATION_MESSAGES]


def run_bot(cfg: ConfigDict) -> None:
    """Start the Telegram bot with a background heartbeat thread."""
    tg = cfg.get("telegram", {})
    bot_token = str(tg.get("bot_token", ""))
    allowed_user = str(tg.get("user_id", ""))
    uni = cfg.get("university", {})

    if not bot_token:
        console.print("[red]Telegram bot token not configured.[/red] Run: openmind setup")
        return

    console.print(f"\n{uni.get('mascot', '')} Starting bot... {uni.get('spirit', '')}")
    console.print(f"[dim]Telegram bot active. Heartbeat every {HEARTBEAT_INTERVAL // 3600} hours.[/dim]")
    console.print("[dim]Press Ctrl+C to stop.[/dim]\n")

    llm_client = create_client(cfg)

    async def _chat_with_typing(chat_id: int, messages: list[ChatMessage]) -> str:
        """Run LLM chat with typing indicator. Shared by all handlers."""
        typing_active = True

        async def _keep_typing() -> None:
            while typing_active:
                try:
                    await application.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                except Exception:
                    pass
                await asyncio.sleep(4)

        typing_task = asyncio.create_task(_keep_typing())
        try:
            return await asyncio.to_thread(chat, cfg, messages, client=llm_client)
        finally:
            typing_active = False
            typing_task.cancel()

    async def _send_response(chat_id: int, response: str, reply_to: Any = None, show_buttons: bool = True) -> None:
        """Send a response, handling chunking, markdown, and PDFs."""
        chunks = [response[i: i + MESSAGE_CHUNK_SIZE] for i in range(0, len(response), MESSAGE_CHUNK_SIZE)]

        for idx, chunk in enumerate(chunks):
            is_last = idx == len(chunks) - 1
            cleaned = _sanitize_markdown(chunk)
            keyboard = _after_response_keyboard() if is_last and show_buttons else None

            try:
                if reply_to:
                    await reply_to.reply_text(cleaned, parse_mode="Markdown", reply_markup=keyboard)
                else:
                    await application.bot.send_message(chat_id=chat_id, text=cleaned, parse_mode="Markdown", reply_markup=keyboard)
            except Exception:
                logger.warning("Markdown reply failed; falling back to plain text.", exc_info=True)
                if reply_to:
                    await reply_to.reply_text(chunk, reply_markup=keyboard)
                else:
                    await application.bot.send_message(chat_id=chat_id, text=chunk, reply_markup=keyboard)

        # Send any generated PDFs
        await _send_generated_pdfs(chat_id, response)

    async def handle_message(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            await update.effective_message.reply_text(
                "This is a private bot. Set up your own: openmindbot.io"
            )
            return

        # Handle PDF documents
        if update.effective_message.document:
            doc = update.effective_message.document
            if doc.file_name and doc.file_name.lower().endswith(".pdf"):
                await _handle_pdf(update, user_id, doc)
                return
            await update.effective_message.reply_text(
                "I can read PDF files. Send me a .pdf and I'll summarize it!"
            )
            return

        text = update.effective_message.text
        if not text:
            return

        if user_id not in _conversations:
            _conversations[user_id] = []
        messages = _conversations[user_id]
        messages.append({"role": "user", "content": text})

        try:
            response = await _chat_with_typing(update.effective_message.chat_id, messages)
            messages.append({"role": "assistant", "content": response})
            _prune_conversation(messages)
            await _send_response(update.effective_message.chat_id, response, reply_to=update.effective_message)
        except Exception as exc:
            logger.exception("Error handling message")
            err_msg = str(exc).lower()
            if "timeout" in err_msg:
                reply = "The AI model took too long to respond. Try a shorter question or try again."
            elif "401" in err_msg or "auth" in err_msg:
                reply = "Authentication error with your AI model. Check your OpenRouter key."
            else:
                reply = "Something went wrong \u2014 this might be a network issue. Try again in a moment."
            await update.effective_message.reply_text(reply)
            messages.pop()

    async def _handle_pdf(update: Update, user_id: str, doc: Any) -> None:
        """Download a PDF sent by the user, extract text, and feed to LLM."""
        chat_id = update.effective_message.chat_id  # type: ignore[union-attr]
        try:
            await application.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

            file = await doc.get_file()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                tmp_path = tmp.name

            try:
                import pymupdf
                pdf_doc = pymupdf.open(tmp_path)
                text_parts = [page.get_text() for page in pdf_doc]
                pdf_doc.close()
                pdf_text = "\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            if not pdf_text.strip():
                await update.effective_message.reply_text(  # type: ignore[union-attr]
                    "I couldn't extract text from this PDF. It might be image-based or scanned."
                )
                return

            if len(pdf_text) > 30000:
                pdf_text = pdf_text[:30000] + "\n... (truncated)"

            caption = update.effective_message.caption or ""  # type: ignore[union-attr]
            user_msg = f"I'm sending you a PDF: {doc.file_name}\n"
            if caption:
                user_msg += f"My question: {caption}\n"
            else:
                user_msg += "Please summarize the key points.\n"
            user_msg += f"\nPDF content:\n{pdf_text}"

            if user_id not in _conversations:
                _conversations[user_id] = []
            messages = _conversations[user_id]
            messages.append({"role": "user", "content": user_msg})

            try:
                response = await _chat_with_typing(chat_id, messages)
                messages.append({"role": "assistant", "content": response})
                _prune_conversation(messages)
                await _send_response(chat_id, response, reply_to=update.effective_message)  # type: ignore[union-attr]
            except Exception:
                messages.pop()  # Clean up on failure
                raise

        except Exception:
            logger.exception("Error handling PDF")
            await update.effective_message.reply_text(  # type: ignore[union-attr]
                "Something went wrong reading that PDF. Try again or send a different file."
            )

    async def _send_generated_pdfs(chat_id: int, response: str) -> None:
        """Check if the LLM response mentions a generated PDF file and send it."""
        pdf_paths = re.findall(r'(/[^\s"\']+\.pdf)', response)
        for pdf_path in pdf_paths:
            path = Path(pdf_path)
            if path.exists() and path.stat().st_size > 0:
                try:
                    with path.open("rb") as f:
                        await application.bot.send_document(
                            chat_id=chat_id,
                            document=f,
                            filename=path.name,
                            caption=f"\U0001f4da {path.stem.replace('_', ' ')}",
                        )
                except Exception:
                    logger.warning("Failed to send PDF %s via Telegram", pdf_path, exc_info=True)

    async def cmd_start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            await update.effective_message.reply_text("This is a private bot. Set up your own: openmindbot.io")
            return
        name = cfg.get("user_name", "there")
        keyboard = _quick_action_keyboard()
        await update.effective_message.reply_text(
            f"Hey {name}! {uni.get('spirit', '')} {uni.get('mascot', '')}\n"
            f"I'm your {uni.get('name', '')} study buddy. Ask me anything!\n\n"
            f"Commands: /help /clear /menu",
            reply_markup=keyboard,
        )

    async def cmd_help(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        await update.effective_message.reply_text(
            "\U0001f43b *OpenMind Commands*\n\n"
            "*Learning:*\n"
            "/learn [topic] \u2014 Guided Socratic tutoring\n"
            "/study [course] \u2014 Generate study guide PDF\n"
            "/cheatsheet [course] \u2014 Generate exam cheatsheet PDF\n\n"
            "*Academics:*\n"
            "/grades \u2014 All course grades\n"
            "/gpa [target] \u2014 GPA calculator\n"
            "/courses \u2014 List your courses\n"
            "/remind [text] \u2014 Set a reminder\n\n"
            "*Session:*\n"
            "/new \u2014 Save context + start fresh\n"
            "/clear \u2014 Clear conversation\n"
            "/menu \u2014 Quick action buttons\n"
            "/help \u2014 This message\n\n"
            "Or just type naturally! Send a PDF to summarize it.\n"
            "Guides: openmindbot.io/guides",
            parse_mode="Markdown",
            reply_markup=_quick_action_keyboard(),
        )

    async def cmd_menu(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        await update.effective_message.reply_text(
            "What do you need?",
            reply_markup=_quick_action_keyboard(),
        )

    async def cmd_clear(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = str(update.effective_user.id)
        msg_count = len(_conversations.get(user_id, []))
        _conversations.pop(user_id, None)
        await update.effective_message.reply_text(
            f"Conversation cleared ({msg_count} messages removed) \u2705",
            reply_markup=_quick_action_keyboard(),
        )

    async def handle_button(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle inline keyboard button presses."""
        query = update.callback_query
        if query is None:
            return
        await query.answer()

        user_id = str(query.from_user.id) if query.from_user else ""
        if allowed_user and user_id != allowed_user:
            return

        button_queries = {
            "deadlines": "What's due this week? Show urgency and grade weight.",
            "grades": "Show all my grades across every course.",
            "gpa": "Calculate my current GPA across all courses.",
            "learn": "I want to study something. What topic should we work on? Pick from my courses and upcoming exams.",
            "study_plan": "Create a study plan for this week based on my deadlines and priorities.",
            "announcements": "Any new announcements from my courses?",
            "menu": None,  # Special: just show menu
        }

        if str(query.data) == "menu":
            chat_id = query.message.chat_id if query.message else None
            if chat_id:
                await application.bot.send_message(
                    chat_id=chat_id,
                    text="What do you need?",
                    reply_markup=_quick_action_keyboard(),
                )
            return

        text = button_queries.get(str(query.data), "")
        if not text:
            return

        if user_id not in _conversations:
            _conversations[user_id] = []
        messages = _conversations[user_id]
        messages.append({"role": "user", "content": text})

        chat_id = query.message.chat_id if query.message else None
        if not chat_id:
            return

        try:
            response = await _chat_with_typing(chat_id, messages)
            messages.append({"role": "assistant", "content": response})
            _prune_conversation(messages)
            await _send_response(chat_id, response)
        except Exception:
            logger.exception("Error handling button")
            await application.bot.send_message(
                chat_id=chat_id,
                text="Something went wrong. Try again in a moment.",
            )
            messages.pop()

    async def _route_slash_to_llm(update: Update, user_id: str, text: str) -> None:
        """Route a slash command as an LLM query — mirrors REPL behavior."""
        if user_id not in _conversations:
            _conversations[user_id] = []
        messages = _conversations[user_id]
        messages.append({"role": "user", "content": text})
        chat_id = update.effective_message.chat_id  # type: ignore[union-attr]
        try:
            response = await _chat_with_typing(chat_id, messages)
            messages.append({"role": "assistant", "content": response})
            _prune_conversation(messages)
            await _send_response(chat_id, response, reply_to=update.effective_message)
        except Exception:
            logger.exception("Error handling slash command")
            await update.effective_message.reply_text(  # type: ignore[union-attr]
                "Something went wrong. Try again in a moment."
            )
            messages.pop()

    async def cmd_grades(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        await _route_slash_to_llm(update, user_id, "What are my grades across all courses?")

    async def cmd_gpa(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        text = update.effective_message.text or ""
        target = text.replace("/gpa", "").strip()
        if target:
            query = f"Calculate my GPA and what I need to get a {target} GPA."
        else:
            query = "Calculate my current GPA across all courses."
        await _route_slash_to_llm(update, user_id, query)

    async def cmd_learn(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        text = update.effective_message.text or ""
        topic = text.replace("/learn", "").strip()
        if topic:
            query = f"I want to learn about: {topic}. Teach me step by step using the Socratic method. Start by asking what I already know, then guide me through it. Use my course materials."
        else:
            query = "I want to study something. What topic should we work on? Pick from my courses."
        await _route_slash_to_llm(update, user_id, query)

    async def cmd_study(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        text = update.effective_message.text or ""
        topic = text.replace("/study", "").strip()
        if topic:
            query = f"Generate a comprehensive study guide PDF for: {topic}. Read my course materials first, then create a detailed two-column LaTeX study guide (10-25 pages). Adapt the structure to the subject."
        else:
            query = "Which course or topic should I make a study guide for?"
        await _route_slash_to_llm(update, user_id, query)

    async def cmd_cheatsheet(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        text = update.effective_message.text or ""
        topic = text.replace("/cheatsheet", "").strip()
        if topic:
            query = f"Generate a dense 2-page exam cheatsheet PDF for: {topic}. Read my course materials first, then create an ultra-compact reference sheet."
        else:
            query = "Which course or topic should I make a cheatsheet for?"
        await _route_slash_to_llm(update, user_id, query)

    async def cmd_courses(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        courses = cfg.get("courses", {})
        if not courses:
            await update.effective_message.reply_text("No courses configured.")
            return
        lines = [f"`{cid}` | {name}" for cid, name in courses.items()]
        await update.effective_message.reply_text(
            "\U0001f4da *Your courses:*\n\n" + "\n".join(lines),
            parse_mode="Markdown",
        )

    async def cmd_remind(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        text = update.effective_message.text or ""
        reminder = text.replace("/remind", "").strip()
        if reminder:
            query = f"Set a reminder: {reminder}"
        else:
            query = "I want to set a reminder. Ask me what and when."
        await _route_slash_to_llm(update, user_id, query)

    async def cmd_new(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return
        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        messages = _conversations.get(user_id, [])
        if messages:
            from openmind.memory import consolidate_conversation
            consolidate_conversation(messages)
            _conversations.pop(user_id, None)
            await update.effective_message.reply_text(
                "Conversation saved to memory and cleared. Starting fresh! \U0001f43b",
                reply_markup=_quick_action_keyboard(),
            )
        else:
            await update.effective_message.reply_text(
                "Already a fresh conversation.",
                reply_markup=_quick_action_keyboard(),
            )

    # Background heartbeat
    heartbeat_thread = threading.Thread(
        target=start_heartbeat,
        args=(cfg, bot_token, allowed_user),
        daemon=True,
    )
    heartbeat_thread.start()

    # Telegram application
    application = Application.builder().token(bot_token).build()
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("help", cmd_help))
    application.add_handler(CommandHandler("menu", cmd_menu))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CommandHandler("new", cmd_new))
    application.add_handler(CommandHandler("grades", cmd_grades))
    application.add_handler(CommandHandler("gpa", cmd_gpa))
    application.add_handler(CommandHandler("learn", cmd_learn))
    application.add_handler(CommandHandler("study", cmd_study))
    application.add_handler(CommandHandler("cheatsheet", cmd_cheatsheet))
    application.add_handler(CommandHandler("courses", cmd_courses))
    application.add_handler(CommandHandler("remind", cmd_remind))
    application.add_handler(CallbackQueryHandler(handle_button))
    application.add_handler(MessageHandler((filters.TEXT | filters.Document.ALL) & ~filters.COMMAND, handle_message))

    # Use explicit async lifecycle so this works in a background thread
    async def _run() -> None:
        async with application:
            await application.start()
            await application.updater.start_polling()  # type: ignore[union-attr]
            stop_event = asyncio.Event()
            await stop_event.wait()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    except Exception:
        logger.exception("Telegram bot stopped")
    finally:
        loop.close()
