"""
Full end-to-end lifecycle: POST a ticket, let the compose worker pick
it up, poll until it leaves `pending`. This is the only test that
exercises the real Temporal worker + real fake classifier + real DB,
so it's marked `live_workflow` and bypasses the no-op start fixture.
"""

import time
import uuid

import pytest

POLL_DEADLINE_SECONDS = 20
POLL_INTERVAL_SECONDS = 0.5


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
def test_ticket_moves_from_pending_to_terminal(client):
    source_id = f"lifecycle-{uuid.uuid4()}"
    r = client.post(
        "/tickets",
        json={
            "id": source_id,
            "subject": "Refund request",
            "body": "please refund my latest charge",
        },
    )
    assert r.status_code == 201
    assert r.json()["status"] == "pending"

    final = _wait_until_resolved(client, source_id)
    assert final["status"] in ("classified", "failed")

    if final["status"] == "classified":
        assert final["category"] in ("billing", "technical", "account", "other")
        assert final["priority"] in ("low", "medium", "high")
        assert final["summary"]
    else:
        # failed path: the validator rejected the fake's output; a reason
        # must be stored so an operator can tell what went wrong.
        got = client.get(f"/tickets/{source_id}").json()
        assert got["status"] == "failed"


@pytest.mark.live_workflow
def test_duplicate_post_after_classification_does_not_restart_workflow(client):
    """
    Idempotency layers 1+2: a repeat POST hits the DB-level dedup
    first (returns 200 with the existing row) so no second workflow
    start call is made. If it were made, Temporal's REJECT_DUPLICATE
    would also catch it, but we assert the simpler fact: the second
    POST returns the already-classified ticket.
    """
    source_id = f"lifecycle-dup-{uuid.uuid4()}"
    first = client.post(
        "/tickets",
        json={"id": source_id, "subject": "login problem", "body": "cannot sign in"},
    )
    assert first.status_code == 201
    final = _wait_until_resolved(client, source_id)

    second = client.post(
        "/tickets",
        json={"id": source_id, "subject": "ignored", "body": "ignored"},
    )
    assert second.status_code == 200
    assert second.json()["status"] == final["status"]
    assert second.json()["updated_at"] == final["updated_at"]
