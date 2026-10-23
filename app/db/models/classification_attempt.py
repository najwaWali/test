from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.models import Base


class ClassificationAttempt(Base):
    __tablename__ = "classification_attempts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    raw_response: Mapped[str | None] = mapped_column(Text)
    parsed_category: Mapped[str | None] = mapped_column(String(16))
    parsed_priority: Mapped[str | None] = mapped_column(String(8))
    parsed_summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=text("NOW()"), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("ticket_id", "attempt_number", name="uq_attempts_ticket_attempt_number"),
        Index("idx_attempts_ticket_created", "ticket_id", text("created_at DESC")),
    )
