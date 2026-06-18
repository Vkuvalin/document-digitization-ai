from pathlib import Path

import pytest

from document_digitization_ai.contracts import (
    DocumentModeHint,
    ExtractionResult,
    JobStatus,
)
from document_digitization_ai.core import ProviderSchemaMode
from document_digitization_ai.extraction import (
    ExtractionProviderRequest,
    FakeExtractionProvider,
    FakeExtractionProviderError,
)
from document_digitization_ai.media import StagedMediaReference, StagedMediaReferenceKind
from document_digitization_ai.providers import (
    ProviderDiagnosticsSummary,
    ProviderExtractionRuntimeSettings,
    ProviderImageInput,
    ProviderInputContext,
)


@pytest.mark.asyncio
async def test_fake_provider_returns_deterministic_response(tmp_path: Path) -> None:
    provider = FakeExtractionProvider()
    request = ExtractionProviderRequest(
        correlation_id="job-001",
        context=_provider_context(tmp_path),
    )

    first = await provider.extract(request)
    second = await provider.extract(request)

    assert first == second
    assert first.provider_name == "fake"
    assert first.model_name == "fake-model-v0"
    assert first.raw_text == "Deterministic fake extracted text."
    assert first.raw_payload == second.raw_payload
    assert first.raw_response_json is not None
    assert first.metadata["correlation_id"] == "job-001"
    assert not isinstance(first, ExtractionResult)


@pytest.mark.asyncio
async def test_fake_provider_can_raise_typed_provider_error(tmp_path: Path) -> None:
    provider = FakeExtractionProvider(fail_with_message="configured failure")
    request = ExtractionProviderRequest(
        correlation_id="job-001",
        context=_provider_context(tmp_path),
    )

    with pytest.raises(FakeExtractionProviderError, match="configured failure"):
        await provider.extract(request)


@pytest.mark.asyncio
async def test_fake_provider_accepts_request_with_staged_media(
    tmp_path: Path,
) -> None:
    context = _provider_context(tmp_path)
    staged_media = StagedMediaReference(
        kind=StagedMediaReferenceKind.LOCAL_FILE,
        value=str(context.image.local_path),
        mime_type=context.image.mime_type,
        file_size_bytes=context.image.file_size_bytes,
    )
    request = ExtractionProviderRequest(
        correlation_id="job-001",
        context=context,
        staged_media=staged_media,
    )

    response = await FakeExtractionProvider().extract(request)

    assert response.metadata["staged_media_kind"] == StagedMediaReferenceKind.LOCAL_FILE.value


def test_fake_provider_does_not_require_provider_or_media_secrets() -> None:
    provider = FakeExtractionProvider()

    assert provider.provider_name == "fake"
    assert provider.model_name == "fake-model-v0"


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
