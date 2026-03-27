"""Telegram bot — message handling + background heartbeat."""

from __future__ import annotations

import asyncio
import logging
import threading
from typing import Any, Final, TypeAlias

from telegram import ChatAction, Update
from telegram.ext import (
    Application,
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

MESSAGE_CHUNK_SIZE: Final[int] = 4_000

console: Console = Console()
logger = logging.getLogger(__name__)

# Per-user conversation state
_conversations: dict[str, list[ChatMessage]] = {}


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
        except Exception:
            logger.exception("Error handling message")
            await update.effective_message.reply_text(
                "Something went wrong while handling that request. Try again in a sec."
            )
            messages.pop()

    async def cmd_start(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = str(update.effective_user.id)
        if allowed_user and user_id != allowed_user:
            return
        name = cfg.get("user_name", "there")
        await update.effective_message.reply_text(
            f"Hey {name}! {uni.get('spirit', '')} {uni.get('mascot', '')}\n"
            f"I'm your {uni.get('name', '')} study buddy. Ask me anything!"
        )

    async def cmd_clear(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_user is None or update.effective_message is None:
            return

        user_id = str(update.effective_user.id)
        _conversations.pop(user_id, None)
        await update.effective_message.reply_text("Conversation cleared \u2705")

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
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

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
