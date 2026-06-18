from __future__ import annotations

from dataclasses import dataclass, field

from document_digitization_ai.extraction.provider import (
    ExtractionProviderRequest,
    ExtractionProviderResponse,
    FakeExtractionProviderError,
    validate_provider_request,
)


def default_fake_provider_payload() -> dict[str, object]:
    return {
        "provider_payload_version": "fake_extraction_provider_v0",
        "document": {
            "detected_type": "unknown",
            "summary": "Deterministic fake provider payload.",
        },
        "raw_text": {
            "text": "Deterministic fake extracted text.",
            "confidence": 1.0,
        },
        "fields": [],
        "tables": [],
        "blocks": [],
        "warnings": [],
        "metadata": {
            "is_fake_provider_payload": True,
        },
    }


@dataclass(frozen=True, slots=True)
class FakeExtractionProvider:
    provider_name: str = "fake"
    model_name: str = "fake-model-v0"
    raw_payload: object = field(default_factory=default_fake_provider_payload)
    raw_text: str = "Deterministic fake extracted text."
    fail_with_message: str | None = None

    async def extract(
        self,
        request: ExtractionProviderRequest,
    ) -> ExtractionProviderResponse:
        validate_provider_request(request)
        if self.fail_with_message is not None:
            raise FakeExtractionProviderError(self.fail_with_message)

        metadata = {
            "correlation_id": request.correlation_id,
            "job_id": request.context.job_id,
            "staged_media_kind": (
                request.staged_media.kind.value
                if request.staged_media is not None
                else None
            ),
        }
        return ExtractionProviderResponse(
            provider_name=self.provider_name,
            model_name=self.model_name,
            raw_payload=self.raw_payload,
            raw_text=self.raw_text,
            finish_reason="fake_complete",
            metadata=metadata,
            raw_response_json={
                "provider": self.provider_name,
                "model": self.model_name,
                "finish_reason": "fake_complete",
                "payload": self.raw_payload,
                "metadata": metadata,
            },
        )
