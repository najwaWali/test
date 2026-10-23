"""
Shared fixtures. Tests run against the same Postgres instance the app
uses (via `settings.database_url`), on the assumption that `alembic
upgrade head` has already created the schema — true both inside the
compose network (`docker compose exec api pytest`) and on a host that
booted the stack via `make up`.

Isolation is achieved by TRUNCATE-before-each-test rather than
transactional rollback, so the e2e tests (which go through the real
`SessionLocal`) see the same world the unit tests do.
"""

from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.db.session import SessionLocal, engine
from app.main import create_app


@pytest.fixture(autouse=True)
def _clean_db():
    """
    Truncate app tables before every test. CASCADE handles the FK from
    classification_attempts → tickets. RESTART IDENTITY resets the
    BIGSERIAL on attempts so assertions on attempt ids stay stable.
    """
    with engine.begin() as conn:
        conn.execute(
            text("TRUNCATE tickets, classification_attempts RESTART IDENTITY CASCADE")
        )
    yield


@pytest.fixture(autouse=True)
def _no_workflow_start_by_default(request, monkeypatch):
    """
    Keep ingest-and-read tests fast + deterministic by replacing the
    workflow-start call with a no-op. Tests that want the real worker
    to pick up the ticket opt in with `@pytest.mark.live_workflow`.
    """
    if "live_workflow" in request.keywords:
        return
    monkeypatch.setattr(
        "app.api.controllers.tickets.start_classification_workflow",
        AsyncMock(return_value=None),
    )


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    app = create_app()
    with TestClient(app) as c:
        yield c
