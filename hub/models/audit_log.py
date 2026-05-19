import uuid
from datetime import datetime
from sqlalchemy import String, Text, BigInteger, DateTime, ForeignKey, func, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID, INET
import enum
from hub.models.database import Base

class AuditResult(str, enum.Enum):
    success  = "success"
    failed   = "failed"
    rejected = "rejected"

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    actor: Mapped[str] = mapped_column(String(100), nullable=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    result: Mapped[AuditResult] = mapped_column(SAEnum(AuditResult), nullable=False)
    error_message: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())