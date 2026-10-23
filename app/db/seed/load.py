import asyncio
import json
import logging
from pathlib import Path

from app.db.queries import tickets as ticket_queries
from app.db.session import SessionLocal
from app.logging import configure_logging
from app.services.temporal_client import start_classification_workflow

SAMPLE_PATH = Path(__file__).parent / "sample_tickets.json"

logger = logging.getLogger(__name__)


async def _ingest(source_id: str, subject: str, body: str) -> str:
    with SessionLocal() as session:
        existing = ticket_queries.get_by_source_id(session, source_id)
        if existing is not None:
            # Workflow start is still safe to call — REJECT_DUPLICATE
            # at the Temporal server dedupes a repeat start under the
            # same workflow id, so this stays idempotent.
            await start_classification_workflow(str(existing.id), source_id)
            return "exists"

        ticket = ticket_queries.insert_pending(
            session, source_id=source_id, subject=subject, body=body
        )
        session.commit()
        ticket_id = str(ticket.id)

    await start_classification_workflow(ticket_id, source_id)
    return "created"


async def main() -> None:
    configure_logging("INFO")
    tickets = json.loads(SAMPLE_PATH.read_text())
    created = exists = 0
    for t in tickets:
        outcome = await _ingest(t["id"], t["subject"], t["body"])
        logger.info("seed: %s -> %s", t["id"], outcome)
        if outcome == "created":
            created += 1
        else:
            exists += 1
    logger.info("seed done: created=%d already_existed=%d", created, exists)


if __name__ == "__main__":
    asyncio.run(main())
