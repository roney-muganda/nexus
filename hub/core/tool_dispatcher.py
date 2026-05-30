import json
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from hub.models.task import Task, TaskStatus
from hub.memory.manager import MemoryManager
from hub.models.memory_context import MemoryType
import uuid
from hub.tools.developer.project_context import get_project_context
from hub.tools.developer.search_docs import search_technical_docs
from hub.tools.student.review_quiz import generate_review_quiz, get_learning_summary
from hub.tools.admin.email_reader import read_and_summarize_emails
from hub.tools.admin.email_drafter import draft_email_reply, create_task_from_email

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
            "generate_review_quiz":     self._generate_review_quiz,
            "get_learning_summary":     self._get_learning_summary,
            "read_emails":              self._read_emails,
            "draft_email_reply":        self._draft_email_reply,
            "create_tasks_from_email":  self._create_tasks_from_email,
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

    async def _generate_review_quiz(self, args: dict) -> dict:
        return await generate_review_quiz(
            db=self.db,
            user_id=self.user_id,
            domain=args.get("domain"),
            num_questions=args.get("num_questions", 5),
    )

    async def _get_learning_summary(self, args: dict) -> dict:
        return await get_learning_summary(
            db=self.db,
            user_id=self.user_id,
            domain=args.get("domain"),
            days=args.get("days", 7),
    )

    async def _execute_terminal_command(self, args: dict) -> dict:
        from hub.api.websocket import send_command_to_spoke
        return await send_command_to_spoke(
            device_id="windows_laptop_001",
            command=args["command"],
            working_dir=args.get("working_dir"),
            timeout_s=args.get("timeout_s", 30),
            require_confirm=args.get("require_confirm", False),
    )

    async def _web_search_and_summarize(self, args: dict) -> dict:
        return {"status": "pending", "message": "Web search coming in Task 8"}

    async def _read_emails(self, args: dict) -> dict:
        return await read_and_summarize_emails(
            user_id=str(self.user_id),
            max_results=args.get("max_results", 10),
            query=args.get("query", "is:unread"),
        )

    async def _draft_email_reply(self, args: dict) -> dict:
        return await draft_email_reply(
            user_id=str(self.user_id),
            thread_id=args.get("thread_id"),
            to=args.get("to"),
            subject=args.get("subject"),
            intent=args["intent"],
            send_immediately=args.get("send_immediately", False),
        )

    async def _create_tasks_from_email(self, args: dict) -> dict:
        return await create_task_from_email(
            email_id=args["email_id"],
            user_id=self.user_id,
            db=self.db,
        )