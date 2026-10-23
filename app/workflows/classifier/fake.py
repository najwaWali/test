import json
import random

BROKEN_RATE_DEFAULT = 0.15

_BILLING_KW = ("charge", "refund", "bill", "invoice", "payment", "subscription", "price")
_ACCOUNT_KW = ("login", "password", "account", "sign in", "sign-in", "2fa", "mfa", "lock")
_TECHNICAL_KW = ("error", "bug", "crash", "500", "exception", "broken", "slow", "fail", "api")
_HIGH_KW = ("urgent", "immediately", "asap", "critical", "down", "outage", "losing")


class FakeClassifier:
    def __init__(self, seed: int | None = None, broken_rate: float = BROKEN_RATE_DEFAULT):
        self._rng = random.Random(seed)
        self._broken_rate = broken_rate

    async def classify(self, subject: str, body: str) -> str:
        if self._rng.random() < self._broken_rate:
            return self._broken_response()
        return self._good_response(subject, body)

    def _good_response(self, subject: str, body: str) -> str:
        text = f"{subject} {body}".lower()

        if any(kw in text for kw in _BILLING_KW):
            category = "billing"
        elif any(kw in text for kw in _ACCOUNT_KW):
            category = "account"
        elif any(kw in text for kw in _TECHNICAL_KW):
            category = "technical"
        else:
            category = "other"

        if any(kw in text for kw in _HIGH_KW):
            priority = "high"
        elif category in ("technical", "billing"):
            priority = "medium"
        else:
            priority = "low"

        anchor = subject.strip() or (body.strip()[:80] if body.strip() else "ticket")
        summary = f"User reports: {anchor[:200]}"

        return json.dumps({"category": category, "priority": priority, "summary": summary})

    def _broken_response(self) -> str:
        kind = self._rng.choice(
            ("invalid_json", "missing_key", "bad_category", "bad_priority", "oversized")
        )
        if kind == "invalid_json":
            return "{category: billing, priority: high, summary: not valid JSON}"
        if kind == "missing_key":
            return json.dumps({"category": "billing", "summary": "no priority"})
        if kind == "bad_category":
            return json.dumps(
                {"category": "finance", "priority": "high", "summary": "out-of-enum category"}
            )
        if kind == "bad_priority":
            return json.dumps(
                {"category": "billing", "priority": "critical", "summary": "out-of-enum priority"}
            )
        return json.dumps(
            {"category": "billing", "priority": "high", "summary": "x" * 350}
        )
