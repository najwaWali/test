from dataclasses import dataclass


@dataclass
class ActivityConfig:
    timeout_s: int
    max_attempts: int


@dataclass
class CallLLMConfig:
    timeout_s: int
    max_attempts: int
    initial_interval_s: float
    backoff_coefficient: float


@dataclass
class ValidateOutputConfig:
    timeout_s: int


@dataclass
class ClassifyTicketConfig:
    get_ticket_status: ActivityConfig
    call_llm: CallLLMConfig
    validate_output: ValidateOutputConfig
    persist_result: ActivityConfig
    mark_failed: ActivityConfig


@dataclass
class ClassifyTicketWorkflowInput:
    ticket_id: str
    config: ClassifyTicketConfig

    @classmethod
    def from_dict(cls, payload: dict) -> "ClassifyTicketWorkflowInput":
        cfg = payload["config"]
        return cls(
            ticket_id=payload["ticket_id"],
            config=ClassifyTicketConfig(
                get_ticket_status=ActivityConfig(**cfg["get_ticket_status"]),
                call_llm=CallLLMConfig(**cfg["call_llm"]),
                validate_output=ValidateOutputConfig(**cfg["validate_output"]),
                persist_result=ActivityConfig(**cfg["persist_result"]),
                mark_failed=ActivityConfig(**cfg["mark_failed"]),
            ),
        )
