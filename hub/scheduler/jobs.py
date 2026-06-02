import logging
import zoneinfo
from datetime import datetime, timezone, timedelta
from sqlalchemy import select, and_
from hub.models.database import AsyncSessionLocal
from hub.models.task import Task, TaskStatus
from hub.models.user import User
from hub.models.user_preferences import UserPreferences
from hub.models.memory_context import MemoryContext, MemoryType

logger = logging.getLogger(__name__)


async def fire_due_reminders():
    now = datetime.now(timezone.utc)
    logger.info(f"Checking for due reminders at {now}")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Task).where(
                and_(
                    Task.reminder_at <= now,
                    Task.status == TaskStatus.todo,
                    Task.reminder_at != None,
                )
            )
        )
        due_tasks = result.scalars().all()

        if not due_tasks:
            return

        logger.info(f"Found {len(due_tasks)} due reminders")

        for task in due_tasks:
            try:
                # get user preferences for notification channel
                prefs_result = await db.execute(
                    select(UserPreferences).where(
                        UserPreferences.user_id == task.user_id
                    )
                )
                prefs = prefs_result.scalar_one_or_none()

                if prefs and prefs.telegram_chat_id:
                    from hub.api.telegram_utils import send_reminder_notification
                    await send_reminder_notification(
                        chat_id=prefs.telegram_chat_id,
                        title=task.title,
                        notes=task.description
                    )
                    logger.info(f"Sent reminder for task: {task.title}")

                # clear reminder_at so it doesn't fire again
                task.reminder_at = None
                await db.flush()

            except Exception as e:
                logger.exception(f"Failed to send reminder for task {task.id}: {e}")

        await db.commit()


async def send_daily_briefing():
    from zoneinfo import ZoneInfo

    logger.info("Running daily briefing check")

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(UserPreferences).where(
                UserPreferences.telegram_chat_id != None,
                UserPreferences.daily_briefing_time != None,
            )
        )
        all_prefs = result.scalars().all()

        for prefs in all_prefs:
            try:
                # get current time in user's timezone
                tz = ZoneInfo(prefs.timezone or "UTC")
                now_local = datetime.now(tz)
                current_time_str = now_local.strftime("%H:%M")

                # only send if current hour matches briefing time
                # compare just the hour to avoid minute precision issues
                briefing_hour = prefs.daily_briefing_time[:2]
                current_hour = current_time_str[:2]

                if briefing_hour == current_hour:
                    logger.info(
                        f"Sending briefing to {prefs.telegram_chat_id} "
                        f"at {current_time_str} ({prefs.timezone})"
                    )
                    # Fixed: Clean function signature matched here
                    await send_briefing_to_user(db, prefs, now_local, tz)
                else:
                    logger.debug(
                        f"Skipping briefing for {prefs.telegram_chat_id} — "
                        f"briefing at {prefs.daily_briefing_time}, "
                        f"now {current_time_str}"
                    )
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
    user_tz = zoneinfo.ZoneInfo(prefs.timezone or "UTC")
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
    await db.flush()


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