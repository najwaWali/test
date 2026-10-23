import uuid
from datetime import timedelta

import pytest
from temporalio import activity
from temporalio.client import Client
from temporalio.exceptions import ApplicationError
from temporalio.worker import Worker

from app.config import settings
from app.helpers.enums import VALIDATION_ERROR_TYPE, ClassifyActivity
from app.workflows.workflows.classify import ClassifyTicketWorkflow


@pytest.fixture
async def temporal_client():
    client = await Client.connect(
        settings.temporal_address, namespace=settings.temporal_namespace
    )
    yield client


class _Recorder:
    def __init__(self):
        self.calls: dict[str, list] = {name.value: [] for name in ClassifyActivity}


def _happy_mocks(rec: _Recorder, *, status: str = "pending", raw: str | None = None):
    @activity.defn(name=ClassifyActivity.GET_TICKET_STATUS.value)
    async def get_ticket_status(payload: dict) -> dict:
        rec.calls[ClassifyActivity.GET_TICKET_STATUS.value].append(payload)
        return {"status": status}

    @activity.defn(name=ClassifyActivity.CALL_LLM.value)
    async def call_llm(payload: dict) -> dict:
        rec.calls[ClassifyActivity.CALL_LLM.value].append(payload)
        return {
            "raw_response": raw
            or '{"category":"billing","priority":"high","summary":"ok"}'
        }

    @activity.defn(name=ClassifyActivity.VALIDATE_OUTPUT.value)
    async def validate_output(payload: dict) -> dict:
        rec.calls[ClassifyActivity.VALIDATE_OUTPUT.value].append(payload)
        return {"category": "billing", "priority": "high", "summary": "ok"}

    @activity.defn(name=ClassifyActivity.PERSIST_RESULT.value)
    async def persist_result(payload: dict) -> None:
        rec.calls[ClassifyActivity.PERSIST_RESULT.value].append(payload)

    @activity.defn(name=ClassifyActivity.MARK_FAILED.value)
    async def mark_failed(payload: dict) -> None:
        rec.calls[ClassifyActivity.MARK_FAILED.value].append(payload)

    return [get_ticket_status, call_llm, validate_output, persist_result, mark_failed]


def _workflow_input(ticket_id: str) -> dict:
    # Tiny timeouts and single-shot retries keep test runs fast; retries
    # that need to actually happen are overridden per-test.
    return {
        "ticket_id": ticket_id,
        "config": {
            "get_ticket_status": {"timeout_s": 5, "max_attempts": 3},
            "call_llm": {
                "timeout_s": 10,
                "max_attempts": 3,
                "initial_interval_s": 0.1,
                "backoff_coefficient": 1.5,
            },
            "validate_output": {"timeout_s": 5},
            "persist_result": {"timeout_s": 10, "max_attempts": 3},
            "mark_failed": {"timeout_s": 10, "max_attempts": 5},
        },
    }


async def _run(client, activities, ticket_id: str = "ticket-xyz"):
    task_queue = f"test-{uuid.uuid4()}"
    workflow_id = f"test-{uuid.uuid4()}"
    async with Worker(
        client,
        task_queue=task_queue,
        workflows=[ClassifyTicketWorkflow],
        activities=activities,
    ):
        await client.execute_workflow(
            ClassifyTicketWorkflow.run,
            _workflow_input(ticket_id),
            id=workflow_id,
            task_queue=task_queue,
            execution_timeout=timedelta(seconds=30),
        )


async def test_happy_path(temporal_client):
    rec = _Recorder()
    await _run(temporal_client, _happy_mocks(rec))

    persist_calls = rec.calls[ClassifyActivity.PERSIST_RESULT.value]
    assert len(persist_calls) == 1
    assert persist_calls[0]["parsed"]["category"] == "billing"
    assert persist_calls[0]["attempt_number"] == 1
    assert rec.calls[ClassifyActivity.MARK_FAILED.value] == []


async def test_call_llm_retries_then_succeeds(temporal_client):
    rec = _Recorder()
    attempts = {"n": 0}

    @activity.defn(name=ClassifyActivity.CALL_LLM.value)
    async def call_llm(payload: dict) -> dict:
        rec.calls[ClassifyActivity.CALL_LLM.value].append(payload)
        attempts["n"] += 1
        if attempts["n"] < 2:
            raise RuntimeError("transient network blip")
        return {"raw_response": '{"category":"billing","priority":"high","summary":"ok"}'}

    activities = _happy_mocks(rec)
    activities[1] = call_llm

    await _run(temporal_client, activities)

    assert attempts["n"] == 2
    assert len(rec.calls[ClassifyActivity.PERSIST_RESULT.value]) == 1
    assert rec.calls[ClassifyActivity.MARK_FAILED.value] == []


async def test_validation_failure_marks_failed_with_llm_error_cause(temporal_client):
    rec = _Recorder()

    @activity.defn(name=ClassifyActivity.VALIDATE_OUTPUT.value)
    async def validate_output(payload: dict) -> dict:
        rec.calls[ClassifyActivity.VALIDATE_OUTPUT.value].append(payload)
        raise ApplicationError(
            "category out of enum: 'critical'",
            type=VALIDATION_ERROR_TYPE,
            non_retryable=True,
        )

    activities = _happy_mocks(rec)
    activities[2] = validate_output

    await _run(temporal_client, activities)

    assert rec.calls[ClassifyActivity.PERSIST_RESULT.value] == []
    failed_calls = rec.calls[ClassifyActivity.MARK_FAILED.value]
    assert len(failed_calls) == 1
    assert failed_calls[0]["cause"] == "LLM_ERROR"
    assert "category out of enum" in failed_calls[0]["reason"]


async def test_persist_result_retries_then_succeeds(temporal_client):
    rec = _Recorder()
    persist_attempts = {"n": 0}

    @activity.defn(name=ClassifyActivity.PERSIST_RESULT.value)
    async def persist_result(payload: dict) -> None:
        rec.calls[ClassifyActivity.PERSIST_RESULT.value].append(payload)
        persist_attempts["n"] += 1
        if persist_attempts["n"] < 2:
            raise RuntimeError("DB transient")

    activities = _happy_mocks(rec)
    activities[3] = persist_result

    await _run(temporal_client, activities)

    assert persist_attempts["n"] == 2
    assert rec.calls[ClassifyActivity.MARK_FAILED.value] == []


async def test_already_classified_short_circuits(temporal_client):
    rec = _Recorder()
    activities = _happy_mocks(rec, status="classified")

    await _run(temporal_client, activities)

    assert len(rec.calls[ClassifyActivity.GET_TICKET_STATUS.value]) == 1
    assert rec.calls[ClassifyActivity.CALL_LLM.value] == []
    assert rec.calls[ClassifyActivity.VALIDATE_OUTPUT.value] == []
    assert rec.calls[ClassifyActivity.PERSIST_RESULT.value] == []
    assert rec.calls[ClassifyActivity.MARK_FAILED.value] == []


async def test_already_failed_short_circuits(temporal_client):
    rec = _Recorder()
    activities = _happy_mocks(rec, status="failed")

    await _run(temporal_client, activities)

    assert rec.calls[ClassifyActivity.CALL_LLM.value] == []
    assert rec.calls[ClassifyActivity.PERSIST_RESULT.value] == []
    assert rec.calls[ClassifyActivity.MARK_FAILED.value] == []
