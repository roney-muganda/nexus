import logging
import uuid
import os
from datetime import datetime, timezone
from hub.core.redis_client import cache_get, cache_set
from fastapi import APIRouter, Request, HTTPException, Header, status
from telegram import Update, Bot
from telegram.ext import Application
from sqlalchemy import select, update
from hub.config import settings
from hub.models.database import AsyncSessionLocal
from hub.models.user import User
from hub.models.user_preferences import UserPreferences
from hub.models.telegram_link import TelegramLink
from hub.core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

telegram_app = (
    Application.builder()
    .token(settings.telegram_bot_token)
    .build()
)


async def get_user_by_telegram_chat_id(db, chat_id: int):
    cache_key = f"telegram_user:{chat_id}"
    cached = await cache_get(cache_key)

    if cached and "user_id" in cached:
        # Cast the cached string back to a UUID for the Postgres query
        try:
            user_uuid = uuid.UUID(cached["user_id"])
            result = await db.execute(
                select(User).where(User.id == user_uuid)
            )
            return result.scalar_one_or_none()
        except ValueError:
            pass # Fallback to DB if UUID casting somehow fails

    # Cache Miss: Find the user via their preferences
    result = await db.execute(
        select(UserPreferences).where(
            UserPreferences.telegram_chat_id == chat_id
        )
    )
    prefs = result.scalar_one_or_none()
    
    if not prefs:
        return None

    # Fetch the actual user object
    result = await db.execute(
        select(User).where(User.id == prefs.user_id)
    )
    user = result.scalar_one_or_none()

    if user:
        # Cache the mapping for 1 hour (3600 seconds)
        await cache_set(cache_key, {
            "user_id": str(user.id)
        }, ttl_seconds=3600)

    return user


async def get_session_id_for_chat(telegram_chat_id: int) -> str:
    import hashlib
    raw = f"telegram_chat_{telegram_chat_id}"
    return str(uuid.UUID(hashlib.md5(raw.encode()).hexdigest()))


@router.post("/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None)
):
    # 1. Webhook Authentication to prevent forged arbitrary requests
    secret_token = os.getenv("TELEGRAM_SECRET_TOKEN")
    if secret_token and x_telegram_bot_api_secret_token != secret_token:
        logger.warning("Rejected Telegram webhook: Secret token mismatch.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="Unauthorized webhook request"
        )

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    update = Update.de_json(data, telegram_app.bot)

    if not update.message or not update.message.text:
        return {"ok": True}

    message = update.message
    telegram_id = message.from_user.id
    chat_id = message.chat_id
    text = message.text.strip()
    full_name = message.from_user.full_name

    # ── /start ──────────────────────────────────────────
    if text.startswith("/start"):
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_chat_id(db, chat_id)

        if user:
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text=f"Welcome back {user.full_name}! What's on your mind?"
            )
        else:
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text=(
                    "👋 Hi! I'm NEXUS.\n\n"
                    "To get started, link your account:\n\n"
                    "1. Log into the NEXUS web API\n"
                    "2. Call POST /api/auth/telegram/generate-link-code\n"
                    "3. Send me: /link YOUR_CODE\n\n"
                    "This connects your Telegram to your NEXUS brain."
                )
            )
        return {"ok": True}

    # ── /link CODE ───────────────────────────────────────
    if text.startswith("/link"):
        parts = text.split()
        if len(parts) != 2:
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text="Usage: /link 123456"
            )
            return {"ok": True}

        code = parts[1].strip()

        async with AsyncSessionLocal() as db:
            # find the code
            result = await db.execute(
                select(TelegramLink).where(
                    TelegramLink.code == code,
                    TelegramLink.used == False,
                    TelegramLink.expires_at > datetime.now(timezone.utc)
                )
            )
            link = result.scalar_one_or_none()

            if not link:
                await telegram_app.bot.send_message(
                    chat_id=chat_id,
                    text="❌ Invalid or expired code. Generate a new one from the API."
                )
                return {"ok": True}

            # mark code as used
            link.used = True
            await db.flush()

            # attach telegram_chat_id to user preferences
            result = await db.execute(
                select(UserPreferences).where(
                    UserPreferences.user_id == link.user_id
                )
            )
            prefs = result.scalar_one_or_none()
            if prefs:
                prefs.telegram_chat_id = chat_id
            else:
                prefs = UserPreferences(
                    user_id=link.user_id,
                    telegram_chat_id=chat_id,
                    preferred_channels=["telegram"]
                )
                db.add(prefs)

            # get user name for confirmation
            result = await db.execute(
                select(User).where(User.id == link.user_id)
            )
            user = result.scalar_one_or_none()
            
            # Commit all database changes
            await db.commit()

        # --- SEED REDIS CACHE ---
        from hub.core.redis_client import cache_set
        await cache_set(f"telegram_user:{chat_id}", {
            "user_id": str(link.user_id)
        }, ttl_seconds=3600)

        await telegram_app.bot.send_message(
            chat_id=chat_id,
            text=(
                f"✅ Linked successfully!\n\n"
                f"Hey {user.full_name if user else 'there'} — "
                f"your Telegram is now connected to your NEXUS account.\n\n"
                f"All your memory, tasks, and projects are available here. "
                f"Just talk to me naturally."
            )
        )
        return {"ok": True}

    # ── /help ────────────────────────────────────────────
    if text.startswith("/help"):
        await telegram_app.bot.send_message(
            chat_id=chat_id,
            text=(
                "Here's what you can ask me:\n\n"
                "📋 *Tasks & Reminders*\n"
                "• Remind me to review my notes at 9am tomorrow\n"
                "• What are my pending tasks?\n\n"
                "📚 *Learning*\n"
                "• I just learned that...\n"
                "• Quiz me on civil engineering\n"
                "• What have I been studying this week?\n\n"
                "💻 *Projects*\n"
                "• What is the status of my NEXUS project?\n"
                "• Mark the auth task as done\n\n"
                "🧠 *Memory*\n"
                "• Remember that I prefer Python over JavaScript\n"
                "• What do you know about me?\n\n"
                "/link CODE — link your account\n"
                "/new — start a fresh conversation"
            ),
            parse_mode="Markdown"
        )
        return {"ok": True}

    # ── /new ─────────────────────────────────────────────
    if text.startswith("/new"):
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_chat_id(db, chat_id)
            
            if user:
                try:
                    session_id = await get_session_id_for_chat(chat_id)
                    orchestrator = Orchestrator(db=db, user_id=str(user.id))
                    
                    # 1. Clear the history from the Postgres database
                    await orchestrator.clear_session(session_id)
                    
                    # 2. Clear the history from the Redis cache
                    from hub.core.redis_client import get_redis
                    r = await get_redis()
                    await r.delete(f"history:{session_id}")
                    
                except Exception as e:
                    logger.error(f"Failed to clear session on /new command: {e}")

        await telegram_app.bot.send_message(
            chat_id=chat_id,
            text="🧹 Conversation history wiped! Starting completely fresh. What's on your mind?"
        )
        return {"ok": True}

    # ── regular message ──────────────────────────────────
    async with AsyncSessionLocal() as db:
        user = await get_user_by_telegram_chat_id(db, chat_id)

        if not user:
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text=(
                    "You haven't linked your account yet.\n\n"
                    "Generate a code from the API:\n"
                    "POST /api/auth/telegram/generate-link-code\n\n"
                    "Then send: /link YOUR_CODE"
                )
            )
            return {"ok": True}

        await telegram_app.bot.send_chat_action(
            chat_id=chat_id, action="typing"
        )

        try:
            session_id = await get_session_id_for_chat(chat_id)
            orchestrator = Orchestrator(db=db, user_id=str(user.id))

            reply = await orchestrator.run(
                user_message=text,
                session_id=session_id,
                device="telegram"
            )

            if len(reply) > 4096:
                chunks = [reply[i:i+4096] for i in range(0, len(reply), 4096)]
                for chunk in chunks:
                    await telegram_app.bot.send_message(
                        chat_id=chat_id, text=chunk
                    )
            else:
                await telegram_app.bot.send_message(
                    chat_id=chat_id, text=reply
                )

        except Exception as e:
            logger.exception(f"Error processing Telegram message: {e}")
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text="Sorry, I ran into an issue. Please try again."
            )

    return {"ok": True}