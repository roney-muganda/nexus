import logging
from telegram import Bot
from hub.config import settings

logger = logging.getLogger(__name__)


async def send_telegram_message(chat_id: int, text: str) -> bool:
    try:
        bot = Bot(token=settings.telegram_bot_token)
        if len(text) > 4096:
            chunks = [text[i:i+4096] for i in range(0, len(text), 4096)]
            for chunk in chunks:
                await bot.send_message(chat_id=chat_id, text=chunk)
        else:
            await bot.send_message(chat_id=chat_id, text=text)
        return True
    except Exception as e:
        logger.exception(f"Failed to send Telegram message to {chat_id}: {e}")
        return False


async def send_reminder_notification(chat_id: int, title: str, notes: str = None):
    text = f"⏰ *Reminder:* {title}"
    if notes:
        text += f"\n\n{notes}"
    await send_telegram_message(chat_id=chat_id, text=text)