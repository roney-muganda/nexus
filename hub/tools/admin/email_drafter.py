import logging
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from hub.tools.admin.gmail_auth import get_gmail_service
from groq import Groq
from hub.config import settings

logger = logging.getLogger(__name__)


async def draft_email_reply(
    thread_id: str = None,
    to: str = None,
    subject: str = None,
    intent: str = "",
    context: str = "",
    send_immediately: bool = False,
) -> dict:
    client = Groq(api_key=settings.groq_api_key)

    original_context = ""
    if thread_id:
        try:
            service = get_gmail_service()
            thread = service.users().threads().get(
                userId="me", id=thread_id
            ).execute()
            messages = thread.get("messages", [])
            if messages:
                last = messages[-1]
                headers = {
                    h["name"]: h["value"]
                    for h in last["payload"]["headers"]
                }
                snippet = last.get("snippet", "")
                original_context = (
                    f"Replying to email from {headers.get('From', 'unknown')}\n"
                    f"Subject: {headers.get('Subject', '')}\n"
                    f"Content: {snippet}"
                )
                if not to:
                    to = headers.get("Reply-To") or headers.get("From", "")
                if not subject:
                    orig_subject = headers.get("Subject", "")
                    subject = f"Re: {orig_subject}" if not orig_subject.startswith("Re:") else orig_subject
        except Exception as e:
            logger.warning(f"Could not fetch thread {thread_id}: {e}")

    prompt = f"""Write a professional email reply.

{f'Original email context: {original_context}' if original_context else ''}
{f'Additional context: {context}' if context else ''}

Intent/what to say: {intent}

Write only the email body — no subject line, no metadata.
Keep it professional, concise, and natural."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
        temperature=0.7,
    )

    draft_body = response.choices[0].message.content.strip()

    if send_immediately and to:
        try:
            service = get_gmail_service()
            message = MIMEMultipart()
            message["to"] = to
            message["subject"] = subject or "Re: your message"
            message.attach(MIMEText(draft_body, "plain"))

            raw = base64.urlsafe_b64encode(
                message.as_bytes()
            ).decode("utf-8")

            send_body = {"raw": raw}
            if thread_id:
                send_body["threadId"] = thread_id

            service.users().messages().send(
                userId="me", body=send_body
            ).execute()

            return {
                "status": "sent",
                "to": to,
                "subject": subject,
                "body": draft_body,
            }
        except Exception as e:
            logger.exception(f"Failed to send email: {e}")
            return {
                "status": "draft_only",
                "reason": str(e),
                "body": draft_body,
            }

    return {
        "status": "drafted",
        "to": to or "unknown",
        "subject": subject or "",
        "body": draft_body,
        "note": "Review and send manually or call again with send_immediately=true"
    }


async def create_task_from_email(
    email_id: str,
    user_id: str,
    db,
) -> dict:
    try:
        service = get_gmail_service()
        msg = service.users().messages().get(
            userId="me", id=email_id, format="full"
        ).execute()

        headers = {
            h["name"]: h["value"]
            for h in msg["payload"]["headers"]
        }
        snippet = msg.get("snippet", "")
        subject = headers.get("Subject", "(no subject)")
        sender = headers.get("From", "unknown")

        client = Groq(api_key=settings.groq_api_key)
        prompt = f"""Extract action items from this email.

From: {sender}
Subject: {subject}
Content: {snippet}

Return a JSON array of action items, each with:
- title: short task title
- priority: 1-5 (1=urgent)
- due_hint: date hint if mentioned (or null)

Return only valid JSON, no explanation."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.1,
        )

        import json
        import uuid
        from hub.models.task import Task, TaskStatus

        raw = response.choices[0].message.content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        action_items = json.loads(raw)

        created_tasks = []
        for item in action_items:
            task = Task(
                user_id=uuid.UUID(user_id),
                title=item["title"],
                priority=item.get("priority", 2),
                status=TaskStatus.todo,
                description=f"From email: {subject} (from {sender})",
                source_device="gmail",
            )
            db.add(task)
            await db.flush()
            created_tasks.append({
                "id": str(task.id),
                "title": task.title,
                "priority": task.priority,
            })

        await db.flush()
        return {
            "status": "created",
            "email_subject": subject,
            "tasks_created": len(created_tasks),
            "tasks": created_tasks,
        }

    except Exception as e:
        logger.exception(f"Failed to create tasks from email {email_id}: {e}")
        return {"status": "error", "message": str(e)}