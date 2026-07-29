import json
import logging
import uuid
from datetime import datetime, timezone, timedelta, date
from zoneinfo import ZoneInfo
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from groq import Groq
from hub.config import settings
from hub.models.task import Task, TaskStatus
from hub.models.memory_context import MemoryContext, MemoryType
from hub.models.user_preferences import UserPreferences
from hub.models.daily_plan import DailyPlan

logger = logging.getLogger(__name__)


async def generate_daily_plan(
    db: AsyncSession,
    user_id: str,
    energy_level: str = "normal",
    focus_preference: str = None,
    custom_instructions: str = None,
) -> dict:
    tz = ZoneInfo("Africa/Nairobi")
    now_local = datetime.now(tz)
    today = now_local.date()
    
    # Cast user_id to UUID safely for asyncpg
    user_uuid = uuid.UUID(user_id)

    # check if plan already exists for today
    existing = await db.execute(
        select(DailyPlan).where(
            and_(
                DailyPlan.user_id == user_uuid,
                DailyPlan.plan_date == today,
            )
        )
    )
    existing_plan = existing.scalar_one_or_none()
    if existing_plan and not custom_instructions:
        return {
            "status": "existing",
            "plan": existing_plan.plan_text,
            "focus_theme": existing_plan.focus_theme,
            "insights": existing_plan.insights,
            "time_blocks": existing_plan.time_blocks,
            "message": "Here's today's plan (already generated this morning)."
        }

    # gather all context
    prefs_result = await db.execute(
        select(UserPreferences).where(
            UserPreferences.user_id == user_uuid
        )
    )
    prefs = prefs_result.scalar_one_or_none()
    working_hours = prefs.working_hours if prefs and prefs.working_hours else {"start": "08:00", "end": "18:00"}

    # overdue tasks
    overdue_result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_uuid,
                Task.due_at < datetime.now(timezone.utc),
                Task.status.in_([TaskStatus.todo, TaskStatus.in_progress])
            )
        ).order_by(Task.priority)
    )
    overdue_tasks = overdue_result.scalars().all()

    # due today
    today_end = datetime.now(timezone.utc).replace(
        hour=23, minute=59, second=59
    )
    today_result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_uuid,
                Task.due_at >= datetime.now(timezone.utc),
                Task.due_at <= today_end,
                Task.status.in_([TaskStatus.todo, TaskStatus.in_progress])
            )
        ).order_by(Task.priority)
    )
    due_today = today_result.scalars().all()

    # in progress tasks
    wip_result = await db.execute(
        select(Task).where(
            and_(
                Task.user_id == user_uuid,
                Task.status == TaskStatus.in_progress
            )
        ).limit(5)
    )
    in_progress = wip_result.scalars().all()

    # recent learning — what was studied in last 7 days
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    learning_result = await db.execute(
        select(MemoryContext).where(
            and_(
                MemoryContext.user_id == user_uuid,
                MemoryContext.memory_type == MemoryType.learning,
                MemoryContext.created_at >= week_ago,
            )
        ).order_by(MemoryContext.created_at.desc()).limit(10)
    )
    recent_learning = learning_result.scalars().all()

    # overdue learning — concepts not reviewed in 5+ days
    five_days_ago = datetime.now(timezone.utc) - timedelta(days=5)
    stale_result = await db.execute(
        select(MemoryContext).where(
            and_(
                MemoryContext.user_id == user_uuid,
                MemoryContext.memory_type == MemoryType.learning,
                (MemoryContext.last_accessed_at == None) |
                (MemoryContext.last_accessed_at < five_days_ago),
            )
        ).order_by(MemoryContext.importance.desc()).limit(5)
    )
    stale_concepts = stale_result.scalars().all()

    # user preferences and facts from memory
    prefs_memory_result = await db.execute(
        select(MemoryContext).where(
            and_(
                MemoryContext.user_id == user_uuid,
                MemoryContext.memory_type.in_([
                    MemoryType.preference,
                    MemoryType.fact,
                ])
            )
        ).order_by(MemoryContext.importance.desc()).limit(10)
    )
    user_facts = prefs_memory_result.scalars().all()

    # build context for LLM
    context_parts = []

    context_parts.append(
        f"Today is {now_local.strftime('%A, %B %d %Y')} — {now_local.strftime('%H:%M')} EAT"
    )
    context_parts.append(
        f"Working hours: {working_hours.get('start')} - {working_hours.get('end')} EAT"
    )
    context_parts.append(f"Energy level: {energy_level}")

    if focus_preference:
        context_parts.append(f"User wants to focus on: {focus_preference}")

    if overdue_tasks:
        context_parts.append(
            f"\nOVERDUE TASKS ({len(overdue_tasks)}):\n" +
            "\n".join([
                f"  - {t.title} (priority {t.priority})"
                for t in overdue_tasks
            ])
        )

    if due_today:
        context_parts.append(
            f"\nDUE TODAY ({len(due_today)}):\n" +
            "\n".join([
                f"  - {t.title} (priority {t.priority})"
                for t in due_today
            ])
        )

    if in_progress:
        context_parts.append(
            f"\nCURRENTLY IN PROGRESS:\n" +
            "\n".join([f"  - {t.title}" for t in in_progress])
        )

    if recent_learning:
        by_domain = {}
        for m in recent_learning:
            tags = m.tags or []
            domain = next(
                (t for t in tags if t != "learning"), "general"
            )
            if domain not in by_domain:
                by_domain[domain] = []
            by_domain[domain].append(m.content[:80])

        context_parts.append("\nRECENT LEARNING:")
        for domain, concepts in by_domain.items():
            context_parts.append(f"  {domain}:")
            for c in concepts[:3]:
                context_parts.append(f"    - {c}")

    if stale_concepts:
        context_parts.append(
            f"\nCONCEPTS NOT REVIEWED IN 5+ DAYS (need attention):\n" +
            "\n".join([
                f"  - {m.content[:80]}"
                for m in stale_concepts
            ])
        )

    if user_facts:
        context_parts.append(
            f"\nUSER CONTEXT:\n" +
            "\n".join([
                f"  - {m.content[:80]}"
                for m in user_facts
            ])
        )

    if custom_instructions:
        context_parts.append(f"\nUSER INSTRUCTIONS: {custom_instructions}")

    context = "\n".join(context_parts)

    # generate plan with LLM
    client = Groq(api_key=settings.groq_api_key)

    prompt = f"""You are NEXUS, an intelligent personal assistant for Roney — a software developer and civil engineering student based in Nairobi.

Generate a detailed, intelligent daily plan based on this context:

{context}

Create a structured day plan with:
1. A single focus theme for the day (one sentence)
2. Morning block, afternoon block, evening block — each with specific time-boxed activities
3. At least one civil engineering study session if there are stale concepts to review
4. Developer work blocks aligned with in-progress and due tasks
5. 2-3 sharp insights based on the data (e.g. overdue items, learning gaps, patterns you notice)
6. A motivational but grounded closing note

Rules:
- Be specific with times (e.g. 8:00am not "morning")
- Keep each activity to 30-120 minute blocks — no marathon sessions
- Build in 15-minute breaks between blocks
- Put hardest cognitive work in the morning (highest energy)
- Civil engineering study works well in early afternoon (1-3pm)
- Leave evenings lighter — review, reading, reflection
- If energy is low, suggest shorter blocks and more breaks
- If there are overdue tasks, address the most critical one first

Format your response exactly like this:

FOCUS: [one sentence theme]

MORNING (8:00am - 12:00pm)
⏰ 8:00am - 9:30am — [activity]
⏰ 9:45am - 11:00am — [activity]
⏰ 11:00am - 11:15am — Break
⏰ 11:15am - 12:00pm — [activity]

AFTERNOON (1:00pm - 5:00pm)
⏰ 1:00pm - 2:30pm — [activity]
...

EVENING (6:00pm - 8:00pm)
⏰ 6:00pm - 7:00pm — [activity]
...

INSIGHTS
💡 [insight 1]
💡 [insight 2]
💡 [insight 3]

CLOSING NOTE
[one paragraph]"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=1500,
        temperature=0.6,
    )

    plan_text = response.choices[0].message.content.strip()

    # extract focus theme
    focus_theme = ""
    insights = ""
    for line in plan_text.split("\n"):
        if line.startswith("FOCUS:"):
            focus_theme = line.replace("FOCUS:", "").strip()
        if line.startswith("💡"):
            insights += line + "\n"

    # save to database
    if existing_plan:
        existing_plan.plan_text = plan_text
        existing_plan.focus_theme = focus_theme
        existing_plan.insights = insights
        await db.flush()
        plan_id = str(existing_plan.id)
    else:
        new_plan = DailyPlan(
            user_id=user_uuid,
            plan_date=today,
            plan_text=plan_text,
            focus_theme=focus_theme,
            insights=insights,
        )
        db.add(new_plan)
        await db.flush()
        plan_id = str(new_plan.id)

    await db.commit()

    return {
        "status": "generated",
        "plan_id": plan_id,
        "plan": plan_text,
        "focus_theme": focus_theme,
        "insights": insights,
        "date": today.isoformat(),
    }


async def get_todays_plan(db: AsyncSession, user_id: str) -> dict:
    tz = ZoneInfo("Africa/Nairobi")
    today = datetime.now(tz).date()
    user_uuid = uuid.UUID(user_id)

    result = await db.execute(
        select(DailyPlan).where(
            and_(
                DailyPlan.user_id == user_uuid,
                DailyPlan.plan_date == today,
            )
        )
    )
    plan = result.scalar_one_or_none()

    if not plan:
        return {
            "status": "none",
            "message": "No plan for today yet. Ask me to plan your day."
        }

    return {
        "status": "found",
        "plan": plan.plan_text,
        "focus_theme": plan.focus_theme,
        "insights": plan.insights,
        "date": plan.plan_date.isoformat(),
    }