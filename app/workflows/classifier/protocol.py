from typing import Protocol


class Classifier(Protocol):
    async def classify(self, subject: str, body: str) -> str: ...
