from enum import StrEnum


class Category(StrEnum):
    BILLING = "billing"
    TECHNICAL = "technical"
    ACCOUNT = "account"
    OTHER = "other"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class TicketStatus(StrEnum):
    PENDING = "pending"
    CLASSIFIED = "classified"
    FAILED = "failed"


class AttemptStatus(StrEnum):
    SUCCESS = "SUCCESS"
    LLM_ERROR = "LLM_ERROR"
    SYSTEM_ERROR = "SYSTEM_ERROR"


class ClassifyActivity(StrEnum):
    GET_TICKET_STATUS = "get_ticket_status"
    CALL_LLM = "call_llm"
    VALIDATE_OUTPUT = "validate_output"
    PERSIST_RESULT = "persist_result"
    MARK_FAILED = "mark_failed"


VALIDATION_ERROR_TYPE = "ValidationError"
