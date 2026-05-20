import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from hub.models.project import Project
from hub.models.task import Task, TaskStatus


async def get_project_context(
    db: AsyncSession,
    user_id: str,
    project_name: str = None,
    project_id: str = None,
) -> dict:
    # find the project
    if project_id:
        result = await db.execute(
            select(Project).where(
                and_(
                    Project.id == uuid.UUID(project_id),
                    Project.user_id == uuid.UUID(user_id)
                )
            )
        )
        project = result.scalar_one_or_none()
    elif project_name:
        result = await db.execute(
            select(Project).where(
                and_(
                    Project.name.ilike(f"%{project_name}%"),
                    Project.user_id == uuid.UUID(user_id)
                )
            )
        )
        project = result.scalar_one_or_none()
    else:
        # return all active projects summary
        result = await db.execute(
            select(Project).where(
                and_(
                    Project.user_id == uuid.UUID(user_id),
                    Project.is_active == True
                )
            )
        )
        projects = result.scalars().all()
        return {
            "type": "all_projects",
            "count": len(projects),
            "projects": [
                {
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description,
                    "tech_stack": p.tech_stack,
                }
                for p in projects
            ]
        }

    if not project:
        return {"error": f"Project '{project_name or project_id}' not found"}

    # get tasks grouped by status
    tasks_result = await db.execute(
        select(Task).where(
            and_(
                Task.project_id == project.id,
                Task.user_id == uuid.UUID(user_id)
            )
        ).order_by(Task.priority, Task.due_at)
    )
    tasks = tasks_result.scalars().all()

    todo = [t for t in tasks if t.status == TaskStatus.todo]
    in_progress = [t for t in tasks if t.status == TaskStatus.in_progress]
    blocked = [t for t in tasks if t.status == TaskStatus.blocked]
    done_recent = [
        t for t in tasks
        if t.status == TaskStatus.done
        and t.completed_at
        and t.completed_at > datetime.now(timezone.utc) - timedelta(days=7)
    ]

    # check overdue tasks
    now = datetime.now(timezone.utc)
    overdue = [
        t for t in tasks
        if t.due_at and t.due_at < now
        and t.status not in [TaskStatus.done, TaskStatus.cancelled]
    ]

    def task_summary(t: Task) -> dict:
        return {
            "id": str(t.id),
            "title": t.title,
            "priority": t.priority,
            "due_at": t.due_at.isoformat() if t.due_at else None,
            "description": t.description,
        }

    return {
        "project": {
            "id": str(project.id),
            "name": project.name,
            "description": project.description,
            "tech_stack": project.tech_stack,
            "repo_path": project.repo_path,
            "repo_url": project.repo_url,
        },
        "summary": {
            "total_tasks": len(tasks),
            "todo": len(todo),
            "in_progress": len(in_progress),
            "blocked": len(blocked),
            "overdue": len(overdue),
            "done_this_week": len(done_recent),
        },
        "in_progress": [task_summary(t) for t in in_progress],
        "blocked": [task_summary(t) for t in blocked],
        "overdue": [task_summary(t) for t in overdue],
        "next_up": [task_summary(t) for t in todo[:5]],
        "done_this_week": [task_summary(t) for t in done_recent],
    }