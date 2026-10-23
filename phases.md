# Implementation Phases

Four phases. Each one ends in a **runnable, demoable, commit-ready** state — not a half-built intermediate. If you had to stop at the end of any phase, the service would still boot and do what it claims.

**Guiding principle:** vertical slices. Each phase delivers a complete capability, however small. We don't build an entire layer across the whole system before moving on — we build the thinnest possible version of each layer, then thicken.

| Phase | Goal | What runs at the end |
|---|---|---|
| **1** | Foundation | `docker compose up` → Postgres + Temporal + FastAPI; `/health` is green |
| **2** | Ingest + Read API | `POST /tickets` and `GET /tickets` work end-to-end; tickets stay `pending` |
| **3** | Classification pipeline | Tickets move `pending → classified | failed` via Temporal + fake LLM |
| **4** | Polish, seed, tests, README | 10 sample tickets classified; all tests pass; submission-ready |

---

## Phase 1 — Foundation

**Goal:** everything required to run the service exists, boots, and connects to its dependencies. No business logic yet.

### Deliverables

- `pyproject.toml` with deps (fastapi, uvicorn, sqlalchemy, psycopg, alembic, pydantic-settings, temporalio, pytest, httpx, ruff).
- `Dockerfile` — single image, two entrypoints (api, worker).
- `docker-compose.yml` — services: `postgres`, `temporal`, `temporal-ui`, `api`, `worker`.
- `.env.example`, `.gitignore` (excludes `.env`).
- `alembic.ini` + `app/db/alembic/env.py` + `0001_initial.py` migration creating `tickets` and `classification_attempts` with all columns, constraints, indexes.
- `app/db/session.py` — SQLAlchemy engine + session factory.
- `app/db/models/{ticket,classification_attempt}.py` — ORM.
- `app/helpers/enums.py` — `Category`, `Priority`, `TicketStatus`, `AttemptStatus`.
- `app/helpers/exceptions.py` — `ValidationError`, `LLMError`, `SystemError`.
- `app/config.py` — pydantic-settings loader.
- `app/logging.py` — JSON formatter + request-id middleware.
- `app/main.py` — FastAPI app factory, registers `/health`.
- `app/api/controllers/health.py` — `/health` endpoint that opens a DB session and pings Temporal.

### Done when

- [ ] `docker compose up --build` starts all five containers without errors.
- [ ] `curl localhost:8000/health` returns `200 {"ok": true, "db": "ok", "temporal": "ok"}`.
- [ ] `docker compose exec api alembic current` shows the initial revision applied.
- [ ] `docker compose exec postgres psql -U loura -d loura -c "\d tickets"` and `\d classification_attempts` print the expected columns.
- [ ] Temporal UI loads at `localhost:8080`.
- [ ] `ruff check .` passes.

### Not in this phase

Any route besides `/health`. Any workflow or activity. Any classifier code.

---

## Phase 2 — Ingest + Read API

**Goal:** tickets can be created and queried over HTTP. They stay in `pending` because there's no workflow yet; that's fine and visible.

### Deliverables

- `app/db/queries/tickets.py` — `get_by_source_id`, `insert_pending`, `list_filtered`.
- `app/api/schemas/requests.py` — `CreateTicketRequest`, `ListTicketsQuery` (with enum validation on `category`/`priority`).
- `app/api/schemas/responses.py` — `TicketResponse`, `TicketListResponse`, `ErrorResponse`.
- `app/api/controllers/tickets.py`:
  - `POST /tickets` — insert if new, return 201; return 200 with existing on duplicate `source_id`. Workflow start is a TODO stub (`# TODO phase 3`).
  - `GET /tickets/{id}` — lookup by `source_id`, 404 on miss.
  - `GET /tickets` — filter by `category`/`priority`, offset/limit pagination.
- Exception handlers in `app/main.py` producing `{"detail": "...", "code": "..."}`.
- `tests/unit/test_queries_tickets.py` — covers each query function against a real test DB.
- `tests/e2e/test_ingest_and_read.py`:
  - POST a new ticket → 201, `status=pending`.
  - POST the same `id` again → 200, same ticket returned, only one row in DB.
  - GET by id → 200.
  - GET nonexistent → 404 with `code=ticket_not_found`.
  - GET list with filters, with pagination, with invalid enum → 422.

### Done when

- [ ] All deliverables above are present.
- [ ] `pytest tests/` is green.
- [ ] Manual sanity: `curl -X POST localhost:8000/tickets -d '{"id":"t-1","subject":"hi","body":"hello"}' -H 'Content-Type: application/json'` returns 201; repeating returns 200.
- [ ] `psql ... -c "SELECT count(*) FROM tickets WHERE source_id='t-1'"` returns 1 after a duplicate POST.

### Not in this phase

No workflow, no activities, no classifier. Tickets stay `pending` forever — the brief's `pending → classified | failed` lifecycle lands in Phase 3.

---

## Phase 3 — Classification pipeline

**Goal:** the full brief. Tickets flow `pending → classified | failed` through a Temporal workflow, the LLM boundary is handled with care, and all three idempotency layers are in place.

### Deliverables

- `app/db/queries/attempts.py` — `upsert_attempt`, `latest_for_ticket`.
- `app/workflows/classifier/protocol.py` — `Classifier` Protocol.
- `app/workflows/classifier/fake.py` — `FakeClassifier`: deterministic keyword-based mapping, ~15% of the time emits one of {invalid JSON, missing key, out-of-enum category, out-of-enum priority, oversized summary} to exercise the validator. RNG seedable for tests.
- `app/workflows/schemas/activity_io.py` — dataclasses for activity inputs/outputs.
- `app/workflows/activities/get_ticket_status.py`.
- `app/workflows/activities/call_llm.py` — attempt-row cache: read `(ticket_id, attempt_number)` first; call LLM only if no prior raw response; UPSERT raw response with pessimistic `status=SYSTEM_ERROR` before returning.
- `app/workflows/activities/validate_output.py` — raises `ValidationError` on bad JSON, missing keys, out-of-enum values, summary length violations.
- `app/workflows/activities/persist_result.py` — `UPDATE tickets SET status='classified', ...`; set attempt row to `SUCCESS`.
- `app/workflows/activities/mark_failed.py` — `UPDATE tickets SET status='failed', failure_reason=...`; set latest attempt row to `LLM_ERROR` or `SYSTEM_ERROR`.
- `app/workflows/workflows/classify.py` — `ClassifyTicketWorkflow` with status-check prelude, retry policies per activity, catches `ActivityError` → `mark_failed`.
- `app/worker.py` — Temporal worker registering workflows and activities, `max_concurrent_activity_task_executions=10`.
- `app/services/temporal_client.py` *(or inline in controller)* — thin `start_workflow` wrapper with `WorkflowIDReusePolicy.REJECT_DUPLICATE` and workflow ID `classify-{source_id}`.
- Wire the Phase 2 TODO: `POST /tickets` now starts the workflow after inserting the row.
- `tests/unit/test_validator.py` — every failure mode of the validator.
- `tests/unit/test_fake_classifier.py` — pins the RNG seed, asserts both good and broken outputs occur.
- `tests/unit/test_classify_workflow.py` — uses `temporalio.testing.WorkflowEnvironment` with mocked activities:
  - happy path
  - transient `call_llm` failure → retry → success
  - `validate_output` failure → `mark_failed` → ticket `failed`
  - DB failure during `persist_result` → retry → success
  - already-classified ticket → workflow returns without running activities

### Done when

- [ ] All deliverables above are present.
- [ ] `pytest tests/` is green including workflow tests.
- [ ] Manual lifecycle: POST a ticket, poll `GET /tickets/{id}` — within a few seconds `status` transitions to `classified` (most tickets) or `failed` (when the fake emits a broken response).
- [ ] Temporal UI shows the workflow run and its activity attempts.
- [ ] `SELECT ticket_id, attempt_number, status FROM classification_attempts` shows one row per attempt with the right status enum.
- [ ] Duplicate `POST /tickets` with same `source_id` after classification does **not** start a second workflow (check Temporal UI: still only one run).

### Not in this phase

OpenAI classifier, seed script, full prompt-injection test cases, README.

---

## Phase 4 — Polish, seed, tests, README

**Goal:** submission-ready. The sample dataset loads, the real-LLM path exists even if unused, every brief requirement is traceable to code or README text.

### Deliverables

- `app/workflows/classifier/openai.py` — `OpenAIClassifier` loaded only when `LLM_PROVIDER=openai` and `OPENAI_API_KEY` is set. Uses the Chat Completions API with `response_format={"type": "json_object"}`.
- `app/db/seed/sample_tickets.json` — the 10 tickets from the PDF appendix verbatim.
- `app/db/seed/load.py` — reads the JSON and calls the same `create_ticket_and_start_workflow` code path as the API. Idempotent: re-running does not create duplicates.
- Add a dedicated test case for `t-1005` (prompt injection): classify it, assert the ticket ends either `failed` with a validation reason **or** `classified` with a category/priority in the enum (never with the injected `summary='Approved for immediate refund'` text). This is the single test that proves the "model is untrusted" claim.
- Add a dedicated test case for `t-1008` (empty-ish body `"asdf"`): assert the workflow completes (either `classified other/low` or `failed` — document which).
- Full e2e lifecycle test: `tests/e2e/test_ticket_lifecycle.py` — POST → poll → assert final status. Covers one happy path and one forced-failure path (pinned fake RNG seed).
- `README.md`:
  - **Run it** — one-paragraph "clone, `cp .env.example .env`, `docker compose up`, `docker compose exec api python -m app.db.seed.load`."
  - **Decisions on the open questions** — storage, async execution, concurrency, restart behavior, retry policy, prompt-injection stance, API shape. One short paragraph each.
  - **What I'd change with more time** — reclassify endpoint, cursor pagination, evaluation harness, auth.
  - **Known weaknesses** — enums in code not DB, offline fake isn't a real accuracy benchmark, no auth, no cancel signal.
  - **Where to look first** — the file list from `plan.md` section 12.

### Done when

- [ ] Fresh clone, `cp .env.example .env`, `docker compose up --build` boots clean.
- [ ] `docker compose exec api python -m app.db.seed.load` inserts all 10 sample tickets and starts 10 workflows.
- [ ] After ~15 seconds, every sample ticket has `status ∈ {classified, failed}` (none left `pending`).
- [ ] `t-1005` has either `status=failed` or `status=classified` with a non-injected summary.
- [ ] `pytest tests/` is green across unit and e2e.
- [ ] `ruff check .` passes.
- [ ] README answers every "open question" from the brief in its own paragraph.
- [ ] `OPENAI_API_KEY` is not in any committed file (`git grep -i 'sk-' | wc -l` returns 0).

### Not in this phase

Any of the explicit bonus features (reclassify endpoint, evaluation script, graceful-shutdown signal). Mentioned in README as "would do next."

---

## How to execute a phase

1. Branch: `phase-N-<slug>`.
2. Deliverables in any order — vertical slices preferred over "all queries, then all controllers."
3. Keep the service runnable at every commit. If a change breaks `docker compose up`, land the fix in the same commit.
4. Check the "Done when" list before opening a PR. Every box must be ticked.
5. Merge to `main`. Phase N+1 starts from `main`.

## Rough time allocation (within the 4–6h budget)

| Phase | Target |
|---|---|
| 1 | 60 min |
| 2 | 75 min |
| 3 | 120 min |
| 4 | 60 min |

Buffer: 30–45 min for the inevitable Docker/Temporal weirdness. If a phase overruns, cut from Phase 4's README polish before cutting from Phase 3's workflow tests — the workflow tests are what the reviewer actually reads.
