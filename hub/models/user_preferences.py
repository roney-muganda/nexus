import uuid
from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, ForeignKey, func, Enum as SAEnum, BigInteger
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB, ARRAY
import enum
from hub.models.database import Base

class VerbosityLevel(str, enum.Enum):
    terse    = "terse"
    normal   = "normal"
    detailed = "detailed"

class UserPreferences(Base):
    __tablename__ = "user_preferences"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), unique=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(60), default="UTC")
    language: Mapped[str] = mapped_column(String(10), default="en")
    preferred_channels: Mapped[list] = mapped_column(ARRAY(String), default=["telegram"])
    verbosity: Mapped[VerbosityLevel] = mapped_column(SAEnum(VerbosityLevel), default=VerbosityLevel.normal)
    daily_briefing_time: Mapped[str] = mapped_column(String(10), nullable=True)
    working_hours: Mapped[dict] = mapped_column(JSONB, default=lambda: {"start": "09:00", "end": "18:00"})
    llm_temperature: Mapped[float] = mapped_column(Float, default=0.7)
    integrations: Mapped[dict] = mapped_column(JSONB, default=dict)
    command_allowlist: Mapped[list] = mapped_column(ARRAY(String), default=list)
    memory_retention_days: Mapped[int] = mapped_column(Integer, default=365)
    last_briefing_sent_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True
)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user: Mapped["User"] = relationship("User", back_populates="preferences")
    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )

    telegram_chat_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True
    )