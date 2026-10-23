"""
Pins the fake's RNG and asserts that:
  - keyword mapping is deterministic
  - the broken-rate knob exposes every validator-tripping failure mode
  - a given seed always produces the same output sequence
"""

import json

import pytest

from app.workflows.classifier.fake import FakeClassifier


def _always_good(seed: int = 1) -> FakeClassifier:
    return FakeClassifier(seed=seed, broken_rate=0.0)


def _always_broken(seed: int = 1) -> FakeClassifier:
    return FakeClassifier(seed=seed, broken_rate=1.0)


async def test_good_response_is_valid_json_with_expected_keys():
    fc = _always_good()
    parsed = json.loads(await fc.classify("Refund request", "please help"))
    assert set(parsed.keys()) == {"category", "priority", "summary"}


@pytest.mark.parametrize(
    "subject, body, expected_category",
    [
        ("Charged twice", "I was billed for subscription", "billing"),
        ("Cannot login", "password doesn't work on account", "account"),
        ("500 error on API", "the backend crashed again", "technical"),
        ("Just saying hi", "nothing specific here", "other"),
    ],
)
async def test_keyword_mapping_is_deterministic(subject, body, expected_category):
    fc = _always_good()
    out = json.loads(await fc.classify(subject, body))
    assert out["category"] == expected_category


async def test_urgency_keyword_bumps_priority_to_high():
    fc = _always_good()
    out = json.loads(await fc.classify("URGENT: refund", "need this immediately"))
    assert out["priority"] == "high"


async def test_broken_rate_exercises_every_failure_mode():
    fc = _always_broken(seed=0)
    kinds_seen = {
        "invalid_json": False,
        "missing_key": False,
        "bad_category": False,
        "bad_priority": False,
        "oversized_summary": False,
    }

    # 200 iterations is enough with 5 modes, each weighted 1/5, to hit
    # every bucket with the pinned seed.
    for _ in range(200):
        raw = await fc.classify("x", "y")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            kinds_seen["invalid_json"] = True
            continue

        if "priority" not in payload or "category" not in payload or "summary" not in payload:
            kinds_seen["missing_key"] = True
        elif payload["category"] not in {"billing", "technical", "account", "other"}:
            kinds_seen["bad_category"] = True
        elif payload["priority"] not in {"low", "medium", "high"}:
            kinds_seen["bad_priority"] = True
        elif len(payload.get("summary", "")) > 300:
            kinds_seen["oversized_summary"] = True

    assert all(kinds_seen.values()), f"never hit: {[k for k, v in kinds_seen.items() if not v]}"


async def test_same_seed_produces_identical_sequence():
    a = FakeClassifier(seed=99)
    b = FakeClassifier(seed=99)
    for _ in range(10):
        assert await a.classify("x", "y") == await b.classify("x", "y")


async def test_broken_rate_zero_never_breaks():
    fc = _always_good()
    for _ in range(50):
        payload = json.loads(await fc.classify("any", "any"))
        assert payload["category"] in {"billing", "technical", "account", "other"}
        assert payload["priority"] in {"low", "medium", "high"}
        assert 0 < len(payload["summary"]) <= 300
