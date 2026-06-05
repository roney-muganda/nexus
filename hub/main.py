from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from hub.config import settings
from hub.api import auth, tasks, memory, chat, websocket, telegram

from hub.scheduler.scheduler import get_scheduler
from hub.scheduler.jobs import (
    fire_due_reminders,
    send_daily_briefing,
    check_project_health
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    print(f"Starting {settings.app_name}...")
    
    scheduler = None
    try:
        scheduler = get_scheduler()

        # fire reminders every minute
        scheduler.add_job(
            fire_due_reminders,
            trigger="interval",
            minutes=1,
            id="fire_reminders",
            replace_existing=True
        )

        # daily briefing check — now runs EVERY minute to honor exact HH:MM settings
        scheduler.add_job(
            send_daily_briefing,
            trigger="cron",
            minute="*", 
            id="daily_briefing",
            replace_existing=True
        )

        # project health check every 6 hours
        scheduler.add_job(
            check_project_health,
            trigger="interval",
            hours=6,
            id="project_health",
            replace_existing=True
        )

        scheduler.start()
        print("Scheduler started successfully.")
    except Exception as e:
        # Catch any connection or setup errors to prevent complete app failure
        logger.error(f"Failed to start background scheduler: {e}")
        print("Warning: API is running, but background tasks (reminders/briefings) are disabled.")

    yield

    # shutdown
    if scheduler and scheduler.running:
        scheduler.shutdown(wait=False)
        print("Shutting down scheduler...")

app = FastAPI(
    title="NEXUS",
    description="Autonomous Personal Assistant Hub",
    version="0.1.0",
    debug=settings.debug,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(auth.router,      prefix="/api/auth",    tags=["auth"])
app.include_router(tasks.router,     prefix="/api/tasks",   tags=["tasks"])
app.include_router(memory.router,    prefix="/api/memory",  tags=["memory"])
app.include_router(chat.router,      prefix="/api/chat",    tags=["chat"])
app.include_router(websocket.router, prefix="/ws",          tags=["websocket"])
app.include_router(telegram.router,  prefix="/api/telegram", tags=["telegram"])

@app.get("/health")
@app.head("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}