import logging
import uuid
from fastapi import APIRouter, Request, HTTPException
from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from hub.config import settings
from hub.models.database import AsyncSessionLocal
from hub.models.user import User
from hub.core.orchestrator import Orchestrator

logger = logging.getLogger(__name__)
router = APIRouter()

# build the telegram application once at module level
telegram_app = (
    Application.builder()
    .token(settings.telegram_bot_token)
    .build()
)


async def get_or_create_user_by_telegram_id(
    db: AsyncSession,
    telegram_id: int,
    username: str = None,
    full_name: str = None,
) -> User:
    # look up user by telegram_id stored in preferences metadata
    result = await db.execute(
        select(User).where(
            User.email == f"telegram_{telegram_id}@nexus.local"
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        from hub.auth.password import hash_password
        from hub.models.user_preferences import UserPreferences
        user = User(
            email=f"telegram_{telegram_id}@nexus.local",
            hashed_password=hash_password(str(uuid.uuid4())),
            full_name=full_name or username or f"Telegram User {telegram_id}",
            is_active=True,
        )
        db.add(user)
        await db.flush()

        prefs = UserPreferences(
            user_id=user.id,
            preferred_channels=["telegram"],
        )
        db.add(prefs)
        await db.commit()
        await db.refresh(user)
        logger.info(f"Created new user for Telegram ID {telegram_id}")

    return user


async def get_session_id_for_chat(telegram_chat_id: int) -> str:
    # use a deterministic session ID per Telegram chat
    # so conversation history persists across messages
    import hashlib
    raw = f"telegram_chat_{telegram_chat_id}"
    return str(uuid.UUID(hashlib.md5(raw.encode()).hexdigest()))


@router.post("/webhook")
async def telegram_webhook(request: Request):
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
    text = message.text
    username = message.from_user.username
    full_name = message.from_user.full_name

    # handle commands
    if text.startswith("/start"):
        await telegram_app.bot.send_message(
            chat_id=chat_id,
            text=(
                "👋 Hey! I'm NEXUS, your personal AI assistant.\n\n"
                "I can help you with:\n"
                "• Setting reminders and managing tasks\n"
                "• Storing and reviewing what you're learning\n"
                "• Searching your technical docs\n"
                "• Managing your projects\n\n"
                "Just talk to me naturally. What's on your mind?"
            )
        )
        return {"ok": True}

    if text.startswith("/help"):
        await telegram_app.bot.send_message(
            chat_id=chat_id,
            text=(
                "Here's what you can ask me:\n\n"
                "📋 *Tasks & Reminders*\n"
                "• 'Remind me to review my notes at 9am tomorrow'\n"
                "• 'What are my pending tasks?'\n\n"
                "📚 *Learning*\n"
                "• 'I just learned that...'\n"
                "• 'Quiz me on civil engineering'\n"
                "• 'What have I been studying this week?'\n\n"
                "💻 *Projects*\n"
                "• 'What's the status of my NEXUS project?'\n"
                "• 'Mark the auth task as done'\n\n"
                "🧠 *Memory*\n"
                "• 'Remember that I prefer Python over JavaScript'\n"
                "• 'What do you know about me?'"
            ),
            parse_mode="Markdown"
        )
        return {"ok": True}

    if text.startswith("/new"):
        # force a new conversation session
        await telegram_app.bot.send_message(
            chat_id=chat_id,
            text="Starting a fresh conversation. What's up?"
        )
        return {"ok": True}

    # send typing indicator
    await telegram_app.bot.send_chat_action(chat_id=chat_id, action="typing")

    async with AsyncSessionLocal() as db:
        try:
            user = await get_or_create_user_by_telegram_id(
                db=db,
                telegram_id=telegram_id,
                username=username,
                full_name=full_name,
            )

            session_id = await get_session_id_for_chat(chat_id)
            orchestrator = Orchestrator(db=db, user_id=str(user.id))

            reply = await orchestrator.run(
                user_message=text,
                session_id=session_id,
                device="telegram"
            )

            # split long messages — Telegram has a 4096 char limit
            if len(reply) > 4096:
                chunks = [reply[i:i+4096] for i in range(0, len(reply), 4096)]
                for chunk in chunks:
                    await telegram_app.bot.send_message(
                        chat_id=chat_id,
                        text=chunk
                    )
            else:
                await telegram_app.bot.send_message(
                    chat_id=chat_id,
                    text=reply
                )

        except Exception as e:
            logger.exception(f"Error processing Telegram message: {e}")
            await telegram_app.bot.send_message(
                chat_id=chat_id,
                text="Sorry, I ran into an issue processing that. Please try again."
            )

    return {"ok": True}