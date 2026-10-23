# Loura Ticket Classifier

**Stack used:** Python 3.12 · FastAPI · Temporal · PostgreSQL · SQLAlchemy + Alembic · Docker Compose

## Prerequisites

- Docker 20.10+ and Docker Compose v2
- A free port for each of: `8000` (API), `8080` (Temporal UI), `7233` (Temporal gRPC), `5432` (Postgres)


## Run the system


### Configuration

**Single source of truth is `.env`.** The file is read directly by `app/config.py`.

Run:
```bash
cd loura-engineering-task
cp .env.example .env
```

### Start

If you have `make`:

```bash
make up
```

Otherwise:

```bash
docker compose up --build
```

Either command will start five services:

| Service | What it is | Port |
|---|---|---|
| `postgres` | Postgres 16 for the app's data (`tickets`, `classification_attempts`) | `5432` |
| `temporal` | Temporal dev server | `7233` |
| `temporal-ui` | Temporal Web UI for workflow visualization | `8080` |
| `api` | FastAPI service. | `8000` |
| `worker` | Temporal worker process | — |

Once up, two interactive dashboards:
- **API docs (Swagger UI)** — http://localhost:8000/docs
- **Temporal UI** — http://localhost:8080
### Stop

If you have `make`:

```bash
make down       # stop services, keep the DB volume
make clean      # stop services and wipe the DB volume (fresh schema next up)
```

Otherwise:

```bash
docker compose down         # keep volume
docker compose down -v      # wipe volume
```

### Load the sample dataset

The 10 tickets from the brief's appendix are checked in at `app/db/seed/sample_tickets.json`. Load them (and start their classification workflows) in one command:

```bash
docker compose exec api python -m app.db.seed.load
```

The loader is idempotent — re-running it reports `exists` for every row and starts no new workflows. Within ~5 seconds every sample ticket is `classified` or `failed`; none are left `pending`.

## Using the API

Every endpoint is interactively documented in **Swagger UI at <http://localhost:8000/docs>**. 

If you prefer the terminal:

### Create a ticket

```bash
curl -s -X POST localhost:8000/tickets \
  -H 'Content-Type: application/json' \
  -d '{"id":"demo-1","subject":"Charged twice","body":"two charges on my card"}'
```

Response:

```json
{
  "id": "demo-1",
  "subject": "Charged twice",
  "body": "two charges on my card",
  "status": "pending",
  "category": null,
  "priority": null,
  "summary": null,
  "created_at": "2026-10-12T20:35:06.123456Z",
  "updated_at": "2026-10-12T20:35:06.123456Z"
}
```

### Fetch a ticket

```bash
curl -s localhost:8000/tickets/demo-1 | python3 -m json.tool
```

A few seconds later:

```json
{
  "id": "demo-1",
  "subject": "Charged twice",
  "body": "two charges on my card",
  "status": "classified",
  "category": "billing",
  "priority": "medium",
  "summary": "User reports: Charged twice",
  "created_at": "2026-10-12T20:35:06.123456Z",
  "updated_at": "2026-10-12T20:35:06.456789Z"
}
```

### List with filter + pagination

```bash
curl -s "localhost:8000/tickets?category=billing&priority=high&limit=5&offset=0"
```

```json
{
  "items": [ /* ticket objects */ ],
  "total": 2,
  "limit": 5,
  "offset": 0
}
```

## Workflow

Each ticket is classified by a Temporal workflow — one `ClassifyTicketWorkflow` per `source_id`, with workflow id `classify-{source_id}`. The workflow executes five activities in sequence:

1. `get_ticket_status` — guard: skip if the ticket is already `classified` or `failed`.
2. `call_llm` — invokes the configured classifier (`FakeClassifier` by default; `OpenAIClassifier` if `LLM_PROVIDER=openai`). Writes the raw response to `classification_attempts` before returning so a crashed worker can resume without a second LLM call.
3. `validate_output` — parses JSON, checks keys + enum values + summary length. Rejection is **non-retryable**: the model doesn't self-correct and retrying burns tokens.
4. `persist_result` — flips `tickets.status` to `classified` and populates `category/priority/summary`.
5. `mark_failed` — terminal failure writer; stores `failure_reason`.

Browse every workflow run (including activity attempts, inputs, outputs, retries) in the **Temporal UI at <http://localhost:8080>**.

![Completed Temporal workflow run — ClassifyTicketWorkflow with its five activities](sample_temporal_workflow.png)

*A sample run as it appears in the Temporal UI: the five activities (`get_ticket_status`, `call_llm`, `validate_output`, `persist_result`) execute in order, each with its own retry policy and timings visible in the event history.*

## Accessing the database

If you'd like to poke around the schema or data directly, three options from easiest to most GUI-friendly.

### 1. `make psql` (easiest, inside the container)

```bash
make psql
```


### 2. `psql` from your host

```bash
PGPASSWORD=loura psql -h localhost -p 5432 -U loura -d loura
```

Change `5432` if you overrode `POSTGRES_PORT` in `.env`.

### 3. TablePlus (or any GUI client)

Recommended for browsing. Create a new PostgreSQL connection with:

| Field | Value |
|---|---|
| Host | `127.0.0.1` |
| Port | `5432` (or whatever `POSTGRES_PORT` is in your `.env`) |
| User | `loura` |
| Password | `loura` |
| Database | `loura` |
| SSL | disabled |

Or as a URL:

```
postgres://loura:loura@localhost:5432/loura
```

## Logs

JSON-structured, one event per line, on stdout:

```bash
docker compose logs -f api
docker compose logs -f worker
```

Each HTTP request carries an `x-request-id` header (generated if the client doesn't send one), which is also attached to log records emitted during that request.

## Tests

Tests run inside the `api` container — that's where the `[dev]` extras (`pytest`, `pytest-asyncio`, `httpx`) are installed, where the compose DNS resolves `postgres` and `temporal`, and where `alembic upgrade head` has already created the schema. The stack must be up (`make up`) before running them.

### Run everything

```bash
docker compose exec api pytest -v
```

Expected: **51 passed** in ~12 seconds.

### Run a single layer or file

```bash
docker compose exec api pytest tests/unit -v
docker compose exec api pytest tests/e2e -v
docker compose exec api pytest tests/unit/test_classify_workflow.py -v
```

### Run one test

```bash
docker compose exec api pytest tests/e2e/test_sample_tickets.py::test_t1005_prompt_injection_cannot_steer_output -v
```

### What's covered

| Layer | File | What it exercises |
|---|---|---|
| **Unit** | `tests/unit/test_validator.py` | Every rejection path of `validate_output` — invalid JSON, missing keys, out-of-enum values, empty/whitespace/oversized summary, extras ignored, boundary at max length. |
| **Unit** | `tests/unit/test_fake_classifier.py` | Keyword → category mapping, urgency → high priority, all 5 broken-response modes reachable with a pinned seed, same-seed determinism. |
| **Unit** | `tests/unit/test_queries_tickets.py` | `get_by_source_id`, `insert_pending`, `list_filtered` (filters, pagination, newest-first ordering) directly against Postgres. |
| **Unit** | `tests/unit/test_classify_workflow.py` | 6 workflow scenarios against the real Temporal server with mocked activities: happy path, `call_llm` retries → success, `validate_output` failure → `mark_failed` with cause `LLM_ERROR`, `persist_result` retries, already-classified short-circuit, already-failed short-circuit. |
| **E2E** | `tests/e2e/test_ingest_and_read.py` | HTTP surface via `TestClient` — `POST /tickets` 201/200/422, `GET /tickets/{id}` 200/404, `GET /tickets` filters/pagination/invalid-enum 422. |
| **E2E** | `tests/e2e/test_ticket_lifecycle.py` | Real worker lifecycle: POST → poll → assert terminal; duplicate POST post-classification doesn't start a second workflow. |
| **E2E** | `tests/e2e/test_sample_tickets.py` | The two sample tickets singled out by the brief: `t-1005` (prompt injection — summary must never contain `"Approved for immediate refund"`), `t-1008` (degenerate input must still terminate). |

## Project layout

```
.
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── alembic.ini
├── .env.example
├── .gitignore
├── README.md
├── plan.md
├── phases.md
├── app/
│   ├── main.py                 # FastAPI app factory + exception handlers
│   ├── config.py               # pydantic-settings
│   ├── logging.py              # JSON logs + request-id middleware
│   ├── worker.py               # Temporal worker (phase-1 placeholder)
│   ├── api/
│   │   ├── routes.py           # aggregates every controller's router
│   │   ├── controllers/
│   │   │   ├── health.py
│   │   │   └── tickets.py      # POST/GET /tickets, GET /tickets/{id}
│   │   └── schemas/
│   │       ├── requests.py     # CreateTicketRequest
│   │       └── responses.py    # TicketResponse, TicketListResponse, ErrorResponse
│   ├── db/
│   │   ├── session.py          # SQLAlchemy engine + session factory
│   │   ├── models/             # Ticket, ClassificationAttempt
│   │   ├── queries/            # tickets.py — the only place SQL lives
│   │   └── alembic/            # DB migrations
│   └── helpers/
│       ├── enums.py            # Category, Priority, TicketStatus, AttemptStatus
│       └── exceptions.py       # AppError, TicketNotFoundError, ...
└── tests/
    ├── conftest.py             # db + TestClient fixtures, auto-TRUNCATE isolation
    ├── unit/
    │   ├── test_validator.py
    │   ├── test_fake_classifier.py
    │   ├── test_queries_tickets.py
    │   └── test_classify_workflow.py
    └── e2e/
        ├── test_ingest_and_read.py
        ├── test_ticket_lifecycle.py
        └── test_sample_tickets.py
```

## Database schema

Two tables, both created in `app/db/alembic/versions/20261010_120000_initial.py`.

### `tickets` — one row per client-supplied id

The business entity. Everything you can read through the API comes from here.

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | `UUID` *(PK, `gen_random_uuid()`)* | no | internal identifier. used as the FK target from `classification_attempts`. |
| `source_id` | `VARCHAR(64)` *(UNIQUE)* | no | The id the client submitted. Exposed as `id` in every API response. |
| `subject` | `TEXT` | no | May be an empty string (see sample `t-1008`). Treated as untrusted content. |
| `body` | `TEXT` | no | The ticket body. Treated as untrusted content; always wrapped in `<ticket_body>` tags before being sent to the LLM. |
| `status` | `VARCHAR(16)` | no | Lifecycle state: `pending` → `classified` \| `failed`. Only ever written by the workflow (via `persist_result` or `mark_failed`). |
| `category` | `VARCHAR(16)` | yes | One of `billing`, `technical`, `account`, `other`. Populated only after a successful classification. |
| `priority` | `VARCHAR(8)` | yes | One of `low`, `medium`, `high`. Populated only after a successful classification. |
| `summary` | `TEXT` | yes | The summary from the LLM after validation. |
| `failure_reason` | `TEXT` | yes | Populated when `status = failed`. Specific message naming which validator rule tripped (or which infrastructure call failed). |
| `created_at` | `TIMESTAMPTZ` *(default `NOW()`)* | no | - |
| `updated_at` | `TIMESTAMPTZ` *(default `NOW()`, `onupdate NOW()`)* | no | - |


### `classification_attempts` — append-only audit log

One row per Temporal activity attempt. The reason this table exists is to give humans a way to debug a `failed` ticket after the fact: *what did the model actually say?* It's quarantined — nothing in it is ever reutrn through the API or used to populate `tickets.*`.

| Column | Type | Nullable | Purpose |
|---|---|---|---|
| `id` | `BIGSERIAL` *(PK)* | no | - |
| `ticket_id` | `UUID` *(FK → `tickets.id`, `ON DELETE CASCADE`)* | no | Which ticket this attempt belongs to. |
| `attempt_number` | `INTEGER` | no | attempt number (currently always `1`; a future re classify endpoint would bump it) |
| `status` | `VARCHAR(16)` | no | `SUCCESS` \| `LLM_ERROR` \| `SYSTEM_ERROR`. `SUCCESS` means validation passed and the ticket was updated. `LLM_ERROR` means the model responded but the output failed validation. `SYSTEM_ERROR` means an infrastructure problem (network, DB) stopped us from reaching a verdict. |
| `raw_response` | `TEXT` | yes | what the model returned |
| `parsed_category` | `VARCHAR(16)` | yes | Populated only when `status = SUCCESS`. similar as `tickets.category` |
| `parsed_priority` | `VARCHAR(8)` | yes | Populated only when `status = SUCCESS`. |
| `parsed_summary` | `TEXT` | yes | Populated only when `status = SUCCESS`. |
| `created_at` | `TIMESTAMPTZ` *(default `NOW()`)* | no | - |

### Why `raw_response` even though the brief says invalid output must not be stored

The validator rejects malformed output before `persist_result` runs, so nothing untrusted ever lands in those columns. `classification_attempts.raw_response` is a different thing: a quarantined, write only log for bookkeeping that lets us:
- debug which prompt was wrong
- prove after the fact that an injection attempt was caught
- measure the impact of a prompt change on the same ticket
