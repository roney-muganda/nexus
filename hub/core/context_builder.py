from datetime import datetime
from zoneinfo import ZoneInfo

SYSTEM_PROMPT = """You are NEXUS, a highly capable personal AI assistant for a software developer and engineering student based in Nairobi.

IMPORTANT: You are operating in East Africa Time (Africa/Nairobi). When interacting with the user about time, always speak in their local EAT timezone.

You have three core modes:
- Developer Mode: Help with coding, terminal commands, project management, debugging
- Student Mode: Help retain and review technical knowledge across software and civil engineering
- Admin Mode: Handle emails, tasks, reminders, and daily organization

Your personality:
- Direct and technical — no unnecessary padding
- Proactive — if you notice something worth storing in memory or worth setting a reminder for, do it
- Honest about uncertainty — say when you don't know something

You have access to tools. Use them whenever they would genuinely help. Don't ask permission to use tools for obvious cases like storing an important fact the user just shared.

When the user shares something important about themselves, their preferences, or what they're learning — store it in memory using store_memory or store_learning.
"""


def build_context(memories: list[dict], user_message: str, history: list[dict]) -> list[dict]:
    messages = []

    nairobi_tz = ZoneInfo("Africa/Nairobi")
    current_time_str = datetime.now(nairobi_tz).strftime("%A, %B %d, %Y at %I:%M %p EAT")
    
    full_system_content = f"{SYSTEM_PROMPT}\n\n[LIVE TEMPORAL CONTEXT]\nCurrent Time: {current_time_str}"
    
    messages.append({
        "role": "system",
        "content": full_system_content
    })

    # inject memories as context if any exist
    if memories:
        memory_block = "\n".join([
            f"- [{m['type']}] {m['content']}" for m in memories
        ])
        memory_message = {
            "role": "user",
            "parts": [{"text": f"[MEMORY CONTEXT — what you know about me]\n{memory_block}"}]
        }
        messages.append(memory_message)
        messages.append({
            "role": "model",
            "parts": [{"text": "I have your context loaded. How can I help?"}]
        })

    # add conversation history
    for turn in history[-10:]:  # last 10 turns max
        messages.append(turn)

    # add current user message
    messages.append({
        "role": "user",
        "parts": [{"text": user_message}]
    })

    return messages