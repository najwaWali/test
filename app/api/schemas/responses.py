from datetime import datetime

from pydantic import BaseModel

from app.db.models.ticket import Ticket
from app.helpers.enums import Category, Priority, TicketStatus


class TicketResponse(BaseModel):
    id: str
    subject: str
    body: str
    status: TicketStatus
    category: Category | None
    priority: Priority | None
    summary: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_ticket(cls, ticket: Ticket) -> "TicketResponse":
        return cls(
            id=ticket.source_id,
            subject=ticket.subject,
            body=ticket.body,
            status=TicketStatus(ticket.status),
            category=Category(ticket.category) if ticket.category else None,
            priority=Priority(ticket.priority) if ticket.priority else None,
            summary=ticket.summary,
            created_at=ticket.created_at,
            updated_at=ticket.updated_at,
        )


class TicketListResponse(BaseModel):
    items: list[TicketResponse]
    total: int
    limit: int
    offset: int


class ErrorResponse(BaseModel):
    detail: str
    code: str
