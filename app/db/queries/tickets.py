from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.ticket import Ticket
from app.helpers.enums import Category, Priority, TicketStatus


def get_by_source_id(session: Session, source_id: str) -> Ticket | None:
    stmt = select(Ticket).where(Ticket.source_id == source_id)
    return session.execute(stmt).scalar_one_or_none()


def insert_pending(session: Session, source_id: str, subject: str, body: str) -> Ticket:
    ticket = Ticket(
        source_id=source_id,
        subject=subject,
        body=body,
        status=TicketStatus.PENDING.value,
    )
    session.add(ticket)
    session.flush()
    session.refresh(ticket)
    return ticket


def list_filtered(
    session: Session,
    category: Category | None,
    priority: Priority | None,
    limit: int,
    offset: int,
) -> tuple[list[Ticket], int]:
    filters = []
    if category is not None:
        filters.append(Ticket.category == category.value)
    if priority is not None:
        filters.append(Ticket.priority == priority.value)

    count_stmt = select(func.count()).select_from(Ticket)
    for f in filters:
        count_stmt = count_stmt.where(f)
    total = session.execute(count_stmt).scalar_one()

    page_stmt = select(Ticket)
    for f in filters:
        page_stmt = page_stmt.where(f)
    page_stmt = page_stmt.order_by(Ticket.created_at.desc()).limit(limit).offset(offset)
    page = list(session.execute(page_stmt).scalars().all())

    return page, total
