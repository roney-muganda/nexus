from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from hub.config import settings
from hub.api import auth, tasks, memory, chat, websocket

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup
    print(f"Starting {settings.app_name}...")
    yield
    # shutdown
    print("Shutting down...")

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

@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}