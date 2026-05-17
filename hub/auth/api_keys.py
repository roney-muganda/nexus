import secrets
import hashlib
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, Column, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from hub.models.database import Base
import uuid
from datetime import datetime
from sqlalchemy import func


class APIKey(Base):
    __tablename__ = "api_keys"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    device_id: Mapped[str] = mapped_column(String(100), nullable=True)
    scopes: Mapped[str] = mapped_column(String(500), default="read:memory,write:tasks")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


def generate_api_key() -> tuple[str, str]:
    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, key_hash


async def verify_api_key(raw_key: str, db: AsyncSession) -> APIKey | None:
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    result = await db.execute(
        select(APIKey).where(APIKey.key_hash == key_hash)
    )
    return result.scalar_one_or_none()