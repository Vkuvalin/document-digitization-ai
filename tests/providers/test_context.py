from pathlib import Path
from typing import cast

import pytest

from document_digitization_ai.contracts import (
    DocumentModeHint,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageQualityIndicators,
    ImageShape,
    JobStatus,
    Warning,
    WarningCode,
)
from document_digitization_ai.core import ExtractionSettings, ProviderSchemaMode
from document_digitization_ai.db import DocumentJob
from document_digitization_ai.providers import (
    ProviderInputContextLifecycleError,
    ProviderInputContextSettingsError,
    ProviderInputContextStateError,
    attach_staged_media,
    build_provider_input_context,
)


def test_build_provider_input_context_from_intake_completed_job(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    job = _build_ready_job(image_path)

    context = build_provider_input_context(job, _extraction_settings())

    assert context.job_id == "job-001"
    assert context.job_status is JobStatus.IMAGE_DIAGNOSTICS_READY
    assert context.document_mode_hint is DocumentModeHint.FORM
    assert context.image.local_path == image_path
    assert context.image.mime_type == "image/jpeg"
    assert context.image.file_size_bytes == image_path.stat().st_size
    assert context.image.width == 1600
    assert context.image.height == 2200
    assert context.image.sha256 == "a" * 64
    assert context.diagnostics.diagnostics_present is True
    assert [warning.code for warning in context.diagnostics.warnings] == [
        WarningCode.LOW_CONTRAST.value
    ]
    assert context.diagnostics.contrast == 12.5
    assert context.extraction.model == "openai/test-vision"
    assert context.extraction.temperature == 0.2
    assert context.extraction.timeout_seconds == 45
    assert context.extraction.max_retries == 1
    assert context.extraction.provider_name.value == "fake"
    assert context.extraction.provider_schema_mode is ProviderSchemaMode.FULL


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.CREATED,
        JobStatus.IMAGE_UPLOADED,
        JobStatus.FAILED,
    ],
)
def test_build_provider_input_context_rejects_invalid_lifecycle_status(
    tmp_path: Path,
    status: JobStatus,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    job = _build_ready_job(image_path)
    job.status = status

    with pytest.raises(ProviderInputContextLifecycleError):
        build_provider_input_context(job, _extraction_settings())


@pytest.mark.parametrize(
    ("field_name", "field_value", "error_match"),
    [
        ("source_image_path", None, "source_image_path"),
        ("source_image_mime_type", None, "source_image_mime_type"),
        ("source_image_size_bytes", None, "source_image_size_bytes"),
        ("image_diagnostics_payload", None, "image_diagnostics_payload"),
    ],
)
def test_build_provider_input_context_rejects_missing_required_job_state(
    tmp_path: Path,
    field_name: str,
    field_value: object,
    error_match: str,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    job = _build_ready_job(image_path)
    setattr(job, field_name, field_value)

    with pytest.raises(ProviderInputContextStateError, match=error_match):
        build_provider_input_context(job, _extraction_settings())


def test_build_provider_input_context_rejects_badly_typed_image_size(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    job = _build_ready_job(image_path)
    job.source_image_size_bytes = cast(int, "128")

    with pytest.raises(ProviderInputContextStateError, match="source_image_size_bytes"):
        build_provider_input_context(job, _extraction_settings())


def test_build_provider_input_context_rejects_missing_source_image_file(
    tmp_path: Path,
) -> None:
    job = _build_ready_job(tmp_path / "missing.jpg")

    with pytest.raises(ProviderInputContextStateError, match="does not exist"):
        build_provider_input_context(job, _extraction_settings())


def test_build_provider_input_context_rejects_source_image_directory(
    tmp_path: Path,
) -> None:
    directory = tmp_path / "image-dir"
    directory.mkdir()
    job = _build_ready_job(directory)

    with pytest.raises(ProviderInputContextStateError, match="must point to a file"):
        build_provider_input_context(job, _extraction_settings())


def test_build_provider_input_context_rejects_placeholder_model(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    job = _build_ready_job(image_path)

    with pytest.raises(ProviderInputContextSettingsError, match="OPENROUTER_MODEL"):
        build_provider_input_context(job, ExtractionSettings())


def test_build_provider_input_context_rejects_invalid_schema_mode(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    job = _build_ready_job(image_path)
    settings = ExtractionSettings.model_construct(
        model="openai/test-vision",
        temperature=0.1,
        timeout_seconds=60,
        max_retries=2,
        structured_outputs_enabled=True,
        structured_outputs_require_parameters=False,
        provider_schema_mode=cast(ProviderSchemaMode, "strict"),
    )

    with pytest.raises(ProviderInputContextSettingsError, match="provider_schema_mode"):
        build_provider_input_context(job, settings)


def test_build_provider_input_context_does_not_require_provider_or_media_secrets(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    job = _build_ready_job(image_path)

    context = build_provider_input_context(job, _extraction_settings())

    assert context.extraction.model == "openai/test-vision"


def test_attach_staged_media_rejects_object_without_to_dict(tmp_path: Path) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    context = build_provider_input_context(
        _build_ready_job(image_path),
        _extraction_settings(),
    )

    with pytest.raises(ProviderInputContextStateError, match="staged_media"):
        attach_staged_media(context, object())  # type: ignore[arg-type]


def _build_ready_job(image_path: Path) -> DocumentJob:
    return DocumentJob(
        id="job-001",
        status=JobStatus.IMAGE_DIAGNOSTICS_READY,
        user_mode_hint=DocumentModeHint.FORM,
        source_image_path=str(image_path),
        source_image_mime_type="image/jpeg",
        source_image_size_bytes=image_path.stat().st_size if image_path.is_file() else 128,
        image_diagnostics_payload=_build_image_diagnostics().to_dict(),
    )


def _build_image_diagnostics() -> ImageDiagnostics:
    return ImageDiagnostics(
        file=ImageFileMetadata(
            mime_type="image/jpeg",
            file_size_bytes=128,
            file_extension=".jpg",
            sha256="a" * 64,
        ),
        image=ImageShape.from_dimensions(width=1600, height=2200, format="JPEG"),
        quality=ImageQualityIndicators(
            contrast=12.5,
            brightness=44.0,
            is_low_resolution=False,
            is_low_contrast=True,
        ),
        warnings=(
            Warning(
                code=WarningCode.LOW_CONTRAST,
                message="Контраст изображения снижен.",
            ),
        ),
    )


def _extraction_settings() -> ExtractionSettings:
    return ExtractionSettings(
        model="openai/test-vision",
        temperature=0.2,
        timeout_seconds=45,
        max_retries=1,
        provider_schema_mode=ProviderSchemaMode.FULL,
    )


def _write_image_bytes(path: Path) -> Path:
    path.write_bytes(b"fake-image-bytes")
    return path
