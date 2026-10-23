import json

import pytest
from temporalio.exceptions import ApplicationError

from app.helpers.enums import VALIDATION_ERROR_TYPE
from app.workflows.activities.classify_activities import (
    MAX_SUMMARY_LENGTH,
    validate_output,
)


def _call(**fields):
    return {"raw_response": json.dumps(fields)}


async def test_valid_payload_returns_parsed_dict():
    out = await validate_output(
        _call(category="billing", priority="high", summary="legit summary")
    )
    assert out == {
        "category": "billing",
        "priority": "high",
        "summary": "legit summary",
    }


async def test_invalid_json_rejected():
    with pytest.raises(ApplicationError) as excinfo:
        await validate_output({"raw_response": "{not: valid json"})
    assert excinfo.value.type == VALIDATION_ERROR_TYPE
    assert excinfo.value.non_retryable
    assert "not valid JSON" in str(excinfo.value)


async def test_response_not_a_dict_rejected():
    with pytest.raises(ApplicationError, match="not a JSON object"):
        await validate_output({"raw_response": json.dumps(["billing", "high", "x"])})


@pytest.mark.parametrize(
    "missing_key, payload",
    [
        ("category", {"priority": "high", "summary": "ok"}),
        ("priority", {"category": "billing", "summary": "ok"}),
        ("summary", {"category": "billing", "priority": "high"}),
    ],
)
async def test_missing_key_rejected(missing_key, payload):
    with pytest.raises(ApplicationError, match=f"missing required key: {missing_key}"):
        await validate_output({"raw_response": json.dumps(payload)})


async def test_out_of_enum_category_rejected():
    with pytest.raises(ApplicationError, match="category out of enum"):
        await validate_output(_call(category="finance", priority="high", summary="s"))


async def test_out_of_enum_priority_rejected():
    with pytest.raises(ApplicationError, match="priority out of enum"):
        await validate_output(_call(category="billing", priority="critical", summary="s"))


async def test_empty_summary_rejected():
    with pytest.raises(ApplicationError, match="non-empty string"):
        await validate_output(_call(category="billing", priority="high", summary=""))


async def test_whitespace_only_summary_rejected():
    with pytest.raises(ApplicationError, match="non-empty string"):
        await validate_output(_call(category="billing", priority="high", summary="   "))


async def test_oversized_summary_rejected():
    oversize = "x" * (MAX_SUMMARY_LENGTH + 1)
    with pytest.raises(ApplicationError, match="summary too long"):
        await validate_output(_call(category="billing", priority="high", summary=oversize))


async def test_extra_keys_are_ignored():
    out = await validate_output(
        _call(category="billing", priority="high", summary="ok", unexpected=42)
    )
    assert out["category"] == "billing"
    assert out["priority"] == "high"


async def test_summary_at_max_length_accepted():
    s = "x" * MAX_SUMMARY_LENGTH
    out = await validate_output(_call(category="billing", priority="high", summary=s))
    assert out["summary"] == s
