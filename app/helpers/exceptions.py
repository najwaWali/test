class AppError(Exception):
    """Base for all application-level exceptions."""


class ValidationError(AppError):
    """Model output failed shape or allowlist validation. Non-retryable."""


class LLMError(AppError):
    """LLM returned an output the validator rejected."""


class SystemError(AppError):
    """Infrastructure problem (DB, network, provider 5xx). Retryable."""


class TicketNotFoundError(AppError):
    """No ticket with the given source_id exists."""
