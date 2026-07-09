import json
import uuid
import time
import logging
from groq import Groq
import groq
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from hub.config import settings
from hub.core.context_builder import build_context, SYSTEM_PROMPT
from hub.core.tool_schemas import TOOL_SCHEMAS
from hub.core.tool_dispatcher import ToolDispatcher
from hub.models.conversation_turn import ConversationTurn, TurnRole
from hub.memory.manager import MemoryManager
from hub.models.memory_context import MemoryType

logger = logging.getLogger(__name__)


class Orchestrator:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id
        self.dispatcher = ToolDispatcher(db, user_id)
        self.client = Groq(api_key=settings.groq_api_key)

    def _build_tools(self) -> list:
        tools = []
        for schema in TOOL_SCHEMAS:
            tools.append({
                "type": "function",
                "function": {
                    "name": schema["name"],
                    "description": schema["description"],
                    "parameters": schema["parameters"]
                }
            })
        return tools

    def _route_task(self, prompt: str) -> str:
        """Dynamically selects the best model based on the task complexity."""
        prompt_lower = prompt.lower()
        
        # Heavy Lifting: Code, engineering, memory storage, quizzes, and complex tool usage
        heavy_keywords = [
            "code", "debug", "django", "python", "structural", "autocad", 
            "calculate", "architect", "quiz", "remember", "store", "memory", 
            "project", "learn", "study", "email"
        ]
        if any(kw in prompt_lower for kw in heavy_keywords):
            return "llama-3.3-70b-versatile"
            
        # Default/Admin: Fast, cheap, everyday conversational tasks
        return "llama-3.1-8b-instant"

    async def clear_session(self, session_id: str) -> None:
        """Deletes all conversation history for a given session to start fresh."""
        try:
            stmt = delete(ConversationTurn).where(
                ConversationTurn.session_id == uuid.UUID(session_id),
                ConversationTurn.user_id == uuid.UUID(self.user_id)
            )
            await self.db.execute(stmt)
            await self.db.commit()
            logger.info(f"Successfully cleared conversation turns for session {session_id}")
        except Exception as e:
            await self.db.rollback()
            logger.error(f"Failed to clear session history for {session_id}: {e}")
            raise e

    async def run(
        self,
        user_message: str,
        session_id: str,
        device: str = "web"
    ) -> str:
        start_time = time.time()

        history = await self._load_history(session_id)
        memory_manager = MemoryManager(db=self.db, user_id=self.user_id)
        memories = await memory_manager.retrieve(user_message, top_k=5)

        # Utilize the dynamic context builder with East Africa Time injection
        messages = build_context(memories=memories, user_message=user_message, history=history)

        await self._save_turn(session_id, TurnRole.user, user_message, device)

        tools = self._build_tools()
        tool_calls_made = 0 
        max_tool_calls = 3
        final_response = ""

        # Determine best model for this specific prompt
        primary_model = self._route_task(user_message)

        # Standardized Groq Fallback Chain
        fallback_chain = [
            primary_model,
            "llama-3.3-70b-versatile",    # Primary Heavy Intellect
            "mixtral-8x7b-32768",         # Excellent backup model available on Groq
            "llama-3.1-8b-instant"        # Fastest, lowest rate limit backup
        ]

        # De-duplicate the list while preserving order
        fallback_chain = list(dict.fromkeys(fallback_chain))

        while True:
            response = None
            last_error = None

            for model_candidate in fallback_chain:
                try:
                    response = self.client.chat.completions.create(
                        model=model_candidate,
                        messages=messages,
                        tools=tools,
                        tool_choice="auto",
                        max_tokens=1024,
                        temperature=0.7,
                    )
                    logger.info(f"Successfully executed inference cycle using: {model_candidate}")
                    break
                except (groq.RateLimitError, Exception) as e:
                    last_error = e
                    logger.warning(f"Model {model_candidate} failed or rate limited. error: {str(e)}. Falling back down the chain...")
                    continue
            
            if not response:
                logger.error(f"All models in the chain failed. Last error caught: {last_error}")
                final_response = "⚠️ All NEXUS core models are currently hit by high traffic limits. Please resend this message in a moment."
                break

            message = response.choices[0].message

            # check for tool calls
            if message.tool_calls and tool_calls_made < max_tool_calls:
                # add assistant message with tool calls to history
                messages.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })

                # execute each tool and add results
                for tc in message.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {}

                    result = await self.dispatcher.execute(tc.function.name, args)
                    tool_calls_made += 1

                    # --- LIVE DATA CIRCUIT BREAKER ---
                    safe_result = str(result)
                    if len(safe_result) > 2500:
                        safe_result = safe_result[:2500] + "\n... [SYSTEM WARNING: TOOL OUTPUT TRUNCATED TO PREVENT TOKEN OVERFLOW]"
                        logger.warning(f"Truncated massive tool output from {tc.function.name}")

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": safe_result
                    })

                continue

            # no tool calls — final response
            final_response = message.content or ""
            break

        latency_ms = int((time.time() - start_time) * 1000)
        await self._save_turn(
            session_id, TurnRole.assistant,
            final_response, device, latency_ms=latency_ms
        )
        await self.db.commit()
        return final_response

    async def _load_history(self, session_id: str) -> list[dict]:
        from hub.core.redis_client import cache_get, cache_set
        
        cache_key = f"history:{session_id}"
        cached = await cache_get(cache_key)
        if cached is not None:
            return cached

        # Cache Miss: Load from DB
        result = await self.db.execute(
            select(ConversationTurn)
            .where(
                ConversationTurn.session_id == uuid.UUID(session_id),
                ConversationTurn.user_id == uuid.UUID(self.user_id)
            )
            .order_by(ConversationTurn.created_at)
            .limit(20)
        )
        turns = result.scalars().all()
        
        # Keep only the 6 most recent turns
        recent_turns = turns[-6:] if len(turns) > 6 else turns
        
        history = []
        for turn in recent_turns:
            role = "user" if turn.role == TurnRole.user else "assistant"
            if turn.content:
                safe_content = turn.content
                
                # CIRCUIT BREAKER
                if len(safe_content) > 1500:
                    safe_content = safe_content[:1500] + "\n... [TRUNCATED TO PREVENT TOKEN OVERFLOW]"
                    
                history.append({
                    "role": role,
                    "content": safe_content
                })
                
        # Cache the history list for 2 hours (7200 seconds)
        await cache_set(cache_key, history, ttl_seconds=7200)
        return history


    async def _save_turn(
        self,
        session_id: str,
        role: TurnRole,
        content: str,
        device: str,
        latency_ms: int = None
    ):
        from hub.core.redis_client import cache_get, cache_set
        
        # 1. Save to DB asynchronously
        turn = ConversationTurn(
            session_id=uuid.UUID(session_id),
            user_id=uuid.UUID(self.user_id),
            role=role,
            content=content,
            device=device,
            latency_ms=latency_ms
        )
        self.db.add(turn)
        await self.db.flush()

        # 2. SMART CACHE UPDATE: Append to Redis instead of deleting
        cache_key = f"history:{session_id}"
        cached_history = await cache_get(cache_key)
        
        if cached_history is not None:
            role_str = "user" if role == TurnRole.user else "assistant"
            safe_content = content or ""
            
            if len(safe_content) > 1500:
                safe_content = safe_content[:1500] + "\n... [TRUNCATED TO PREVENT TOKEN OVERFLOW]"
                
            # Append new turn
            cached_history.append({
                "role": role_str,
                "content": safe_content
            })
            
            # Maintain the sliding window of 6 turns
            cached_history = cached_history[-6:]
            
            # Write back to cache, resetting the 2-hour timer
            await cache_set(cache_key, cached_history, ttl_seconds=7200)