import json
import uuid
import time
import logging
from sqlalchemy import select, delete
from groq import Groq
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
        self.model = "llama-3.3-70b-versatile"

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
        memory_manager=MemoryManager(db=self.db, user_id=self.user_id)
        memories = await memory_manager.retrieve(user_message, top_k=5)

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        if memories:
            memory_block = "\n".join([
                f"- [{m['type']}] {m['content']}"
                for m in memories
            ])
            messages.append({
                "role": "user",
                "content": f"[MEMORY CONTEXT]\n{memory_block}"
            })
            messages.append({
                "role": "assistant",
                "content": "Memory context loaded."
            })        
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

        await self._save_turn(session_id, TurnRole.user, user_message, device)

        tools = self._build_tools()
        tool_calls_made = 0 
        max_tool_calls = 3
        final_response = ""

        while True:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=8192,
                temperature=0.7,
            )

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

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result
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
        history = []
        for turn in turns:
            role = "user" if turn.role == TurnRole.user else "assistant"
            if turn.content:
                history.append({
                    "role": role,
                    "content": turn.content
                })
        return history

    async def _save_turn(
        self,
        session_id: str,
        role: TurnRole,
        content: str,
        device: str,
        latency_ms: int = None
    ):
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