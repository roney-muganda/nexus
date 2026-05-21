import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from groq import Groq
from hub.config import settings
from hub.models.memory_context import MemoryContext, MemoryType
from hub.memory.chroma_client import get_or_create_collection, MEMORY_COLLECTION
from hub.memory.embedder import embed_text

logger = logging.getLogger(__name__)


async def generate_review_quiz(
    db: AsyncSession,
    user_id: str,
    domain: str = None,
    num_questions: int = 5,
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=3)

    conditions = [
        MemoryContext.user_id == user_id,
        MemoryContext.memory_type == MemoryType.learning,
        (MemoryContext.last_accessed_at == None) |
        (MemoryContext.last_accessed_at < cutoff),
    ]

    if domain:
        from sqlalchemy import func, text
        conditions.append(
            text("lower(:domain) = ANY(SELECT lower(unnest(tags)))")
            .bindparams(domain=domain)
    )

    query = select(MemoryContext).where(
        and_(*conditions)
    ).order_by(
        MemoryContext.last_accessed_at.asc().nullsfirst()
    ).limit(num_questions)

    result = await db.execute(query)
    memories = result.scalars().all()

    if not memories:
        return {
            "status": "no_content",
            "message": f"No learning notes found{' for ' + domain if domain else ''}. "
                       f"Start storing things you learn using store_learning."
        }

    concepts = [m.content for m in memories]

    client = Groq(api_key=settings.groq_api_key)
    concepts_text = "\n".join([f"{i+1}. {c}" for i, c in enumerate(concepts)])
    prompt = f"""You are a study assistant helping someone review what they have learned.
Based on these learning notes, generate {num_questions} quiz questions.
For each question provide: the question, the correct answer, and a brief explanation.

Learning notes:
{concepts_text}

Format your response as a numbered list like this:
Q1: [question]
A1: [answer]
E1: [explanation]

Q2: [question]
...and so on."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=2000,
        temperature=0.7,
    )

    quiz_text = response.choices[0].message.content

    now = datetime.now(timezone.utc)
    for memory in memories:
        memory.last_accessed_at = now
        memory.access_count = (memory.access_count or 0) + 1
    await db.flush()

    return {
        "status": "ready",
        "domain": domain or "all",
        "num_questions": len(memories),
        "quiz": quiz_text,
        "concepts_reviewed": [c[:80] + "..." if len(c) > 80 else c for c in concepts],
    }

async def get_learning_summary(
    db: AsyncSession,
    user_id: str,
    domain: str = None,
    days: int = 7,
) -> dict:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    query = select(MemoryContext).where(
        and_(
            MemoryContext.user_id == user_id,
            MemoryContext.memory_type == MemoryType.learning,
            MemoryContext.created_at >= cutoff,
        )
    ).order_by(MemoryContext.created_at.desc())

    result = await db.execute(query)
    memories = result.scalars().all()

    if domain:
        memories = [
            m for m in memories
            if domain.lower() in [t.lower() for t in (m.tags or [])]
        ]

    # group by domain tag
    by_domain = {}
    for m in memories:
        tags = m.tags or []
        domain_tags = [t for t in tags if t != "learning"]
        key = domain_tags[0] if domain_tags else "general"
        if key not in by_domain:
            by_domain[key] = []
        by_domain[key].append(m.content[:100])

    return {
        "period_days": days,
        "total_concepts": len(memories),
        "by_domain": by_domain,
        "message": f"You've stored {len(memories)} learning notes in the last {days} days."
    }