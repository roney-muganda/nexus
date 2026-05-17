import uuid
from datetime import datetime
from sqlalchemy import String, Text, Float, Integer, DateTime, ForeignKey, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID, ARRAY
import enum
from hub.models.database import Base

class MemoryType(str, enum.Enum):
    fact         = "fact"
    preference   = "preference"
    skill        = "skill"
    event        = "event"
    relationship = "relationship"
    research     = "research"
    learning     = "learning"

class MemoryContext(Base):
    __tablename__ = "memory_context"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    chroma_id: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    memory_type: Mapped[MemoryType] = mapped_column(SAEnum(MemoryType), nullable=False)
    importance: Mapped[float] = mapped_column(Float, default=0.5)
    access_count: Mapped[int] = mapped_column(Integer, default=0)
    last_accessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(100), nullable=True)
    tags: Mapped[list] = mapped_column(ARRAY(String), default=list)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    embedding_model: Mapped[str] = mapped_column(String(100), default="gemini-embedding-001")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", back_populates="memories")