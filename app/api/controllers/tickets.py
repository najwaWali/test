import logging

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas.requests import CreateTicketRequest
from app.api.schemas.responses import TicketListResponse, TicketResponse
from app.db.queries import tickets as ticket_queries
from app.db.session import SessionLocal
from app.helpers.enums import Category, Priority
from app.helpers.exceptions import TicketNotFoundError
from app.services.temporal_client import start_classification_workflow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])


def get_db() -> Session:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@router.post(
    "",
    response_model=TicketResponse,
    summary="Create (or return existing) ticket; starts classification asynchronously.",
    responses={
        201: {"description": "New ticket created and queued for classification."},
        200: {"description": "A ticket with this id already exists; current state returned."},
    },
)
async def create_ticket(
    payload: CreateTicketRequest,
    response: Response,
    session: Session = Depends(get_db),
) -> TicketResponse:
    existing = ticket_queries.get_by_source_id(session, payload.id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return TicketResponse.from_ticket(existing)

    try:
        ticket = ticket_queries.insert_pending(
            session,
            source_id=payload.id,
            subject=payload.subject,
            body=payload.body,
        )
        session.commit()
    except IntegrityError:
        session.rollback()
        existing = ticket_queries.get_by_source_id(session, payload.id)
        if existing is None:
            raise
        response.status_code = status.HTTP_200_OK
        return TicketResponse.from_ticket(existing)

    await start_classification_workflow(str(ticket.id), ticket.source_id)

    response.status_code = status.HTTP_201_CREATED
    return TicketResponse.from_ticket(ticket)


@router.get(
    "/{ticket_id}",
    response_model=TicketResponse,
    summary="Look up a ticket by its client-supplied id.",
    responses={404: {"description": "No ticket with that id exists."}},
)
def get_ticket(ticket_id: str, session: Session = Depends(get_db)) -> TicketResponse:
    ticket = ticket_queries.get_by_source_id(session, ticket_id)
    if ticket is None:
        raise TicketNotFoundError(f"ticket '{ticket_id}' not found")
    return TicketResponse.from_ticket(ticket)


@router.get(
    "",
    response_model=TicketListResponse,
    summary="List tickets with optional category/priority filters and pagination.",
)
def list_tickets(
    category: Category | None = Query(default=None),
    priority: Priority | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> TicketListResponse:
    items, total = ticket_queries.list_filtered(
        session,
        category=category,
        priority=priority,
        limit=limit,
        offset=offset,
    )
    return TicketListResponse(
        items=[TicketResponse.from_ticket(t) for t in items],
        total=total,
        limit=limit,
        offset=offset,
    )
