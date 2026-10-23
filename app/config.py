"""
Values are read from, in precedence order:
  1. Process environment variables.
  2. The .env file at the current working directory
     (= /app/.env inside the container, mounted from the host's .env).
  3. The field defaults defined below.

The defaults are container-friendly (hostnames resolve to compose services),
so a fresh clone with no .env file works out of the box.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+psycopg://loura:loura@postgres:5432/loura"

    # Temporal
    temporal_address: str = "temporal:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "ticket-classification"

    # LLM
    llm_provider: str = "fake"
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"

    # App
    log_level: str = "INFO"
    max_concurrent_activities: int = 10

    # ------------------------------------------------------------------
    # Workflow / activity tuning
    # ------------------------------------------------------------------
    # Each activity has its own policy because each has its own failure
    # mode. These are read by workflow code in Phase 3 to build
    # Temporal RetryPolicy objects.

    # Workflow run-level timeout (total wall clock a workflow may consume)
    workflow_run_timeout_seconds: int = 300

    # get_ticket_status activity — workflow-entry guard, read-only DB
    get_ticket_status_timeout_seconds: int = 5
    get_ticket_status_max_attempts: int = 3

    # call_llm activity — the expensive one; retries on transient errors only
    call_llm_timeout_seconds: int = 30
    call_llm_max_attempts: int = 3
    call_llm_initial_interval_seconds: float = 1.0
    call_llm_backoff_coefficient: float = 2.0

    # validate_output activity — pure function; non-retryable on failure
    validate_output_timeout_seconds: int = 5

    # persist_result activity — DB write on success path
    persist_result_timeout_seconds: int = 10
    persist_result_max_attempts: int = 3

    # mark_failed activity — DB write on failure path; critical to land
    mark_failed_timeout_seconds: int = 10
    mark_failed_max_attempts: int = 5

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


settings = Settings()
