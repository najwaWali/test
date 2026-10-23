from dataclasses import dataclass


@dataclass
class CallLLMInput:
    ticket_id: str
    attempt_number: int


@dataclass
class CallLLMOutput:
    raw_response: str


@dataclass
class ValidateOutputInput:
    raw_response: str


@dataclass
class ParsedClassification:
    category: str
    priority: str
    summary: str


@dataclass
class PersistResultInput:
    ticket_id: str
    parsed: ParsedClassification
    attempt_number: int


@dataclass
class MarkFailedInput:
    ticket_id: str
    reason: str
    cause: str
    attempt_number: int
