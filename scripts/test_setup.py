import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

print("\n" + "="*50)
print("  NEXUS — Setup Verification")
print("="*50 + "\n")

# ── Test 1: Environment Variables ──────────────────
print("[ 1 ] Checking environment variables...")
required_vars = [
    "DATABASE_URL",
    "REDIS_URL",
    "GEMINI_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "SECRET_KEY",
    "HMAC_SECRET",
]
missing = []
for var in required_vars:
    val = os.getenv(var)
    if not val:
        missing.append(var)
        print(f"      ✗ {var} — MISSING")
    else:
        masked = val[:8] + "..." if len(val) > 8 else "***"
        print(f"      ✓ {var} = {masked}")

if missing:
    print(f"\n  ⚠ {len(missing)} variable(s) missing — add them to .env\n")
else:
    print("      All environment variables present.\n")


# ── Test 2: PostgreSQL ─────────────────────────────
print("[ 2 ] Testing PostgreSQL connection...")
try:
    import psycopg2
    db_url = os.getenv("DATABASE_URL", "").replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    cur.execute("""
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
    """)
    tables = [row[0] for row in cur.fetchall()]
    conn.close()
    print(f"      ✓ Connected — {version[:40]}")
    if tables:
        print(f"      ✓ Tables found: {', '.join(tables)}")
    else:
        print("      ⚠ No tables found — run: alembic upgrade head")
except Exception as e:
    print(f"      ✗ Failed — {e}")
print()


# ── Test 3: Redis ──────────────────────────────────
print("[ 3 ] Testing Redis connection...")
try:
    import redis
    redis_url = os.getenv("REDIS_URL", "redis://127.0.0.1:6379/0")
    r = redis.from_url(redis_url)
    r.set("nexus:test", "ok", ex=10)
    val = r.get("nexus:test")
    print(f"      ✓ Connected — ping: {r.ping()}")
    print(f"      ✓ Read/write OK — got: {val.decode()}")
except Exception as e:
    print(f"      ✗ Failed — {e}")
print()


# ── Test 4: ChromaDB ───────────────────────────────
print("[ 4 ] Testing ChromaDB connection...")
try:
    import chromadb
    host = os.getenv("CHROMA_HOST", "localhost")
    port = int(os.getenv("CHROMA_PORT", "8000"))
    client = chromadb.HttpClient(host=host, port=port)
    client.heartbeat()
    collections = client.list_collections()
    print(f"      ✓ Connected — host: {host}:{port}")
    print(f"      ✓ Collections: {len(collections)}")
except Exception as e:
    print(f"      ✗ Failed — {e}")
print()


# ── Test 5: FastAPI App Import ─────────────────────
print("[ 5 ] Testing FastAPI app import...")
try:
    from hub.main import app
    routes = [r.path for r in app.routes]
    print(f"      ✓ App imported successfully")
    print(f"      ✓ Routes registered: {len(routes)}")
    for route in routes:
        print(f"          {route}")
except Exception as e:
    print(f"      ✗ Failed — {e}")
print()


# ── Test 6: SQLAlchemy Models ──────────────────────
print("[ 6 ] Testing SQLAlchemy models...")
try:
    from hub.models.database import Base
    from hub.models.user import User
    from hub.models.task import Task
    from hub.models.memory_context import MemoryContext
    from hub.models.user_preferences import UserPreferences
    from hub.models.conversation_turn import ConversationTurn
    from hub.models.audit_log import AuditLog
    tables = list(Base.metadata.tables.keys())
    print(f"      ✓ All models imported successfully")
    print(f"      ✓ Registered tables: {', '.join(tables)}")
except Exception as e:
    print(f"      ✗ Failed — {e}")
print()

# ── Test 7: Embeddings ─────────────────────────────
print("[ 7 ] Testing embedding model...")
try:
    import asyncio
    from hub.memory.embedder import embed_text
    embedding = asyncio.run(embed_text("test sentence for embedding"))
    print(f"      ✓ Embedding generated — dimensions: {len(embedding)}")
except Exception as e:
    print(f"      ✗ Failed — {e}")
print()

# ── Test 8: Memory Manager ─────────────────────────
print("[ 8 ] Testing memory collection access...")
try:
    from hub.memory.chroma_client import get_or_create_collection, MEMORY_COLLECTION
    col = get_or_create_collection(MEMORY_COLLECTION)
    count = col.count()
    print(f"      ✓ Memory collection accessible")
    print(f"      ✓ Stored memories: {count}")
except Exception as e:
    print(f"      ✗ Failed — {e}")
print()


# ── Summary ────────────────────────────────────────
print("="*50)
print("  Done. Fix any ✗ items before proceeding.")
print("="*50 + "\n")