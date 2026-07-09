from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from hub.config import settings
from hub.api import auth, tasks, memory, chat, websocket, telegram
from hub.core.redis_client import check_redis_health, close_redis

from hub.scheduler.scheduler import get_scheduler
from hub.scheduler.jobs import (
    fire_due_reminders,
    send_daily_briefing,
    check_project_health,
    sync_upcoming_reminders_to_redis
)

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    print(f"Starting {settings.app_name}...")
    
    # 1. Initialize and verify Redis connection
    await check_redis_health()
    
    scheduler = None
    try:
        # 2. Seed the Redis cache with upcoming tasks immediately on boot
        print("Seeding Redis reminders cache from Postgres...")
        await sync_upcoming_reminders_to_redis()

        scheduler = get_scheduler()

        # 3. Fire reminders every minute (This now safely reads ONLY from Redis)
        scheduler.add_job(
            fire_due_reminders,
            trigger="interval",
            minutes=1,
            id="fire_reminders",
            replace_existing=True
        )

        # 4. Sync Postgres upcoming tasks to Redis every 6 hours
        scheduler.add_job(
            sync_upcoming_reminders_to_redis,
            trigger="interval",
            hours=6,
            id="sync_reminders",
            replace_existing=True
        )

        # 5. Daily briefing check — checks every 30 mins to catch the 59-minute window
        scheduler.add_job(
            send_daily_briefing,
            trigger="interval",
            minutes=30, 
            id="daily_briefing",
            replace_existing=True
        )

        # 6. Project health check every 6 hours
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
        
    # Close Redis cleanly to prevent connection leaks
    await close_redis()

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