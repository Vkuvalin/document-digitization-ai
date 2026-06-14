from pathlib import Path

import pytest

from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.core import ProviderSchemaMode
from document_digitization_ai.extraction import (
    ExtractionProviderRequestError,
    ExtractionProviderRequest,
    ExtractionProviderResponse,
)
from document_digitization_ai.media import (
    StagedMediaReference,
    StagedMediaReferenceKind,
)
from document_digitization_ai.providers import (
    ProviderDiagnosticsSummary,
    ProviderExtractionRuntimeSettings,
    ProviderImageInput,
    ProviderInputContext,
)


def test_provider_request_references_context_and_optional_staged_media(
    tmp_path: Path,
) -> None:
    context = _provider_context(tmp_path)
    staged_media = StagedMediaReference(
        kind=StagedMediaReferenceKind.LOCAL_FILE,
        value=str(context.image.local_path),
        mime_type=context.image.mime_type,
        file_size_bytes=context.image.file_size_bytes,
        sha256=context.image.sha256,
    )

    request = ExtractionProviderRequest(
        correlation_id="job-001",
        context=context,
        staged_media=staged_media,
        provider_options={"trace": "test"},
    )

    payload = request.to_dict()

    assert request.context is context
    assert request.staged_media is staged_media
    assert payload["correlation_id"] == "job-001"
    assert payload["staged_media"] == staged_media.to_dict()


def test_provider_request_rejects_non_json_options(tmp_path: Path) -> None:
    with pytest.raises(ExtractionProviderRequestError, match="provider_options"):
        ExtractionProviderRequest(
            correlation_id="job-001",
            context=_provider_context(tmp_path),
            provider_options={"not_json": {object()}},
        )


def test_provider_request_rejects_non_finite_options(tmp_path: Path) -> None:
    with pytest.raises(ExtractionProviderRequestError, match="must be finite"):
        ExtractionProviderRequest(
            correlation_id="job-001",
            context=_provider_context(tmp_path),
            provider_options={"temperature": float("nan")},
        )


def test_provider_request_rejects_invalid_prompt_or_schema_package(
    tmp_path: Path,
) -> None:
    with pytest.raises(ExtractionProviderRequestError, match="prompt_package"):
        ExtractionProviderRequest(
            correlation_id="job-001",
            context=_provider_context(tmp_path),
            prompt_package=object(),  # type: ignore[arg-type]
        )

    with pytest.raises(ExtractionProviderRequestError, match="schema_package"):
        ExtractionProviderRequest(
            correlation_id="job-001",
            context=_provider_context(tmp_path),
            schema_package=object(),  # type: ignore[arg-type]
        )


def test_provider_request_rejects_invalid_context(tmp_path: Path) -> None:
    with pytest.raises(ExtractionProviderRequestError, match="context"):
        ExtractionProviderRequest(
            correlation_id="job-001",
            context=object(),  # type: ignore[arg-type]
        )


def test_provider_response_requires_json_compatible_payload() -> None:
    with pytest.raises(ValueError, match="raw_payload"):
        ExtractionProviderResponse(
            provider_name="fake",
            model_name="fake-model-v0",
            raw_payload={"not_json": {object()}},
        )


def test_provider_response_rejects_non_finite_json_payload_and_metadata() -> None:
    with pytest.raises(ValueError, match="raw_payload"):
        ExtractionProviderResponse(
            provider_name="fake",
            model_name="fake-model-v0",
            raw_payload={"score": float("inf")},
        )

    with pytest.raises(ValueError, match="metadata"):
        ExtractionProviderResponse(
            provider_name="fake",
            model_name="fake-model-v0",
            raw_payload={},
            metadata={"duration": float("-inf")},
        )


def _provider_context(tmp_path: Path) -> ProviderInputContext:
    image_path = tmp_path / "original.jpg"
    image_path.write_bytes(b"fake-image-bytes")
    return ProviderInputContext(
        job_id="job-001",
        job_status=JobStatus.IMAGE_DIAGNOSTICS_READY,
        document_mode_hint=DocumentModeHint.AUTO,
        image=ProviderImageInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            width=1000,
            height=800,
            sha256="c" * 64,
        ),
        diagnostics=ProviderDiagnosticsSummary(
            diagnostics_present=True,
            warnings=(),
            is_low_resolution=False,
        ),
        extraction=ProviderExtractionRuntimeSettings(
            model="openai/test-vision",
            temperature=0.1,
            timeout_seconds=60,
            max_retries=2,
            provider_schema_mode=ProviderSchemaMode.COMPACT,
            structured_outputs_enabled=True,
            structured_outputs_require_parameters=False,
        ),
    )
