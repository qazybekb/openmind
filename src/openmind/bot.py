"""Telegram bot — message handling + background heartbeat."""

from __future__ import annotations

import asyncio
import logging
import threading
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

import tempfile
from pathlib import Path
from rich.console import Console

from openmind.config import ConfigDict
from openmind.heartbeat import HEARTBEAT_INTERVAL, start_heartbeat
from openmind.llm import chat, create_client

ChatMessage: TypeAlias = dict[str, Any]

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

    async def handle_message(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return

        text = update.effective_message.text

        # Handle PDF documents
        if update.effective_message.document:
            doc = update.effective_message.document
            if doc.file_name and doc.file_name.lower().endswith(".pdf"):
                await _handle_pdf(update, user_id, doc)
                return

        if not text:
            return

        if user_id not in _conversations:
            _conversations[user_id] = []
        messages = _conversations[user_id]
        messages.append({"role": "user", "content": text})

        try:
            # Show "typing..." while the LLM is working
            chat_id = update.effective_message.chat_id
            typing_active = True

            async def _keep_typing() -> None:
                while typing_active:
                    try:
                        await application.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                    except Exception:
                        pass
                    await asyncio.sleep(4)  # Telegram typing expires after 5s

            typing_task = asyncio.create_task(_keep_typing())

            try:
                response = await asyncio.to_thread(chat, cfg, messages, client=llm_client)
            finally:
                typing_active = False
                typing_task.cancel()

            messages.append({"role": "assistant", "content": response})

            # Telegram limits messages to 4096 characters
            for i in range(0, len(response), MESSAGE_CHUNK_SIZE):
                chunk = response[i : i + MESSAGE_CHUNK_SIZE]
                try:
                    await update.effective_message.reply_text(chunk, parse_mode="Markdown")
                except Exception:
                    logger.warning("Telegram Markdown reply failed; falling back to plain text.", exc_info=True)
                    await update.effective_message.reply_text(chunk)

            # Send any generated PDFs (study guides, cheatsheets)
            await _send_generated_pdfs(update.effective_message.chat_id, response)
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

            # Download to temp file
            file = await doc.get_file()
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                await file.download_to_drive(tmp.name)
                tmp_path = tmp.name

            # Extract text with pymupdf
            try:
                import pymupdf
                pdf_doc = pymupdf.open(tmp_path)
                text_parts = []
                for page in pdf_doc:
                    text_parts.append(page.get_text())
                pdf_doc.close()
                pdf_text = "\n".join(text_parts)
            finally:
                Path(tmp_path).unlink(missing_ok=True)

            if not pdf_text.strip():
                await update.effective_message.reply_text(  # type: ignore[union-attr]
                    "I couldn't extract text from this PDF. It might be image-based."
                )
                return

            # Truncate if very long
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

            typing_active = True

            async def _keep_typing_pdf() -> None:
                while typing_active:
                    try:
                        await application.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
                    except Exception:
                        pass
                    await asyncio.sleep(4)

            typing_task = asyncio.create_task(_keep_typing_pdf())
            try:
                response = await asyncio.to_thread(chat, cfg, messages, client=llm_client)
            finally:
                typing_active = False
                typing_task.cancel()

            messages.append({"role": "assistant", "content": response})

            for i in range(0, len(response), MESSAGE_CHUNK_SIZE):
                chunk = response[i : i + MESSAGE_CHUNK_SIZE]
                try:
                    await update.effective_message.reply_text(chunk, parse_mode="Markdown")  # type: ignore[union-attr]
                except Exception:
                    await update.effective_message.reply_text(chunk)  # type: ignore[union-attr]

            # If the response mentions a generated PDF, send it
            await _send_generated_pdfs(chat_id, response)

        except Exception:
            logger.exception("Error handling PDF")
            await update.effective_message.reply_text(  # type: ignore[union-attr]
                "Something went wrong reading that PDF. Try again."
            )

    async def _send_generated_pdfs(chat_id: int, response: str) -> None:
        """Check if the LLM response mentions a generated PDF file and send it."""
        import re
        # Look for paths in the response that end in .pdf
        pdf_paths = re.findall(r'(/[^\s"\']+\.pdf)', response)
        for pdf_path in pdf_paths:
            path = Path(pdf_path)
            if path.exists() and path.stat().st_size > 0:
                try:
                    await application.bot.send_document(
                        chat_id=chat_id,
                        document=path.open("rb"),
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
            return
        name = cfg.get("user_name", "there")
        keyboard = _quick_action_keyboard()
        await update.effective_message.reply_text(
            f"Hey {name}! {uni.get('spirit', '')} {uni.get('mascot', '')}\n"
            f"I'm your {uni.get('name', '')} study buddy. Ask me anything!",
            reply_markup=keyboard,
        )

    async def cmd_clear(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = str(update.effective_user.id)
        _conversations.pop(user_id, None)
        await update.effective_message.reply_text("Conversation cleared \u2705")

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
        }

        text = button_queries.get(str(query.data), "")
        if not text:
            return

        # Simulate a regular message
        if user_id not in _conversations:
            _conversations[user_id] = []
        messages = _conversations[user_id]
        messages.append({"role": "user", "content": text})

        chat_id = query.message.chat_id if query.message else None
        if not chat_id:
            return

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
            response = await asyncio.to_thread(chat, cfg, messages, client=llm_client)
        finally:
            typing_active = False
            typing_task.cancel()

        messages.append({"role": "assistant", "content": response})

        for i in range(0, len(response), MESSAGE_CHUNK_SIZE):
            chunk = response[i : i + MESSAGE_CHUNK_SIZE]
            try:
                await application.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="Markdown")
            except Exception:
                await application.bot.send_message(chat_id=chat_id, text=chunk)

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
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CallbackQueryHandler(handle_button))
    application.add_handler(MessageHandler((filters.TEXT | filters.Document.PDF) & ~filters.COMMAND, handle_message))

    # Use explicit async lifecycle so this works in a background thread
    async def _run() -> None:
        async with application:
            await application.start()
            await application.updater.start_polling()  # type: ignore[union-attr]
            # Block until cancelled
            stop_event = asyncio.Event()
            await stop_event.wait()

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_run())
    except Exception:
        logger.exception("Telegram bot stopped")
    finally:
        loop.close()
