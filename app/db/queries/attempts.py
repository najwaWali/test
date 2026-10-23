from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.db.models.classification_attempt import ClassificationAttempt


def upsert_attempt(
    session: Session,
    *,
    ticket_id: str | UUID,
    attempt_number: int,
    status: str,
    raw_response: str | None = None,
    parsed_category: str | None = None,
    parsed_priority: str | None = None,
    parsed_summary: str | None = None,
) -> ClassificationAttempt:
    stmt = pg_insert(ClassificationAttempt).values(
        ticket_id=ticket_id,
        attempt_number=attempt_number,
        status=status,
        raw_response=raw_response,
        parsed_category=parsed_category,
        parsed_priority=parsed_priority,
        parsed_summary=parsed_summary,
    )
    excluded = stmt.excluded
    stmt = stmt.on_conflict_do_update(
        constraint="uq_attempts_ticket_attempt_number",
        set_={
            "status": excluded.status,
            "raw_response": func.coalesce(
                excluded.raw_response, ClassificationAttempt.raw_response
            ),
            "parsed_category": func.coalesce(
                excluded.parsed_category, ClassificationAttempt.parsed_category
            ),
            "parsed_priority": func.coalesce(
                excluded.parsed_priority, ClassificationAttempt.parsed_priority
            ),
            "parsed_summary": func.coalesce(
                excluded.parsed_summary, ClassificationAttempt.parsed_summary
            ),
        },
    )
    session.execute(stmt)

    return session.execute(
        select(ClassificationAttempt).where(
            ClassificationAttempt.ticket_id == ticket_id,
            ClassificationAttempt.attempt_number == attempt_number,
        )
    ).scalar_one()


def get_by_ticket_and_attempt(
    session: Session, ticket_id: str | UUID, attempt_number: int
) -> ClassificationAttempt | None:
    return session.execute(
        select(ClassificationAttempt).where(
            ClassificationAttempt.ticket_id == ticket_id,
            ClassificationAttempt.attempt_number == attempt_number,
        )
    ).scalar_one_or_none()


def latest_for_ticket(
    session: Session, ticket_id: str | UUID
) -> ClassificationAttempt | None:
    return session.execute(
        select(ClassificationAttempt)
        .where(ClassificationAttempt.ticket_id == ticket_id)
        .order_by(ClassificationAttempt.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
