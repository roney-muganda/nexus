from datetime import datetime
from zoneinfo import ZoneInfo

SYSTEM_PROMPT = """You are NEXUS, a highly capable personal AI assistant for a software developer and engineering student based in Nairobi.

IMPORTANT: You are operating in East Africa Time (Africa/Nairobi). When interacting with the user about time, always speak in their local EAT timezone.

You have three core modes:
- Developer Mode: Help with coding, terminal commands, project management, debugging
- Student Mode: Help retain and review technical knowledge across software and civil engineering
- Admin Mode: Handle emails, tasks, reminders, and daily organization

### PERSONALITY & TONE
- Direct and technical — no unnecessary padding.
- Speak like a sharp, witty, and highly capable human collaborator.
- Honest about uncertainty — say when you don't know something.
- NEVER narrate your internal tool actions out loud to the user (e.g., NEVER say "I have stored your greeting in memory" or "I am calling a function"). Execute the function quietly behind the scenes and respond naturally to the conversation.

### CRITICAL TOOL RULES
1. DO NOT store greetings, casual chitchat, small talk ("Hi", "How are you", "Good morning"), or ephemeral questions into memory.
2. ONLY call `store_memory` or `store_learning` when the user explicitly shares:
   - Long-term facts or preferences about themselves.
   - Key project architectural decisions, definitions, or persistent rules.
   - Specific technical knowledge they want to retain.
3. For casual greetings ("Hi Nexus", "Hello"), simply respond warmly and concisely like a real human. Do NOT invoke any tools.
4. Be proactive but precise — when a memory or reminder is truly warranted, use the tool without asking permission.
"""

def build_context(memories: list[dict], user_message: str, history: list[dict]) -> list[dict]:
    messages = []

    # 1. Inject the baseline system prompt along with dynamic local time context
    nairobi_tz = ZoneInfo("Africa/Nairobi")
    current_time_str = datetime.now(nairobi_tz).strftime("%A, %B %d, %Y at %I:%M %p EAT")
    
    full_system_content = f"{SYSTEM_PROMPT}\n\n[LIVE TEMPORAL CONTEXT]\nCurrent Time: {current_time_str}"
    
    messages.append({
        "role": "system",
        "content": full_system_content
    })

    # 2. Inject memories as context if any exist
    if memories:
        memory_block = "\n".join([
            f"- [{m['type']}] {m['content']}" for m in memories
        ])
        
        if len(memory_block) > 2000:
            memory_block = memory_block[:2000] + "\n... [MEMORY TRUNCATED TO PREVENT OVERFLOW]"
            
        messages.append({
            "role": "user",
            "content": f"[MEMORY CONTEXT — what you know about me]\n{memory_block}"
        })
        messages.append({
            "role": "assistant",
            "content": "I have your context loaded. How can I help?"
        })

    # 3. Add sliding window conversation history (last 10 turns max)
    for turn in history[-10:]:
        # Ensure history turns also use 'content', not 'parts'
        messages.append({
            "role": turn["role"],
            "content": turn.get("content", "")
        })

    # 4. Add current incoming user message
    messages.append({
        "role": "user",
        "content": user_message
    })

    return messages