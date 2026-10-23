import asyncio

from temporalio.client import Client
from temporalio.common import WorkflowIDReusePolicy
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.service import RPCError, RPCStatusCode

from app.config import settings
from app.workflows.workflows.classify import ClassifyTicketWorkflow

_client: Client | None = None
_client_lock = asyncio.Lock()


async def get_client() -> Client:
    global _client
    if _client is not None:
        return _client
    async with _client_lock:
        if _client is None:
            _client = await Client.connect(
                settings.temporal_address, namespace=settings.temporal_namespace
            )
        return _client


def _build_workflow_input(ticket_id: str) -> dict:
    return {
        "ticket_id": ticket_id,
        "config": {
            "get_ticket_status": {
                "timeout_s": settings.get_ticket_status_timeout_seconds,
                "max_attempts": settings.get_ticket_status_max_attempts,
            },
            "call_llm": {
                "timeout_s": settings.call_llm_timeout_seconds,
                "max_attempts": settings.call_llm_max_attempts,
                "initial_interval_s": settings.call_llm_initial_interval_seconds,
                "backoff_coefficient": settings.call_llm_backoff_coefficient,
            },
            "validate_output": {
                "timeout_s": settings.validate_output_timeout_seconds,
            },
            "persist_result": {
                "timeout_s": settings.persist_result_timeout_seconds,
                "max_attempts": settings.persist_result_max_attempts,
            },
            "mark_failed": {
                "timeout_s": settings.mark_failed_timeout_seconds,
                "max_attempts": settings.mark_failed_max_attempts,
            },
        },
    }


async def start_classification_workflow(ticket_id: str, source_id: str) -> None:
    client = await get_client()
    try:
        await client.start_workflow(
            ClassifyTicketWorkflow.run,
            _build_workflow_input(ticket_id),
            id=f"classify-{source_id}",
            task_queue=settings.temporal_task_queue,
            id_reuse_policy=WorkflowIDReusePolicy.REJECT_DUPLICATE,
        )
    except WorkflowAlreadyStartedError:
        return
    except RPCError as exc:
        if exc.status == RPCStatusCode.ALREADY_EXISTS:
            return
        raise
