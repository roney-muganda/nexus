import base64
import logging
from email import message_from_bytes
from hub.tools.admin.gmail_auth import get_gmail_service
from groq import Groq
from hub.config import settings

logger = logging.getLogger(__name__)


def decode_email_body(payload: dict) -> str:
    body = ""
    if "parts" in payload:
        for part in payload["parts"]:
            if part["mimeType"] == "text/plain":
                data = part["body"].get("data", "")
                if data:
                    body += base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    elif "body" in payload:
        data = payload["body"].get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
    return body.strip()


async def read_and_summarize_emails(
    user_id: str,
    max_results: int = 10,
    query: str = "is:unread",
    summarize: bool = True,
) -> dict:
    try:
        service = get_gmail_service()

        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results
        ).execute()

        messages = result.get("messages", [])
        if not messages:
            return {
                "status": "empty",
                "message": "No emails found matching the query.",
                "emails": []
            }

        emails = []
        for msg in messages:
            msg_data = service.users().messages().get(
                userId="me",
                id=msg["id"],
                format="full"
            ).execute()

            headers = {
                h["name"]: h["value"]
                for h in msg_data["payload"]["headers"]
            }
            body = decode_email_body(msg_data["payload"])

            emails.append({
                "id": msg["id"],
                "thread_id": msg_data["threadId"],
                "subject": headers.get("Subject", "(no subject)"),
                "sender": headers.get("From", "unknown"),
                "date": headers.get("Date", ""),
                "snippet": msg_data.get("snippet", ""),
                # TRUNCATION FIX: Severely limit the body size just in case it is requested
                "body": body[:300] + ("..." if len(body) > 300 else ""),
                "labels": msg_data.get("labelIds", []),
            })

        if not summarize:
            return {
                "status": "success",
                "count": len(emails),
                "emails": emails
            }

        # use LLM to create priority-ranked summary
        client = Groq(api_key=settings.groq_api_key)
        email_text = "\n\n".join([
            f"FROM: {e['sender']}\nSUBJECT: {e['subject']}\nDATE: {e['date']}\nSNIPPET: {e['snippet']}"
            for e in emails
        ])

        prompt = f"""Summarize these emails for a software developer.
For each email identify:
- Priority (HIGH/MEDIUM/LOW)
- Required action (if any)
- One-line summary

Emails:
{email_text}

Format as a ranked list starting with highest priority."""

        response = client.chat.completions.create(
            # MODEL FIX: Swapped to the active, rate-limit friendly 8B model
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.3,
        )

        summary = response.choices[0].message.content

        return {
            "status": "success",
            "count": len(emails),
            "summary": summary,
            "emails": [
                {
                    "id": e["id"],
                    "subject": e["subject"],
                    "sender": e["sender"],
                    "date": e["date"],
                }
                for e in emails
            ]
        }

    except Exception as e:
        logger.exception(f"Gmail read failed: {e}")
        return {"status": "error", "message": str(e)}