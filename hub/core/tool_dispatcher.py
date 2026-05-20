import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from hub.models.task import Task, TaskStatus
from hub.memory.manager import MemoryManager
from hub.models.memory_context import MemoryType
import uuid
from hub.tools.developer.project_context import get_project_context
from hub.tools.developer.search_docs import search_technical_docs


class ToolDispatcher:
    def __init__(self, db: AsyncSession, user_id: str):
        self.db = db
        self.user_id = user_id

    async def execute(self, tool_name: str, args: dict) -> str:
        handlers = {
            "set_reminder":             self._set_reminder,
            "search_technical_docs":    self._search_technical_docs,
            "execute_terminal_command": self._execute_terminal_command,
            "update_project_milestone": self._update_project_milestone,
            "store_memory":             self._store_memory,
            "store_learning":           self._store_learning,
            "web_search_and_summarize": self._web_search_and_summarize,
            "get_project_context":      self._get_project_context,
        }
        handler = handlers.get(tool_name)
        if not handler:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})
        try:
            result = await handler(args)
            return json.dumps(result)
        except Exception as e:
            return json.dumps({"error": str(e)})

    async def _set_reminder(self, args: dict) -> dict:
        task = Task(
            user_id=self.user_id,
            title=args["title"],
            reminder_at=datetime.fromisoformat(
                args["datetime_utc"].replace("Z", "+00:00")
            ),
            recurrence=args.get("recurrence"),
            channels=args.get("channels", ["telegram"]),
            priority=args.get("priority", 2),
            status=TaskStatus.todo,
            source_device="assistant"
        )
        self.db.add(task)
        await self.db.flush()
        return {"status": "created", "reminder_id": str(task.id), "title": task.title}

    async def _update_project_milestone(self, args: dict) -> dict:
        task = Task(
            user_id=self.user_id,
            title=args["title"],
            status=TaskStatus(args["status"]),
            priority=args.get("priority", 2),
            description=args.get("notes"),
            source_device="assistant"
        )
        if args.get("due_date"):
            task.due_at = datetime.fromisoformat(args["due_date"])
        self.db.add(task)
        await self.db.flush()
        return {"status": "saved", "task_id": str(task.id), "title": task.title}

    async def _store_memory(self, args: dict) -> dict:
        importance_map = {
            "fact": 0.6,
            "preference": 0.8,
            "skill": 0.7,
            "event": 0.5,
            "relationship": 0.8,
            "learning": 0.7,
        }
        memory_type = args["memory_type"]
        importance = importance_map.get(memory_type, 0.5)
        manager = MemoryManager(db=self.db, user_id=self.user_id)
        chroma_id = await manager.store(
            content=args["content"],
            memory_type=MemoryType(memory_type),
            importance=importance,
            tags=args.get("tags", []),
            source="user_stated"
        )
        return {"status": "stored", "memory_id": chroma_id}

    async def _store_learning(self, args: dict) -> dict:
        content = f"{args['concept']}: {args['explanation']}"
        manager = MemoryManager(db=self.db, user_id=self.user_id)
        chroma_id = await manager.store(
            content=content,
            memory_type=MemoryType.learning,
            importance=0.7,
            tags=[args["domain"], "learning"],
            source=args.get("source", "user")
        )
        return {
            "status": "stored",
            "memory_id": chroma_id,
            "concept": args["concept"],
            "domain": args["domain"]
        }

    async def _search_technical_docs(self, args: dict) -> dict:
        return await search_technical_docs(
            query=args["query"],
            sources=args.get("sources"),
            top_k=args.get("top_k", 5),
        )

    async def _get_project_context(self, args: dict) -> dict:
        return await get_project_context(
            db=self.db,
            user_id=self.user_id,
            project_name=args.get("project_name"),
            project_id=args.get("project_id"),
        )

    async def _execute_terminal_command(self, args: dict) -> dict:
        return {"status": "pending", "message": "Desktop spoke coming in Task 10"}

    async def _web_search_and_summarize(self, args: dict) -> dict:
        return {"status": "pending", "message": "Web search coming in Task 8"}