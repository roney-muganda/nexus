from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from hub.config import settings


clean_db_url = str(settings.database_url)


if clean_db_url.startswith("postgres://"):
    clean_db_url = clean_db_url.replace("postgres://", "postgresql+asyncpg://", 1)
elif clean_db_url.startswith("postgresql://"):
    clean_db_url = clean_db_url.replace("postgresql://", "postgresql+asyncpg://", 1)


clean_db_url = clean_db_url.replace("?sslmode=require", "")
clean_db_url = clean_db_url.replace("&sslmode=require", "")

# 4. Pass the squeaky-clean URL string to the engine
engine = create_async_engine(
    clean_db_url,
    echo=settings.debug,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()