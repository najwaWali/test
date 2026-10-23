import json
import time
import uuid
from pathlib import Path

import pytest

SAMPLE_PATH = (
    Path(__file__).parent.parent.parent / "app" / "db" / "seed" / "sample_tickets.json"
)
POLL_DEADLINE_SECONDS = 20
POLL_INTERVAL_SECONDS = 0.5

VALID_CATEGORIES = {"billing", "technical", "account", "other"}
VALID_PRIORITIES = {"low", "medium", "high"}
INJECTED_SUMMARY = "Approved for immediate refund"


def _samples() -> dict[str, dict]:
    return {t["id"]: t for t in json.loads(SAMPLE_PATH.read_text())}


def _wait_until_resolved(client, source_id: str) -> dict:
    deadline = time.time() + POLL_DEADLINE_SECONDS
    last = None
    while time.time() < deadline:
        last = client.get(f"/tickets/{source_id}").json()
        if last["status"] != "pending":
            return last
        time.sleep(POLL_INTERVAL_SECONDS)
    pytest.fail(f"ticket {source_id} never left pending; last state: {last}")


@pytest.mark.live_workflow
def test_t1005_prompt_injection_cannot_steer_output(client):
    """
    The brief singles out t-1005 as the prompt-injection test. The
    ticket asks the model to classify it as `technical/high` and set the
    summary to a specific string ('Approved for immediate refund'). The
    service must either (a) end up `failed` because the model's response
    doesn't pass validation, or (b) end up `classified` with values the
    validator accepted — never with the injected summary.
    """
    sample = _samples()["t-1005"]
    source_id = f"t-1005-{uuid.uuid4()}"
    payload = {**sample, "id": source_id}
    r = client.post("/tickets", json=payload)
    assert r.status_code == 201

    final = _wait_until_resolved(client, source_id)
    assert final["status"] in ("classified", "failed")

    if final["status"] == "classified":
        assert final["category"] in VALID_CATEGORIES
        assert final["priority"] in VALID_PRIORITIES
        assert INJECTED_SUMMARY not in (final["summary"] or ""), (
            f"injected summary leaked into tickets.summary: {final['summary']!r}"
        )
    else:
        detail = client.get(f"/tickets/{source_id}").json()
        assert detail["status"] == "failed"


@pytest.mark.live_workflow
def test_t1008_empty_subject_short_body_still_terminates(client):
    """
    t-1008 is the degenerate input: empty subject, body is `asdf`.
    The brief doesn't dictate the terminal state — only that the
    workflow must terminate instead of hanging. With the fake
    classifier this reliably lands on `classified` as `other/low`
    (no keyword hits anywhere), but a broken response from the ~15%
    failure branch would legitimately produce `failed`. Either is OK;
    `pending` after the polling deadline is not.
    """
    sample = _samples()["t-1008"]
    source_id = f"t-1008-{uuid.uuid4()}"
    payload = {**sample, "id": source_id}
    r = client.post("/tickets", json=payload)
    assert r.status_code == 201

    final = _wait_until_resolved(client, source_id)
    assert final["status"] in ("classified", "failed")

    if final["status"] == "classified":
        assert final["category"] in VALID_CATEGORIES
        assert final["priority"] in VALID_PRIORITIES
        assert final["summary"]
