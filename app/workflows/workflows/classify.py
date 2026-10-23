from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ActivityError

from app.helpers.enums import (
    VALIDATION_ERROR_TYPE,
    AttemptStatus,
    ClassifyActivity,
    TicketStatus,
)
from app.workflows.schemas.workflow_io import ClassifyTicketWorkflowInput


def _reason_from(exc: ActivityError) -> str:
    cause = getattr(exc, "cause", None)
    return str(cause) if cause is not None else str(exc)


@workflow.defn
class ClassifyTicketWorkflow:
    @workflow.run
    async def run(self, payload: dict) -> None:
        data = ClassifyTicketWorkflowInput.from_dict(payload)
        cfg = data.config

        guard = await workflow.execute_activity(
            ClassifyActivity.GET_TICKET_STATUS.value,
            args=[{"ticket_id": data.ticket_id}],
            start_to_close_timeout=timedelta(seconds=cfg.get_ticket_status.timeout_s),
            retry_policy=RetryPolicy(maximum_attempts=cfg.get_ticket_status.max_attempts),
            result_type=dict,
        )
        if guard["status"] in (TicketStatus.CLASSIFIED.value, TicketStatus.FAILED.value):
            workflow.logger.info(
                "classify: ticket %s already %s — skipping",
                data.ticket_id,
                guard["status"],
            )
            return

        attempt_number = 1
        cause = AttemptStatus.SYSTEM_ERROR.value
        reason = ""

        try:
            llm = await workflow.execute_activity(
                ClassifyActivity.CALL_LLM.value,
                args=[{"ticket_id": data.ticket_id, "attempt_number": attempt_number}],
                start_to_close_timeout=timedelta(seconds=cfg.call_llm.timeout_s),
                retry_policy=RetryPolicy(
                    maximum_attempts=cfg.call_llm.max_attempts,
                    initial_interval=timedelta(seconds=cfg.call_llm.initial_interval_s),
                    backoff_coefficient=cfg.call_llm.backoff_coefficient,
                ),
                result_type=dict,
            )

            try:
                parsed = await workflow.execute_activity(
                    ClassifyActivity.VALIDATE_OUTPUT.value,
                    args=[{"raw_response": llm["raw_response"]}],
                    start_to_close_timeout=timedelta(seconds=cfg.validate_output.timeout_s),
                    retry_policy=RetryPolicy(
                        maximum_attempts=1,
                        non_retryable_error_types=[VALIDATION_ERROR_TYPE],
                    ),
                    result_type=dict,
                )
            except ActivityError as exc:
                cause = AttemptStatus.LLM_ERROR.value
                reason = _reason_from(exc)
                raise

            await workflow.execute_activity(
                ClassifyActivity.PERSIST_RESULT.value,
                args=[
                    {
                        "ticket_id": data.ticket_id,
                        "parsed": parsed,
                        "attempt_number": attempt_number,
                    }
                ],
                start_to_close_timeout=timedelta(seconds=cfg.persist_result.timeout_s),
                retry_policy=RetryPolicy(maximum_attempts=cfg.persist_result.max_attempts),
            )
        except ActivityError as exc:
            if not reason:
                reason = _reason_from(exc)
            await workflow.execute_activity(
                ClassifyActivity.MARK_FAILED.value,
                args=[
                    {
                        "ticket_id": data.ticket_id,
                        "reason": reason,
                        "cause": cause,
                        "attempt_number": attempt_number,
                    }
                ],
                start_to_close_timeout=timedelta(seconds=cfg.mark_failed.timeout_s),
                retry_policy=RetryPolicy(maximum_attempts=cfg.mark_failed.max_attempts),
            )
