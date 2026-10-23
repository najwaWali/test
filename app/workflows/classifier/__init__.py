from app.config import settings
from app.workflows.classifier.fake import FakeClassifier
from app.workflows.classifier.protocol import Classifier


def get_classifier() -> Classifier:
    provider = settings.llm_provider.lower()
    if provider == "fake":
        return FakeClassifier()
    if provider == "openai":
        if not settings.openai_api_key:
            raise RuntimeError("LLM_PROVIDER=openai but OPENAI_API_KEY is not set")
        from app.workflows.classifier.openai import OpenAIClassifier

        return OpenAIClassifier(
            api_key=settings.openai_api_key, model=settings.openai_model
        )
    raise ValueError(f"unknown LLM_PROVIDER: {settings.llm_provider!r}")
