import asyncio
import logging

from temporalio.client import Client
from temporalio.worker import Worker

from app.config import settings
from app.logging import configure_logging
from app.workflows.activities import (
    call_llm,
    get_ticket_status,
    mark_failed,
    persist_result,
    validate_output,
)
from app.workflows.workflows.classify import ClassifyTicketWorkflow

logger = logging.getLogger(__name__)


async def main() -> None:
    configure_logging(settings.log_level)
    client = await Client.connect(
        settings.temporal_address, namespace=settings.temporal_namespace
    )

    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[ClassifyTicketWorkflow],
        activities=[
            get_ticket_status,
            call_llm,
            validate_output,
            persist_result,
            mark_failed,
        ],
        max_concurrent_activities=settings.max_concurrent_activities,
    )
    logger.info(
        "worker ready: task_queue=%s max_concurrent_activities=%d",
        settings.temporal_task_queue,
        settings.max_concurrent_activities,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
