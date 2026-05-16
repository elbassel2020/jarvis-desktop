"""
Telegram bot bridge for @MSMA_Walid_bot.
Only processes messages from WALID_CHAT_ID — all others silently rejected.
"""
import logging
import time
from typing import Callable

from jarvis.security.credential_broker import broker
from jarvis.security.audit import write_audit

_logger = logging.getLogger("jarvis.telegram")

WALID_CHAT_ID = 1032010360  # Only Walid's chat is accepted


async def _build_app(token: str):
    from telegram.ext import Application
    return Application.builder().token(token).build()


async def start_polling(callback: Callable) -> object:
    """Start Telegram polling. callback(text, chat_id) called per allowed message."""
    from telegram.ext import MessageHandler, filters
    from telegram import Update

    token = broker.resolve("cred://telegram/msma-walid-bot")
    app = await _build_app(token)

    async def handler(update: Update, context):
        chat_id = update.effective_chat.id
        if chat_id != WALID_CHAT_ID:
            _logger.warning(f"Rejected Telegram message from chat_id={chat_id}")
            return
        text = update.message.text or ""
        write_audit(actor="telegram", action="message_received",
                    params={"chat_id": chat_id, "preview": text[:100]},
                    outcome="ok", egress_host="api.telegram.org")
        await callback(text, chat_id)

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler))
    await app.initialize()
    await app.start()
    await app.updater.start_polling()
    _logger.info("Telegram polling started (WALID_CHAT_ID only)")
    return app


async def send_to_walid(text: str) -> bool:
    """Send a message to Walid's chat. Returns True on success."""
    t0 = time.monotonic()
    try:
        from telegram import Bot
        token = broker.resolve("cred://telegram/msma-walid-bot")
        bot = Bot(token=token)
        await bot.send_message(chat_id=WALID_CHAT_ID, text=text[:4000])
        duration_ms = int((time.monotonic() - t0) * 1000)
        write_audit(actor="telegram", action="send_to_walid",
                    params={"preview": text[:100]},
                    outcome="ok", egress_host="api.telegram.org",
                    duration_ms=duration_ms)
        return True
    except Exception as e:
        write_audit(actor="telegram", action="send_to_walid",
                    outcome="error", notes=str(e)[:200])
        return False
