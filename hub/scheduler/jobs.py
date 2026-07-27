import json
import logging
import zoneinfo
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_

from hub.models.database import AsyncSessionLocal
from hub.models.task import Task, TaskStatus
from hub.models.user import User
from hub.models.user_preferences import UserPreferences
from hub.models.memory_context import MemoryContext, MemoryType
from hub.core.redis_client import get_redis, cache_get, cache_set

logger = logging.getLogger(__name__)

REMINDERS_ZSET_KEY = "reminders:due"


async def fire_due_reminders():
    """
    RUNS EVERY 1 MINUTE:
    Checks Upstash Redis Sorted Set for due reminders. Bypasses Neon completely
    unless a reminder is actively firing.
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    r = await get_redis()

    # 1. Fetch all tasks matching scores from 0 up to 'now' timestamp
    due_items = await r.zrangebyscore(REMINDERS_ZSET_KEY, 0, now_ts)
    if not due_items:
        return

    logger.info(f"⏰ Found {len(due_items)} due reminders in Redis cache.")

    async with AsyncSessionLocal() as db:
        for item_json in due_items:
            try:
                task_data = json.loads(item_json)
                task_id = task_data.get("id")
                user_id = task_data.get("user_id")
                title = task_data.get("title")
                description = task_data.get("description")

                # 2. Check Redis for User Preferences (Telegram Chat ID)
                prefs_key = f"prefs:{user_id}"
                prefs_data = await cache_get(prefs_key)

                if prefs_data:
                    telegram_chat_id = prefs_data.get("telegram_chat_id")
                else:
                    # Cache miss on preferences (Rarely hits DB)
                    prefs_result = await db.execute(
                        select(UserPreferences).where(UserPreferences.user_id == user_id)
                    )
                    prefs = prefs_result.scalar_one_or_none()
                    telegram_chat_id = prefs.telegram_chat_id if prefs else None

                    if prefs:
                        await cache_set(prefs_key, {
                            "telegram_chat_id": prefs.telegram_chat_id,
                            "timezone": prefs.timezone,
                            "daily_briefing_time": prefs.daily_briefing_time,
                        }, ttl_seconds=3600) # Cache preference for 1 hour

                # 3. Fire Telegram Notification
                if telegram_chat_id:
                    from hub.api.telegram_utils import send_reminder_notification
                    await send_reminder_notification(
                        chat_id=telegram_chat_id,
                        title=title,
                        notes=description
                    )
                    logger.info(f"✅ Telegram reminder dispatched for task: {title}")

                # 4. Clear reminder from Postgres so it doesn't double-fire on next sync
                await db.execute(
                    Task.__table__.update()
                    .where(Task.id == task_id)
                    .values(reminder_at=None)
                )
                
                # 5. Remove processing item from Redis Sorted Set
                await r.zrem(REMINDERS_ZSET_KEY, item_json)

            except Exception as e:
                logger.exception(f"Failed to process cached reminder item: {e}")

        await db.commit()


async def sync_upcoming_reminders_to_redis():
    """
    RUNS EVERY 6 HOURS:
    Looks ahead 7 hours into Neon Postgres, finds upcoming active reminders,
    and caches them into the Redis Sorted Set.
    """
    now = datetime.now(timezone.utc)
    lookahead_limit = now + timedelta(hours=7)
    logger.info(f"🔄 Syncing Postgres reminders between {now} and {lookahead_limit} to Redis...")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Task).where(
                and_(
                    Task.reminder_at >= now,
                    Task.reminder_at <= lookahead_limit,
                    Task.status == TaskStatus.todo,
                    Task.reminder_at != None
                )
            )
        )
        upcoming_tasks = result.scalars().all()

        if not upcoming_tasks:
            logger.info("No upcoming reminders found to sync.")
            return

        r = await get_redis()
        pipeline = r.pipeline()

        for task in upcoming_tasks:
            task_payload = json.dumps({
                "id": str(task.id),
                "user_id": str(task.user_id),
                "title": task.title,
                "description": task.description or ""
            })
            score = int(task.reminder_at.timestamp())
            pipeline.zadd(REMINDERS_ZSET_KEY, {task_payload: score})

        await pipeline.execute()
        logger.info(f"🚀 Successfully synchronized {len(upcoming_tasks)} tasks to Redis.")


async def send_daily_briefing():
    from zoneinfo import ZoneInfo
    logger.info("Running daily briefing check")

    async with AsyncSessionLocal() as db:
        # 1. Removed the strict requirement for daily_briefing_time to not be null
        result = await db.execute(
            select(UserPreferences).where(
                UserPreferences.telegram_chat_id.isnot(None)
            )
        )
        all_prefs = result.scalars().all()

        for prefs in all_prefs:
            try:
                tz = ZoneInfo(prefs.timezone or "Africa/Nairobi")
                now_local = datetime.now(tz)
                current_minutes = now_local.hour * 60 + now_local.minute
                
                # parse briefing time
                pref_time = prefs.daily_briefing_time or "09:00"
                # Use pref_time here, NOT prefs.daily_briefing_time
                briefing_parts = pref_time.split(":") 
                briefing_minutes = int(briefing_parts[0]) * 60 + int(briefing_parts[1])
                
                # allow a 59-minute window so we never miss it
                diff = abs(current_minutes - briefing_minutes)
                within_window = diff <= 59
                
                if not within_window:
                    logger.debug(
                        f"Not briefing time for {prefs.user_id} — "
                        f"briefing at {prefs.daily_briefing_time}, "
                        f"now {now_local.strftime('%H:%M')}"
                    )
                    continue
                    
                # skip if already sent today
                if prefs.last_briefing_sent_at:
                    last_sent_local = prefs.last_briefing_sent_at.astimezone(tz)
                    if last_sent_local.date() == now_local.date():
                        logger.info(
                            f"Briefing already sent today for {prefs.user_id}"
                        )
                        continue
                        
                logger.info(
                    f"Sending briefing to {prefs.telegram_chat_id} "
                    f"at {now_local.strftime('%H:%M')} {prefs.timezone}"
                )
                await send_briefing_to_user(db, prefs)
            except Exception as e:
                logger.exception(
                    f"Failed briefing check for user {prefs.user_id}: {e}"
                )


async def send_briefing_to_user(db, prefs: UserPreferences):
    # Rate-limiting check: skip if already sent within the last 20 hours
    if prefs.last_briefing_sent_at:
        now_utc = datetime.now(timezone.utc)
        hours_since = (now_utc - prefs.last_briefing_sent_at).total_seconds() / 3600
        if hours_since < 20:
            logger.info(f"Briefing already sent {hours_since:.1f}h ago — skipping")
            return

    from hub.api.telegram_utils import send_telegram_message

    # Handle timezone setups cleanly inside the function
    user_tz = zoneinfo.ZoneInfo(prefs.timezone or "Africa/Nairobi")
    now_local = datetime.now(user_tz)
    now_utc = now_local.astimezone(timezone.utc)

    # Calculate timezone-aware boundaries for "Today" and convert them to UTC for the DB
    today_start_local = datetime(now_local.year, now_local.month, now_local.day, 0, 0, 0, tzinfo=user_tz)
    today_end_local = datetime(now_local.year, now_local.month, now_local.day, 23, 59, 59, tzinfo=user_tz)
    today_end_utc = today_end_local.astimezone(timezone.utc)

    # get overdue tasks (due before right now)
    overdue_result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == prefs.user_id,
                Task.due_at < now_utc,
                Task.status.in_([TaskStatus.todo, TaskStatus.in_progress])
            )
        ).order_by(Task.priority)
    )
    overdue = overdue_result.scalars().all()

    # get tasks due today (between right now and 11:59PM local time)
    today_result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == prefs.user_id,
                Task.due_at >= now_utc,
                Task.due_at <= today_end_utc,
                Task.status.in_([TaskStatus.todo, TaskStatus.in_progress])
            )
        ).order_by(Task.priority)
    )
    due_today = today_result.scalars().all()

    # get in-progress tasks
    wip_result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == prefs.user_id,
                Task.status == TaskStatus.in_progress
            )
        ).limit(5)
    )
    in_progress = wip_result.scalars().all()

    # get recent learning
    week_ago_utc = now_utc - timedelta(days=7)
    learning_result = await db.execute(
        select(MemoryContext).where(
            and_(
                MemoryContext.user_id == prefs.user_id,
                MemoryContext.memory_type == MemoryType.learning,
                MemoryContext.created_at >= week_ago_utc
            )
        )
    )
    recent_learning = learning_result.scalars().all()

    # build the briefing message using their Local Time
    lines = [f"☀️ *Good morning! Here's your NEXUS briefing for {now_local.strftime('%A, %B %d')}*\n"]

    if overdue:
        lines.append(f"🔴 *Overdue ({len(overdue)})*")
        for t in overdue[:3]:
            lines.append(f"  • {t.title}")
        if len(overdue) > 3:
            lines.append(f"  ...and {len(overdue) - 3} more")
        lines.append("")

    if due_today:
        lines.append(f"📅 *Due Today ({len(due_today)})*")
        for t in due_today[:3]:
            lines.append(f"  • {t.title}")
        lines.append("")

    if in_progress:
        lines.append(f"⚡ *In Progress ({len(in_progress)})*")
        for t in in_progress[:3]:
            lines.append(f"  • {t.title}")
        lines.append("")

    if recent_learning:
        lines.append(
            f"📚 *Learning this week:* {len(recent_learning)} concepts stored"
        )
        lines.append("")

    if not overdue and not due_today and not in_progress:
        lines.append("✅ No urgent tasks — your slate is clear!")
        lines.append("")

    lines.append("_Reply to ask me anything._")

    message = "\n".join(lines)
    await send_telegram_message(
        chat_id=prefs.telegram_chat_id,
        text=message
    )
    logger.info(f"Sent daily briefing to chat {prefs.telegram_chat_id}")

    # Track execution timestamp and save state
    prefs.last_briefing_sent_at = datetime.now(timezone.utc)
    await db.commit()


async def check_project_health():
    logger.info("Running project health check")

    async with AsyncSessionLocal() as db:
        now = datetime.now(timezone.utc)

        result = await db.execute(
            select(UserPreferences).where(
                UserPreferences.telegram_chat_id != None
            )
        )
        all_prefs = result.scalars().all()

        for prefs in all_prefs:
            overdue_result = await db.execute(
                select(Task).where(
                    and_(
                        Task.user_id == prefs.user_id,
                        Task.due_at < now,
                        Task.status.in_([TaskStatus.todo, TaskStatus.in_progress]),
                        Task.due_at >= now - timedelta(hours=6),
                    )
                )
            )
            newly_overdue = overdue_result.scalars().all()

            if newly_overdue:
                from hub.api.telegram_utils import send_telegram_message
                task_list = "\n".join([f"  • {t.title}" for t in newly_overdue])
                await send_telegram_message(
                    chat_id=prefs.telegram_chat_id,
                    text=f"⚠️ *Tasks just went overdue:*\n{task_list}",
                )