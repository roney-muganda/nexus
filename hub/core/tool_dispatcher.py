import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from hub.models.task import Task, TaskStatus
from hub.models.memory_context import MemoryContext, MemoryType
import uuid


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
        chroma_id = str(uuid.uuid4())
        memory = MemoryContext(
            user_id=self.user_id,
            chroma_id=chroma_id,
            content=args["content"],
            memory_type=MemoryType(args["memory_type"]),
            importance=0.5,
            tags=args.get("tags", []),
            source="assistant"
        )
        self.db.add(memory)
        await self.db.flush()
        return {"status": "stored", "memory_id": chroma_id}

    async def _store_learning(self, args: dict) -> dict:
        content = f"{args['concept']}: {args['explanation']}"
        chroma_id = str(uuid.uuid4())
        memory = MemoryContext(
            user_id=self.user_id,
            chroma_id=chroma_id,
            content=content,
            memory_type=MemoryType.learning,
            importance=float(0.7),
            tags=[args["domain"], "learning"],
            source=args.get("source", "user")
        )
        self.db.add(memory)
        await self.db.flush()
        return {"status": "stored", "concept": args["concept"], "domain": args["domain"]}

    async def _search_technical_docs(self, args: dict) -> dict:
        # stub — will connect to ChromaDB in Task 4
        return {"results": [], "message": "Doc search not yet implemented — coming in Task 4"}

    async def _execute_terminal_command(self, args: dict) -> dict:
        # stub — will connect to Desktop spoke in Task 10
        return {"status": "pending", "message": "Desktop spoke not yet connected — coming in Task 10"}

    async def _web_search_and_summarize(self, args: dict) -> dict:
        # stub — will connect to search API in Task 8
        return {"status": "pending", "message": "Web search not yet implemented — coming in Task 8"}