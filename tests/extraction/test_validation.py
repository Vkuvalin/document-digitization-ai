from pathlib import Path

import pytest

from document_digitization_ai.contracts import (
    BlockType,
    DetectedDocumentType,
    DocumentModeHint,
    ExtractionResult,
    FieldSource,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageQualityIndicators,
    ImageShape,
    JobStatus,
    Warning,
    WarningCode,
    WarningSeverity,
)
from document_digitization_ai.core import ProviderSchemaMode
from document_digitization_ai.extraction import (
    ExtractionProviderResponse,
    ExtractionValidationError,
    ProviderOutputValidationOutcome,
    image_diagnostics_from_payload,
    validate_provider_output,
)
from document_digitization_ai.extraction.fake import default_fake_provider_payload
from document_digitization_ai.providers import (
    ProviderDiagnosticsSummary,
    ProviderExtractionRuntimeSettings,
    ProviderImageInput,
    ProviderInputContext,
)


def test_validate_provider_output_reconstructs_internal_result(
    tmp_path: Path,
) -> None:
    context = _provider_context(tmp_path, DocumentModeHint.FORM)
    image_diagnostics = _image_diagnostics()
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload=default_fake_provider_payload(),
    )

    validation = validate_provider_output(
        response,
        context=context,
        image_diagnostics=image_diagnostics,
    )

    assert validation.outcome is ProviderOutputValidationOutcome.SUCCEEDED
    assert isinstance(validation.extraction_result, ExtractionResult)
    assert validation.extraction_result.document.user_mode_hint is DocumentModeHint.FORM
    assert validation.extraction_result.document.detected_type is DetectedDocumentType.UNKNOWN
    assert validation.extraction_result.image_diagnostics is image_diagnostics
    assert validation.extraction_result.raw_text.text == "Deterministic fake extracted text."
    assert validation.extraction_result.metadata.provider == "fake"
    assert validation.extraction_result.metadata.model == "fake-model-v0"
    assert "raw_payload" not in validation.extraction_result.to_dict()
    assert validation.provider_response is response


def test_validate_provider_output_defaults_missing_optional_sections_as_partial(
    tmp_path: Path,
) -> None:
    context = _provider_context(tmp_path, DocumentModeHint.TABLE)
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload={"raw_text": {"text": "Only text was returned."}},
    )

    validation = validate_provider_output(
        response,
        context=context,
        image_diagnostics=_image_diagnostics(),
    )

    assert validation.outcome is ProviderOutputValidationOutcome.PARTIAL
    assert validation.extraction_result.document.user_mode_hint is DocumentModeHint.TABLE
    assert validation.extraction_result.fields == ()
    assert validation.extraction_result.tables == ()
    assert validation.extraction_result.blocks == ()
    assert [warning.target for warning in validation.validation_warnings] == ["document"]


@pytest.mark.parametrize("raw_payload", [[], "not-json-object", None])
def test_validate_provider_output_rejects_non_object_payload(
    tmp_path: Path,
    raw_payload: object,
) -> None:
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload=raw_payload,
    )

    with pytest.raises(ExtractionValidationError, match="raw_payload"):
        validate_provider_output(
            response,
            context=_provider_context(tmp_path),
            image_diagnostics=_image_diagnostics(),
        )


def test_validate_provider_output_rejects_unusable_empty_result(
    tmp_path: Path,
) -> None:
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload={},
    )

    with pytest.raises(ExtractionValidationError, match="usable extraction content"):
        validate_provider_output(
            response,
            context=_provider_context(tmp_path),
            image_diagnostics=_image_diagnostics(),
        )


def test_validate_provider_output_rejects_warning_only_result(
    tmp_path: Path,
) -> None:
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload={
            "warnings": [
                {
                    "code": "partial_extraction",
                    "message": "Provider returned no readable content.",
                    "severity": "warning",
                }
            ]
        },
    )

    with pytest.raises(ExtractionValidationError, match="usable extraction content"):
        validate_provider_output(
            response,
            context=_provider_context(tmp_path),
            image_diagnostics=_image_diagnostics(),
        )


def test_validate_provider_output_normalizes_table_row_mismatches(
    tmp_path: Path,
) -> None:
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload={
            "document": {"detected_type": "table"},
            "raw_text": {"text": "A B\n1\n2 3 4"},
            "tables": [
                {
                    "title": "Detected table",
                    "columns": ["A", "B"],
                    "rows": [
                        {"cells": ["1"]},
                        {"cells": ["2", "3", "4"]},
                    ],
                }
            ],
        },
    )

    validation = validate_provider_output(
        response,
        context=_provider_context(tmp_path),
        image_diagnostics=_image_diagnostics(),
    )

    table = validation.extraction_result.tables[0]
    assert validation.outcome is ProviderOutputValidationOutcome.PARTIAL
    assert table.rows[0].cells == ("1", "")
    assert table.rows[1].cells == ("2", "3")
    assert any(
        warning.target == "tables[0].rows[0].cells"
        and "fewer cells" in warning.message
        for warning in validation.validation_warnings
    )
    assert any(
        warning.target == "tables[0].rows[1].cells"
        and "more cells" in warning.message
        for warning in validation.validation_warnings
    )


def test_validate_provider_output_skips_malformed_items_and_preserves_valid_items(
    tmp_path: Path,
) -> None:
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload={
            "document": {
                "detected_type": "plain_text",
                "detected_type_confidence": 2,
            },
            "raw_text": {
                "text": "Name: Ada",
                "warnings": "bad warnings shape",
            },
            "fields": [
                {"label": "", "value": "skip"},
                {"label": "Name", "value": 123, "source": "detected"},
            ],
            "blocks": [
                {"type": "heading", "text": "Name", "order": -1},
                {"type": "paragraph", "text": "", "order": 1},
            ],
            "warnings": [
                {
                    "code": "partial_extraction",
                    "message": "Provider returned a partial result.",
                    "severity": "warning",
                },
                {"code": "partial_extraction"},
            ],
        },
    )

    validation = validate_provider_output(
        response,
        context=_provider_context(tmp_path),
        image_diagnostics=_image_diagnostics(),
    )

    assert validation.outcome is ProviderOutputValidationOutcome.PARTIAL
    assert validation.extraction_result.fields[0].label == "Name"
    assert validation.extraction_result.fields[0].value == ""
    assert validation.extraction_result.fields[0].source is FieldSource.DETECTED
    assert validation.extraction_result.blocks[0].type is BlockType.HEADING
    assert validation.extraction_result.blocks[0].order == 0
    assert any(
        warning.code is WarningCode.PARTIAL_EXTRACTION
        for warning in validation.extraction_result.warnings
    )
    assert any(
        warning.target == "raw_text.warnings"
        for warning in validation.validation_warnings
    )


def test_validate_provider_output_ignores_hallucinated_top_level_state(
    tmp_path: Path,
) -> None:
    response = ExtractionProviderResponse(
        provider_name="fake",
        model_name="fake-model-v0",
        raw_payload={
            "document": {"detected_type": "form", "user_mode_hint": "table"},
            "raw_text": {"text": "Trusted context wins."},
            "image_diagnostics": {"file": {"mime_type": "text/plain"}},
            "metadata": {"schema_version": "provider_owned_schema"},
        },
    )

    validation = validate_provider_output(
        response,
        context=_provider_context(tmp_path, DocumentModeHint.FREE_HANDWRITTEN_TEXT),
        image_diagnostics=_image_diagnostics(),
    )

    assert validation.outcome is ProviderOutputValidationOutcome.PARTIAL
    assert (
        validation.extraction_result.document.user_mode_hint
        is DocumentModeHint.FREE_HANDWRITTEN_TEXT
    )
    assert validation.extraction_result.document.detected_type is DetectedDocumentType.FORM
    assert any(
        warning.target == "provider_payload"
        for warning in validation.validation_warnings
    )
    assert any(
        warning.target == "metadata.schema_version"
        for warning in validation.validation_warnings
    )


def test_image_diagnostics_from_payload_reconstructs_backend_diagnostics() -> None:
    diagnostics = _image_diagnostics()

    reconstructed = image_diagnostics_from_payload(diagnostics.to_dict())

    assert reconstructed == diagnostics


def test_image_diagnostics_from_payload_rejects_malformed_backend_payload() -> None:
    with pytest.raises(ExtractionValidationError, match="file.mime_type"):
        image_diagnostics_from_payload(
            {
                "file": {"mime_type": "", "file_size_bytes": 128, "file_extension": ".jpg"},
                "image": {"width": 1200, "height": 800},
            }
        )


def _provider_context(
    tmp_path: Path,
    document_mode_hint: DocumentModeHint = DocumentModeHint.AUTO,
) -> ProviderInputContext:
    image_path = tmp_path / "original.jpg"
    image_path.write_bytes(b"fake-image-bytes")
    return ProviderInputContext(
        job_id="job-001",
        job_status=JobStatus.IMAGE_DIAGNOSTICS_READY,
        document_mode_hint=document_mode_hint,
        image=ProviderImageInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            width=1200,
            height=800,
            sha256="b" * 64,
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


def _image_diagnostics() -> ImageDiagnostics:
    return ImageDiagnostics(
        file=ImageFileMetadata(
            mime_type="image/jpeg",
            file_size_bytes=128,
            file_extension=".jpg",
            sha256="b" * 64,
        ),
        image=ImageShape.from_dimensions(width=1200, height=800, format="JPEG"),
        quality=ImageQualityIndicators(
            blur_score=0.1,
            sharpness_score=0.9,
            brightness=90.0,
            contrast=45.0,
            is_low_resolution=False,
            is_probably_blurry=False,
            is_low_contrast=False,
        ),
        warnings=(
            Warning(
                code=WarningCode.LOW_CONTRAST,
                message="Контраст изображения снижен.",
                severity=WarningSeverity.WARNING,
            ),
        ),
    )
