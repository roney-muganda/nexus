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
    logger.info("Running daily briefing job")
    now_utc = datetime.now(timezone.utc)

    async with AsyncSessionLocal() as db:
        # get all users with telegram linked and briefing time set
        result = await db.execute(
            select(UserPreferences).where(
                UserPreferences.telegram_chat_id != None,
                UserPreferences.daily_briefing_time != None,
            )
        )
        all_prefs = result.scalars().all()

        for prefs in all_prefs:
            try:
                # 1. Resolve User's Local Timezone
                tz_str = prefs.timezone or "UTC"
                try:
                    user_tz = zoneinfo.ZoneInfo(tz_str)
                except Exception:
                    user_tz = timezone.utc
                
                now_local = now_utc.astimezone(user_tz)

                # 2. Check if the current local hour matches their preferred briefing time
                # daily_briefing_time is guaranteed to be "HH:MM" due to Pydantic validation
                briefing_hour = int(prefs.daily_briefing_time.split(":")[0])
                
                if now_local.hour == briefing_hour:
                    await send_briefing_to_user(db, prefs, now_local, user_tz)
                    
            except Exception as e:
                logger.exception(
                    f"Failed to process briefing queue for user {prefs.user_id}: {e}"
                )


async def send_briefing_to_user(db, prefs: UserPreferences, now_local: datetime, user_tz: zoneinfo.ZoneInfo):
    from hub.api.telegram_utils import send_telegram_message

    now_utc = now_local.astimezone(timezone.utc)

    # 3. Calculate timezone-aware boundaries for "Today" and convert them back to UTC for the DB
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
            # 4. Narrow the window to exactly 6 hours to prevent duplicate alerts
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