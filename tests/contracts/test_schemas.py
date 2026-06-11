from typing import cast

import pytest

from document_digitization_ai.contracts import (
    BlockType,
    DetectedDocumentType,
    DocumentInfo,
    DocumentModeHint,
    ExpectedResultSection,
    ExtractedField,
    ExtractedTable,
    ExtractionResult,
    FieldSource,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageQualityIndicators,
    ImageShape,
    JobStatus,
    ProviderConstraint,
    ProviderImageReference,
    ProviderInputContext,
    ProviderJobContext,
    ProviderUserRequest,
    RawText,
    TableRow,
    TextBlock,
    Warning,
    WarningCode,
    WarningSeverity,
)


def test_image_shape_derives_aspect_ratio_and_orientation() -> None:
    image = ImageShape.from_dimensions(width=1600, height=2200, format="JPEG")

    assert image.aspect_ratio == pytest.approx(1600 / 2200)
    assert image.orientation.value == "portrait"
    assert image.to_dict()["format"] == "JPEG"


def test_extraction_result_serializes_approved_top_level_shape() -> None:
    result = ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            detected_type_confidence=0.86,
            language="ru",
            summary="Анкета с рукописными значениями.",
        ),
        image_diagnostics=_build_image_diagnostics(),
        raw_text=RawText(text="Имя: Анна\nСумма: 1200", confidence=0.73),
        fields=(
            ExtractedField(
                label="Имя",
                value="Анна",
                confidence=0.91,
                source=FieldSource.DETECTED,
            ),
        ),
        tables=(
            ExtractedTable(
                title="Позиции",
                columns=("Название", "Сумма"),
                rows=(TableRow(cells=("Услуга", "1200"), confidence=0.77),),
            ),
        ),
        blocks=(
            TextBlock(
                type=BlockType.PARAGRAPH,
                text="Имя: Анна",
                order=0,
                confidence=0.8,
            ),
        ),
        warnings=(
            Warning(
                code=WarningCode.LOW_CONTRAST,
                message="Контраст изображения снижен.",
            ),
        ),
    )

    payload = result.to_dict()

    assert list(payload) == [
        "document",
        "image_diagnostics",
        "raw_text",
        "fields",
        "tables",
        "blocks",
        "warnings",
        "metadata",
    ]
    document = cast(dict[str, object], payload["document"])
    raw_text = cast(dict[str, object], payload["raw_text"])
    fields = cast(list[dict[str, object]], payload["fields"])
    tables = cast(list[dict[str, object]], payload["tables"])
    warnings = cast(list[dict[str, object]], payload["warnings"])

    assert document["user_mode_hint"] == "form"
    assert document["detected_type"] == "form"
    assert raw_text["text"] == "Имя: Анна\nСумма: 1200"
    assert fields[0]["source"] == "detected"
    assert tables[0]["columns"] == ["Название", "Сумма"]
    assert warnings[0]["code"] == "low_contrast"


def test_provider_input_context_serializes_expected_shape_and_constraints() -> None:
    context = ProviderInputContext(
        job=ProviderJobContext(
            job_id="job-001",
            processing_stage=JobStatus.IMAGE_DIAGNOSTICS_READY,
        ),
        user_request=ProviderUserRequest(user_mode_hint=DocumentModeHint.AUTO),
        image=ProviderImageReference(
            image_id="image-001",
            provider_image_reference="provider-placeholder://image-001",
            mime_type="image/jpeg",
            width=1600,
            height=2200,
            file_size_bytes=245_000,
        ),
        image_diagnostics=_build_image_diagnostics(),
    )

    payload = context.to_dict()
    expected_result_shape = cast(list[str], payload["expected_result_shape"])
    constraints = cast(list[str], payload["constraints"])
    diagnostics = cast(dict[str, object], payload["image_diagnostics"])
    diagnostic_warnings = cast(list[dict[str, object]], diagnostics["warnings"])

    assert expected_result_shape == [section.value for section in ExpectedResultSection]
    assert ProviderConstraint.DO_NOT_INVENT_UNREADABLE_TEXT.value in constraints
    assert ProviderConstraint.RETURN_VALID_STRUCTURED_OUTPUT.value in constraints
    assert diagnostic_warnings[0]["code"] == "possible_skew"


def test_confidence_validation_rejects_values_outside_unit_interval() -> None:
    with pytest.raises(ValueError, match="detected_type_confidence"):
        DocumentInfo(
            user_mode_hint=DocumentModeHint.TABLE,
            detected_type_confidence=1.01,
        )


def test_table_validation_requires_columns_and_cells() -> None:
    with pytest.raises(ValueError, match="columns"):
        ExtractedTable(columns=(), rows=())

    with pytest.raises(ValueError, match="cells"):
        TableRow(cells=())


def test_image_diagnostics_validation_rejects_invalid_dimensions() -> None:
    with pytest.raises(ValueError, match="width"):
        ImageShape.from_dimensions(width=0, height=200)


def test_image_shape_validation_rejects_inconsistent_aspect_ratio() -> None:
    with pytest.raises(ValueError, match="aspect_ratio"):
        ImageShape(
            width=100,
            height=200,
            aspect_ratio=1.0,
            orientation=ImageShape.from_dimensions(width=100, height=200).orientation,
        )


def test_warning_validation_rejects_non_enum_code() -> None:
    with pytest.raises(ValueError, match="code"):
        Warning(
            code=cast(WarningCode, "low_contrast"),
            message="Контраст изображения снижен.",
        )


def _build_image_diagnostics() -> ImageDiagnostics:
    return ImageDiagnostics(
        file=ImageFileMetadata(
            mime_type="image/jpeg",
            file_size_bytes=245_000,
            file_extension=".jpg",
            sha256="d" * 64,
        ),
        image=ImageShape.from_dimensions(
            width=1600,
            height=2200,
            color_mode="RGB",
            format="JPEG",
        ),
        quality=ImageQualityIndicators(
            contrast=0.42,
            is_low_contrast=True,
            is_probably_blurry=False,
        ),
        warnings=(
            Warning(
                code=WarningCode.POSSIBLE_SKEW,
                message="Возможен небольшой перекос изображения.",
                severity=WarningSeverity.INFO,
            ),
        ),
    )
