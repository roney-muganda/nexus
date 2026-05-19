# NEXUS — Autonomous Personal Assistant

A cross-platform, RAG-enabled personal AI assistant built on a Hub-and-Spoke architecture. A centralized brain hosted on the cloud manages tasks, reminders, memory, and technical workflows across a Windows laptop and Android mobile device.

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Local Development Setup](#local-development-setup)
- [Environment Variables](#environment-variables)
- [Database Migrations](#database-migrations)
- [Running the Application](#running-the-application)
- [API Reference](#api-reference)
- [Available Tools](#available-tools)
- [Memory System](#memory-system)
- [Device Spokes](#device-spokes)
- [Testing](#testing)
- [Roadmap](#roadmap)

---

## Overview

NEXUS operates in three core modes:

- **Developer Mode** — execute terminal commands, manage project milestones, search codebases, track tasks
- **Student Mode** — store and retrieve learning notes across software and civil engineering, spaced repetition review
- **Admin Mode** — email summarization, reply drafting, task extraction, cross-device notifications

The system is designed around a single principle: the Hub owns all state and intelligence. Device spokes are thin, stateless clients that handle I/O and OS-level integration.

---

## Architecture

```
┌─────────────────────────────────────────┐
│           NEXUS HUB (Render)            │
│                                         │
│  FastAPI Gateway + WebSocket Server     │
│  ↓                                      │
│  LLM Orchestrator (Groq / Llama 3.3)   │
│  ↓                                      │
│  Tool Dispatcher → 7 core tools         │
│  ↓                                      │
│  Memory Manager (ChromaDB + Postgres)   │
│  ↓                                      │
│  Scheduler (Celery + APScheduler)       │
└──────────────┬──────────────────────────┘
               │
       ┌───────┴────────┐
       ↓                ↓
┌─────────────┐  ┌──────────────────┐
│ Android     │  │ Windows Desktop  │
│ Spoke       │  │ Spoke            │
│             │  │                  │
│ Telegram    │  │ Python WS Client │
│ Bot         │  │ Subprocess Exec  │
│ Tasker      │  │ File Indexer     │
│ Profiles    │  │ Win Notifier     │
└─────────────┘  └──────────────────┘
```

**Data stores:**
- PostgreSQL — structured data: tasks, users, preferences, conversation history, audit log
- ChromaDB — vector embeddings for semantic memory retrieval
- Redis — task queue, session state, rate limiting

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API Framework | FastAPI + Uvicorn |
| LLM | Groq (Llama 3.3 70B Versatile) |
| Embeddings | sentence-transformers (all-MiniLM-L6-v2) |
| Vector DB | ChromaDB |
| Relational DB | PostgreSQL 15 |
| ORM | SQLAlchemy 2.0 (async) |
| Migrations | Alembic |
| Task Queue | Celery + Redis |
| Auth | JWT (HS256) + API Keys |
| Mobile | Telegram Bot API + Tasker |
| Desktop | Python WebSocket client + subprocess |
| Hosting | Render.com |

---

## Project Structure

```
nexus/
├── hub/                        # Core application
│   ├── main.py                 # FastAPI entrypoint
│   ├── config.py               # Settings from .env
│   ├── api/                    # Route handlers
│   │   ├── auth.py             # Register, login
│   │   ├── chat.py             # Main conversation endpoint
│   │   ├── tasks.py            # Task CRUD
│   │   ├── memory.py           # Memory read/write
│   │   └── websocket.py        # Desktop spoke WS handler
│   ├── core/                   # Business logic
│   │   ├── orchestrator.py     # LLM function calling loop
│   │   ├── context_builder.py  # Prompt assembly
│   │   ├── tool_dispatcher.py  # Tool execution router
│   │   └── tool_schemas.py     # JSON schemas for all 7 tools
│   ├── memory/                 # RAG memory system
│   │   ├── manager.py          # Embed, store, retrieve
│   │   ├── chroma_client.py    # ChromaDB connection
│   │   └── embedder.py         # Sentence-transformers wrapper
│   ├── models/                 # SQLAlchemy ORM models
│   │   ├── user.py
│   │   ├── task.py
│   │   ├── memory_context.py
│   │   ├── user_preferences.py
│   │   ├── conversation_turn.py
│   │   ├── audit_log.py
│   │   └── api_key.py
│   ├── auth/                   # Auth utilities
│   │   ├── jwt_handler.py
│   │   ├── password.py
│   │   ├── hmac_signer.py
│   │   ├── api_keys.py
│   │   └── dependencies.py
│   └── scheduler/              # Proactive jobs
│       ├── celery_app.py
│       ├── daily_briefing.py
│       └── reminder_firing.py
├── desktop_spoke/              # Windows background service
│   ├── main.py
│   ├── ws_client.py
│   ├── executor.py
│   └── allowlist.py
├── android_spoke/              # Tasker profiles
│   └── profiles/
├── scripts/
│   ├── test_setup.py           # Setup verification
│   ├── index_documents.py      # Bulk index docs to ChromaDB
│   └── seed_db.py
├── migrations/                 # Alembic migrations
├── docker-compose.yml          # Local dev services
├── requirements.txt
└── .env.example
```

---

## Prerequisites

- Python 3.12+
- Docker Desktop
- Node.js (optional, for future frontend)
- A Groq API key — free at [console.groq.com](https://console.groq.com)
- A Telegram Bot token — create via [@BotFather](https://t.me/BotFather)

---

## Local Development Setup

**1. Clone and create virtual environment**

```bash
git clone https://github.com/your-username/nexus.git
cd nexus
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Copy and configure environment variables**

```bash
cp .env.example .env
# Edit .env with your actual values
```

**4. Start local services**

```bash
docker-compose up -d
```

This starts PostgreSQL (port 5434), Redis (port 6380), and ChromaDB (port 8001).

**5. Run database migrations**

```bash
alembic upgrade head
```

**6. Verify setup**

```bash
python scripts/test_setup.py
```

All 8 checks should pass before proceeding.

---

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `GROQ_API_KEY` | Groq API key for LLM | Yes |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token | Yes |
| `SECRET_KEY` | JWT signing secret | Yes |
| `HMAC_SECRET` | Desktop spoke payload signing | Yes |
| `CHROMA_HOST` | ChromaDB host | Yes |
| `CHROMA_PORT` | ChromaDB port (default 8001) | Yes |
| `GEMINI_API_KEY` | Google Gemini key (optional fallback) | No |
| `JWT_ALGORITHM` | JWT algorithm (default HS256) | No |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Token TTL (default 60) | No |

See `.env.example` for a full template.

---

## Database Migrations

```bash
# Generate a new migration after model changes
alembic revision --autogenerate -m "description"

# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Check current migration state
alembic current

# View migration history
alembic history
```

---

## Running the Application

**Development (with hot reload):**

```bash
uvicorn hub.main:app --reload
```

**Production:**

```bash
uvicorn hub.main:app --host 0.0.0.0 --port 8000 --workers 4
```

API docs available at `http://127.0.0.1:8000/docs` once running.

---

## API Reference

### Authentication

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create a new user account |
| POST | `/api/auth/login` | Login and receive JWT token |
| GET | `/api/auth/me` | Get current user info |

**Register:**
```json
POST /api/auth/register
{
  "email": "you@example.com",
  "password": "yourpassword",
  "full_name": "Your Name"
}
```

**Login response:**
```json
{
  "access_token": "eyJhbGci...",
  "token_type": "bearer"
}
```

All subsequent requests require the header:
```
Authorization: Bearer <your_token>
```

### Chat

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/chat/` | Send a message to the assistant |

```json
POST /api/chat/
{
  "message": "Set a reminder to review my structural analysis notes at 9am tomorrow",
  "session_id": "optional-uuid-to-continue-conversation",
  "device": "web"
}
```

Response:
```json
{
  "reply": "I've set a reminder for tomorrow at 9:00 AM...",
  "session_id": "generated-or-provided-uuid"
}
```

Pass the returned `session_id` in follow-up messages to maintain conversation context. Omit it to start a fresh session.

### Health Check

```
GET /health
→ {"status": "ok", "app": "nexus"}
```

---

## Available Tools

The assistant has 7 core tools it can invoke autonomously based on your intent:

| Tool | Description |
|------|-------------|
| `set_reminder` | Creates a timed reminder with multi-channel notification |
| `search_technical_docs` | Semantic search across indexed documentation |
| `execute_terminal_command` | Runs shell commands on Windows via Desktop spoke |
| `update_project_milestone` | Creates or updates project tasks with status tracking |
| `store_memory` | Persists important facts, preferences, and context to long-term memory |
| `store_learning` | Stores study notes tagged by domain for spaced repetition |
| `web_search_and_summarize` | Searches the web and summarizes results (coming Sprint 5) |

Tools are invoked automatically — you never need to call them explicitly. Just speak naturally and the assistant decides which tools to use.

---

## Memory System

NEXUS uses a two-layer RAG memory architecture:

**Storage:**
- Every important piece of context is embedded using `all-MiniLM-L6-v2` (384 dimensions)
- Vectors stored in ChromaDB with cosine similarity search
- Metadata (type, importance, tags, access count) stored in PostgreSQL

**Retrieval:**
- On every message, the top-5 semantically relevant memories are retrieved
- Relevance score = 70% cosine similarity + 30% importance weight
- Retrieved memories are injected into the system prompt as context

**Memory types:** `fact`, `preference`, `skill`, `event`, `relationship`, `learning`

**Decay:** Memories not accessed in 30 days have their importance score reduced by 15%, keeping the retrieval space clean and relevant.

---

## Device Spokes

### Android Spoke

The Android spoke uses Telegram as the primary UI and Tasker for OS-level automation.

**Setup:**
1. Install Tasker on your Android device
2. Set up Tailscale for secure private networking between phone and Hub
3. Import Tasker profiles from `android_spoke/profiles/`
4. Configure the HTTP receiver with your Hub's Tailscale IP

**Supported actions via `control_android_device` tool:**
- `send_notification` — push custom notifications
- `open_app` — launch any installed app
- `set_alarm` — create system alarms
- `toggle_wifi` — enable/disable WiFi
- `read_clipboard` — read clipboard contents

### Windows Desktop Spoke

The Desktop spoke runs as a background Python service with a persistent WebSocket connection to the Hub.

**Setup:**
```bash
cd desktop_spoke
pip install -r requirements.txt
python main.py
```

The agent will auto-reconnect if the connection drops. For permanent background operation, install as a Windows service using the provided `build.spec` with PyInstaller.

**Security:** All commands are HMAC-signed by the Hub and verified by the agent before execution. A command allowlist prevents execution of unauthorized shell commands.

---

## Testing

**Run the full setup verification:**
```bash
python scripts/test_setup.py
```

This verifies all 8 components: environment variables, PostgreSQL, Redis, ChromaDB, FastAPI app import, SQLAlchemy models, embedding model, and memory collection access.

**Run unit tests:**
```bash
pytest hub/tests/ -v
```

**Test the chat endpoint (PowerShell):**
```powershell
# Login first
$login = Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/auth/login" `
  -Method POST -ContentType "application/json" `
  -Body '{"email": "you@example.com", "password": "yourpassword"}'
$token = ($login.Content | ConvertFrom-Json).access_token

# Send a chat message
Invoke-WebRequest -Uri "http://127.0.0.1:8000/api/chat/" `
  -Method POST -ContentType "application/json" `
  -Headers @{"Authorization" = "Bearer $token"} `
  -Body '{"message": "What can you help me with?", "device": "web"}'
```

---

## Roadmap

| Sprint | Weeks | Status | Focus |
|--------|-------|--------|-------|
| 1 | 1–2 | ✅ Done | Project setup, FastAPI, PostgreSQL, Docker |
| 2 | 3–4 | ✅ Done | Auth (JWT, API keys, HMAC), user registration/login |
| 3 | 5–6 | ✅ Done | LLM orchestration, function calling loop, Groq integration |
| 4 | 7–8 | ✅ Done | RAG memory system, ChromaDB, semantic retrieval |
| 5 | 9–10 | 🔄 Next | Android spoke, Tasker integration, Telegram bot wiring |
| 6 | 11–12 | ⬜ Planned | Windows Desktop spoke, command execution, file indexer |
| 7 | 13–14 | ⬜ Planned | Scheduler, daily briefing, proactive reminders, web search |
| 8 | 15–16 | ⬜ Planned | Email integration, admin tools, student mode tools |
| 9 | 17–18 | ⬜ Planned | Harden, observability, Render deployment, documentation |

---

## Contributing

This is a personal productivity tool. If you fork it and adapt it for your own use, keep the following in mind:

- Never commit `.env` — use `.env.example` as the template
- All command execution goes through the allowlist in `desktop_spoke/allowlist.py`
- Rotate `SECRET_KEY` and `HMAC_SECRET` before any public deployment
- The memory system is user-scoped — all ChromaDB queries include `user_id` filters

---

## License

Private — personal use only.
