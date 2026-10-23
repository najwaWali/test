import json
from dataclasses import asdict

from sqlalchemy import select
from temporalio import activity
from temporalio.exceptions import ApplicationError

from app.db.models.ticket import Ticket
from app.db.queries import attempts as attempts_q
from app.db.session import SessionLocal
from app.helpers.enums import (
    VALIDATION_ERROR_TYPE,
    AttemptStatus,
    Category,
    ClassifyActivity,
    Priority,
    TicketStatus,
)
from app.workflows.classifier import get_classifier
from app.workflows.schemas.activity_io import (
    CallLLMInput,
    CallLLMOutput,
    MarkFailedInput,
    ParsedClassification,
    PersistResultInput,
    ValidateOutputInput,
)

MAX_SUMMARY_LENGTH = 300

_VALID_CATEGORIES = {c.value for c in Category}
_VALID_PRIORITIES = {p.value for p in Priority}


def _reject(message: str) -> ApplicationError:
    return ApplicationError(message, type=VALIDATION_ERROR_TYPE, non_retryable=True)


@activity.defn(name=ClassifyActivity.GET_TICKET_STATUS.value)
async def get_ticket_status(payload: dict) -> dict:
    ticket_id = payload["ticket_id"]
    with SessionLocal() as session:
        status = session.execute(
            select(Ticket.status).where(Ticket.id == ticket_id)
        ).scalar_one_or_none()
    if status is None:
        raise ApplicationError(f"ticket {ticket_id} not found", non_retryable=True)
    return {"status": status}


@activity.defn(name=ClassifyActivity.CALL_LLM.value)
async def call_llm(payload: dict) -> dict:
    data = CallLLMInput(**payload)

    with SessionLocal() as session:
        existing = attempts_q.get_by_ticket_and_attempt(
            session, data.ticket_id, data.attempt_number
        )
        if existing is not None and existing.raw_response is not None:
            activity.logger.info(
                "call_llm cache hit for ticket=%s attempt=%s",
                data.ticket_id,
                data.attempt_number,
            )
            return asdict(CallLLMOutput(raw_response=existing.raw_response))

    with SessionLocal() as session:
        row = session.execute(
            select(Ticket.subject, Ticket.body).where(Ticket.id == data.ticket_id)
        ).one_or_none()
    if row is None:
        raise ApplicationError(f"ticket {data.ticket_id} not found", non_retryable=True)
    subject, body = row

    raw_response = await get_classifier().classify(subject, body)

    with SessionLocal() as session:
        attempts_q.upsert_attempt(
            session,
            ticket_id=data.ticket_id,
            attempt_number=data.attempt_number,
            status=AttemptStatus.SYSTEM_ERROR.value,
            raw_response=raw_response,
        )
        session.commit()

    return asdict(CallLLMOutput(raw_response=raw_response))


@activity.defn(name=ClassifyActivity.VALIDATE_OUTPUT.value)
async def validate_output(payload: dict) -> dict:
    data = ValidateOutputInput(**payload)

    try:
        parsed = json.loads(data.raw_response)
    except json.JSONDecodeError as exc:
        raise _reject(f"not valid JSON: {exc.msg}") from exc

    if not isinstance(parsed, dict):
        raise _reject("response is not a JSON object")

    for key in ("category", "priority", "summary"):
        if key not in parsed:
            raise _reject(f"missing required key: {key}")

    category = parsed["category"]
    priority = parsed["priority"]
    summary = parsed["summary"]

    if category not in _VALID_CATEGORIES:
        raise _reject(f"category out of enum: {category!r}")
    if priority not in _VALID_PRIORITIES:
        raise _reject(f"priority out of enum: {priority!r}")
    if not isinstance(summary, str) or not summary.strip():
        raise _reject("summary must be a non-empty string")
    if len(summary) > MAX_SUMMARY_LENGTH:
        raise _reject(f"summary too long: {len(summary)} > {MAX_SUMMARY_LENGTH}")

    return asdict(
        ParsedClassification(category=category, priority=priority, summary=summary)
    )


@activity.defn(name=ClassifyActivity.PERSIST_RESULT.value)
async def persist_result(payload: dict) -> None:
    data = PersistResultInput(
        ticket_id=payload["ticket_id"],
        parsed=ParsedClassification(**payload["parsed"]),
        attempt_number=payload["attempt_number"],
    )

    with SessionLocal() as session:
        ticket = session.execute(
            select(Ticket).where(Ticket.id == data.ticket_id)
        ).scalar_one_or_none()
        if ticket is None:
            raise ApplicationError(
                f"ticket {data.ticket_id} not found", non_retryable=True
            )

        ticket.status = TicketStatus.CLASSIFIED.value
        ticket.category = data.parsed.category
        ticket.priority = data.parsed.priority
        ticket.summary = data.parsed.summary
        ticket.failure_reason = None

        attempts_q.upsert_attempt(
            session,
            ticket_id=data.ticket_id,
            attempt_number=data.attempt_number,
            status=AttemptStatus.SUCCESS.value,
            parsed_category=data.parsed.category,
            parsed_priority=data.parsed.priority,
            parsed_summary=data.parsed.summary,
        )
        session.commit()


@activity.defn(name=ClassifyActivity.MARK_FAILED.value)
async def mark_failed(payload: dict) -> None:
    data = MarkFailedInput(**payload)

    with SessionLocal() as session:
        ticket = session.execute(
            select(Ticket).where(Ticket.id == data.ticket_id)
        ).scalar_one_or_none()
        if ticket is None:
            raise ApplicationError(
                f"ticket {data.ticket_id} not found", non_retryable=True
            )

        ticket.status = TicketStatus.FAILED.value
        ticket.failure_reason = data.reason

        attempts_q.upsert_attempt(
            session,
            ticket_id=data.ticket_id,
            attempt_number=data.attempt_number,
            status=data.cause,
        )
        session.commit()
