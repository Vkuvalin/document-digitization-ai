from pathlib import Path

import pytest
from pydantic import SecretStr

from document_digitization_ai.contracts import (
    DocumentModeHint,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageQualityIndicators,
    ImageShape,
    JobStatus,
)
from document_digitization_ai.core import (
    ExtractionSettings,
    MediaStagingBackend,
    MediaStagingSettings,
)
from document_digitization_ai.db import DocumentJob
from document_digitization_ai.media import (
    LocalNoopMediaStagingService,
    MediaStagingError,
    MediaStagingInput,
    MediaStagingResult,
    StagedMediaReference,
    StagedMediaReferenceKind,
    UnsupportedMediaStagingBackendError,
    build_media_staging_service,
)
from document_digitization_ai.providers import (
    attach_staged_media,
    build_provider_input_context,
)


@pytest.mark.asyncio
async def test_local_noop_staging_returns_local_file_reference(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    service = LocalNoopMediaStagingService()

    result = await service.stage(
        MediaStagingInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            sha256="b" * 64,
        )
    )

    assert result.reference.kind is StagedMediaReferenceKind.LOCAL_FILE
    assert result.reference.value == str(image_path)
    assert result.reference.mime_type == "image/jpeg"
    assert result.reference.file_size_bytes == image_path.stat().st_size
    assert result.reference.sha256 == "b" * 64
    assert result.external_upload_performed is False


@pytest.mark.asyncio
async def test_local_noop_staging_rejects_missing_file(tmp_path: Path) -> None:
    service = LocalNoopMediaStagingService()

    with pytest.raises(MediaStagingError, match="does not exist"):
        await service.stage(
            MediaStagingInput(
                local_path=tmp_path / "missing.jpg",
                mime_type="image/jpeg",
                file_size_bytes=128,
            )
        )


@pytest.mark.asyncio
async def test_local_noop_staging_rejects_directory(tmp_path: Path) -> None:
    directory = tmp_path / "image-dir"
    directory.mkdir()
    service = LocalNoopMediaStagingService()

    with pytest.raises(MediaStagingError, match="must point to a file"):
        await service.stage(
            MediaStagingInput(
                local_path=directory,
                mime_type="image/jpeg",
                file_size_bytes=128,
            )
        )


def test_media_staging_factory_returns_local_noop_for_safe_default() -> None:
    service = build_media_staging_service(MediaStagingSettings())

    assert isinstance(service, LocalNoopMediaStagingService)


def test_media_staging_factory_rejects_unimplemented_imgbb_without_secret() -> None:
    settings = MediaStagingSettings(backend=MediaStagingBackend.IMGBB)

    with pytest.raises(UnsupportedMediaStagingBackendError, match="imgbb"):
        build_media_staging_service(settings)


def test_media_staging_factory_rejects_unimplemented_imgbb_with_key_like_secret() -> None:
    settings = MediaStagingSettings(
        backend=MediaStagingBackend.IMGBB,
        imgbb_api_key=SecretStr("imgbb-key-like-value"),
    )

    with pytest.raises(UnsupportedMediaStagingBackendError, match="imgbb"):
        build_media_staging_service(settings)


@pytest.mark.asyncio
async def test_provider_context_can_carry_staged_media_reference(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    context = build_provider_input_context(
        _build_ready_job(image_path),
        ExtractionSettings(model="openai/test-vision"),
    )
    service = LocalNoopMediaStagingService()

    staging_result = await service.stage(
        MediaStagingInput(
            local_path=context.image.local_path,
            mime_type=context.image.mime_type,
            file_size_bytes=context.image.file_size_bytes,
            sha256=context.image.sha256,
        )
    )
    context_with_media = attach_staged_media(context, staging_result.reference)

    assert context.staged_media is None
    assert context_with_media.staged_media is staging_result.reference
    assert context_with_media.to_dict()["staged_media"] == staging_result.reference.to_dict()


def test_media_staging_input_validates_positive_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file_size_bytes"):
        MediaStagingInput(
            local_path=tmp_path / "original.jpg",
            mime_type="image/jpeg",
            file_size_bytes=0,
        )


def test_media_staging_input_rejects_non_integer_size(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="file_size_bytes"):
        MediaStagingInput(
            local_path=tmp_path / "original.jpg",
            mime_type="image/jpeg",
            file_size_bytes="128",  # type: ignore[arg-type]
        )


def test_media_staging_metadata_must_be_json_compatible(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="metadata"):
        MediaStagingInput(
            local_path=tmp_path / "original.jpg",
            mime_type="image/jpeg",
            file_size_bytes=128,
            metadata={"bad": {object()}},
        )


def test_media_staging_result_validates_external_upload_flag(tmp_path: Path) -> None:
    reference = StagedMediaReference(
        kind=StagedMediaReferenceKind.LOCAL_FILE,
        value=str(tmp_path / "original.jpg"),
        mime_type="image/jpeg",
        file_size_bytes=128,
    )

    with pytest.raises(ValueError, match="external_upload_performed"):
        MediaStagingResult(
            reference=reference,
            external_upload_performed=1,  # type: ignore[arg-type]
        )


def _build_ready_job(image_path: Path) -> DocumentJob:
    return DocumentJob(
        id="job-001",
        status=JobStatus.IMAGE_DIAGNOSTICS_READY,
        user_mode_hint=DocumentModeHint.FORM,
        source_image_path=str(image_path),
        source_image_mime_type="image/jpeg",
        source_image_size_bytes=image_path.stat().st_size,
        image_diagnostics_payload=_build_image_diagnostics().to_dict(),
    )


def _build_image_diagnostics() -> ImageDiagnostics:
    return ImageDiagnostics(
        file=ImageFileMetadata(
            mime_type="image/jpeg",
            file_size_bytes=128,
            file_extension=".jpg",
            sha256="b" * 64,
        ),
        image=ImageShape.from_dimensions(width=1200, height=900, format="JPEG"),
        quality=ImageQualityIndicators(is_low_resolution=False),
    )


def _write_image_bytes(path: Path) -> Path:
    path.write_bytes(b"fake-image-bytes")
    return path
