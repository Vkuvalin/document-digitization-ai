from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from math import isclose, isfinite

from document_digitization_ai.contracts.enums import (
    BlockType,
    DetectedDocumentType,
    DocumentModeHint,
    ExpectedResultSection,
    ExtractionGoal,
    FieldSource,
    ImageOrientation,
    JobStatus,
    ProviderConstraint,
    WarningCode,
    WarningSeverity,
)


EXTRACTION_RESULT_SCHEMA_VERSION = "extraction_result_v0"
IMAGE_DIAGNOSTICS_SCHEMA_VERSION = "image_diagnostics_v0"

DEFAULT_EXPECTED_RESULT_SHAPE: tuple[ExpectedResultSection, ...] = (
    ExpectedResultSection.DOCUMENT,
    ExpectedResultSection.IMAGE_DIAGNOSTICS,
    ExpectedResultSection.RAW_TEXT,
    ExpectedResultSection.FIELDS,
    ExpectedResultSection.TABLES,
    ExpectedResultSection.BLOCKS,
    ExpectedResultSection.WARNINGS,
    ExpectedResultSection.METADATA,
)

DEFAULT_PROVIDER_CONSTRAINTS: tuple[ProviderConstraint, ...] = (
    ProviderConstraint.DO_NOT_INVENT_UNREADABLE_TEXT,
    ProviderConstraint.MARK_UNCERTAIN_VALUES_EXPLICITLY,
    ProviderConstraint.PRESERVE_VISIBLE_TABLE_STRUCTURE,
    ProviderConstraint.RETURN_MODE_MISMATCH_WARNING,
    ProviderConstraint.RETURN_PARTIAL_RESULT_WITH_WARNINGS,
    ProviderConstraint.DO_NOT_SILENTLY_CLEAN_UP_HANDWRITING,
    ProviderConstraint.RETURN_VALID_STRUCTURED_OUTPUT,
)


def infer_image_orientation(width: int, height: int) -> ImageOrientation:
    _ensure_positive_int(width, "width")
    _ensure_positive_int(height, "height")

    if width > height:
        return ImageOrientation.LANDSCAPE
    if height > width:
        return ImageOrientation.PORTRAIT
    return ImageOrientation.SQUARE


def image_aspect_ratio(width: int, height: int) -> float:
    _ensure_positive_int(width, "width")
    _ensure_positive_int(height, "height")
    return width / height


@dataclass(frozen=True, slots=True)
class Warning:
    code: WarningCode
    message: str
    severity: WarningSeverity = WarningSeverity.WARNING
    target: str | None = None

    def __post_init__(self) -> None:
        _ensure_enum_member(self.code, WarningCode, "code")
        _ensure_enum_member(self.severity, WarningSeverity, "severity")
        _ensure_non_empty_text(self.message, "message")
        _ensure_optional_non_empty_text(self.target, "target")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code.value,
            "message": self.message,
            "severity": self.severity.value,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class ImageFileMetadata:
    mime_type: str
    file_size_bytes: int
    file_extension: str
    sha256: str | None = None

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.mime_type, "mime_type")
        _ensure_positive_int(self.file_size_bytes, "file_size_bytes")
        _ensure_non_empty_text(self.file_extension, "file_extension")
        _ensure_optional_non_empty_text(self.sha256, "sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "mime_type": self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "file_extension": self.file_extension,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ImageShape:
    width: int
    height: int
    aspect_ratio: float
    orientation: ImageOrientation
    exif_orientation: int | None = None
    color_mode: str | None = None
    format: str | None = None

    def __post_init__(self) -> None:
        _ensure_positive_int(self.width, "width")
        _ensure_positive_int(self.height, "height")
        _ensure_enum_member(self.orientation, ImageOrientation, "orientation")
        _ensure_positive_float(self.aspect_ratio, "aspect_ratio")
        expected_aspect_ratio = image_aspect_ratio(self.width, self.height)
        if not isclose(self.aspect_ratio, expected_aspect_ratio):
            msg = "aspect_ratio must match width / height"
            raise ValueError(msg)
        _ensure_optional_positive_int(self.exif_orientation, "exif_orientation")
        _ensure_optional_non_empty_text(self.color_mode, "color_mode")
        _ensure_optional_non_empty_text(self.format, "format")

    @classmethod
    def from_dimensions(
        cls,
        *,
        width: int,
        height: int,
        exif_orientation: int | None = None,
        color_mode: str | None = None,
        format: str | None = None,
    ) -> ImageShape:
        return cls(
            width=width,
            height=height,
            aspect_ratio=image_aspect_ratio(width, height),
            orientation=infer_image_orientation(width, height),
            exif_orientation=exif_orientation,
            color_mode=color_mode,
            format=format,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "orientation": self.orientation.value,
            "exif_orientation": self.exif_orientation,
            "color_mode": self.color_mode,
            "format": self.format,
        }


@dataclass(frozen=True, slots=True)
class ImageQualityIndicators:
    blur_score: float | None = None
    sharpness_score: float | None = None
    brightness: float | None = None
    contrast: float | None = None
    is_low_resolution: bool | None = None
    is_probably_blurry: bool | None = None
    is_low_contrast: bool | None = None

    def __post_init__(self) -> None:
        _ensure_optional_non_negative_number(self.blur_score, "blur_score")
        _ensure_optional_non_negative_number(self.sharpness_score, "sharpness_score")
        _ensure_optional_non_negative_number(self.brightness, "brightness")
        _ensure_optional_non_negative_number(self.contrast, "contrast")

    def to_dict(self) -> dict[str, object]:
        return {
            "blur_score": self.blur_score,
            "sharpness_score": self.sharpness_score,
            "brightness": self.brightness,
            "contrast": self.contrast,
            "is_low_resolution": self.is_low_resolution,
            "is_probably_blurry": self.is_probably_blurry,
            "is_low_contrast": self.is_low_contrast,
        }


@dataclass(frozen=True, slots=True)
class ImageDiagnostics:
    file: ImageFileMetadata
    image: ImageShape
    quality: ImageQualityIndicators = field(default_factory=ImageQualityIndicators)
    warnings: tuple[Warning, ...] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(
        default_factory=lambda: {"schema_version": IMAGE_DIAGNOSTICS_SCHEMA_VERSION}
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "file": self.file.to_dict(),
            "image": self.image.to_dict(),
            "quality": self.quality.to_dict(),
            "warnings": [warning.to_dict() for warning in self.warnings],
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class DocumentInfo:
    user_mode_hint: DocumentModeHint
    detected_type: DetectedDocumentType = DetectedDocumentType.UNKNOWN
    detected_type_confidence: float | None = None
    language: str | None = None
    summary: str | None = None

    def __post_init__(self) -> None:
        _ensure_enum_member(self.user_mode_hint, DocumentModeHint, "user_mode_hint")
        _ensure_enum_member(self.detected_type, DetectedDocumentType, "detected_type")
        _ensure_optional_unit_interval(
            self.detected_type_confidence,
            "detected_type_confidence",
        )
        _ensure_optional_non_empty_text(self.language, "language")
        _ensure_optional_non_empty_text(self.summary, "summary")

    def to_dict(self) -> dict[str, object]:
        return {
            "user_mode_hint": self.user_mode_hint.value,
            "detected_type": self.detected_type.value,
            "detected_type_confidence": self.detected_type_confidence,
            "language": self.language,
            "summary": self.summary,
        }


@dataclass(frozen=True, slots=True)
class RawText:
    text: str
    confidence: float | None = None
    warnings: tuple[Warning, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _ensure_optional_unit_interval(self.confidence, "confidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class ExtractedField:
    label: str
    value: str
    confidence: float | None = None
    source: FieldSource = FieldSource.UNKNOWN
    warnings: tuple[Warning, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _ensure_enum_member(self.source, FieldSource, "source")
        _ensure_non_empty_text(self.label, "label")
        _ensure_optional_unit_interval(self.confidence, "confidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "value": self.value,
            "confidence": self.confidence,
            "source": self.source.value,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class TableRow:
    cells: tuple[str, ...]
    confidence: float | None = None
    warnings: tuple[Warning, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.cells:
            msg = "cells must contain at least one value"
            raise ValueError(msg)
        _ensure_optional_unit_interval(self.confidence, "confidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "cells": list(self.cells),
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    columns: tuple[str, ...]
    rows: tuple[TableRow, ...]
    title: str | None = None
    confidence: float | None = None
    warnings: tuple[Warning, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.columns:
            msg = "columns must contain at least one value"
            raise ValueError(msg)
        for column in self.columns:
            _ensure_non_empty_text(column, "columns")
        _ensure_optional_non_empty_text(self.title, "title")
        _ensure_optional_unit_interval(self.confidence, "confidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "columns": list(self.columns),
            "rows": [row.to_dict() for row in self.rows],
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class TextBlock:
    type: BlockType
    text: str
    order: int
    level: int | None = None
    confidence: float | None = None
    warnings: tuple[Warning, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _ensure_enum_member(self.type, BlockType, "type")
        _ensure_non_empty_text(self.text, "text")
        _ensure_non_negative_int(self.order, "order")
        _ensure_optional_positive_int(self.level, "level")
        _ensure_optional_unit_interval(self.confidence, "confidence")

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type.value,
            "level": self.level,
            "text": self.text,
            "order": self.order,
            "confidence": self.confidence,
            "warnings": [warning.to_dict() for warning in self.warnings],
        }


@dataclass(frozen=True, slots=True)
class ExtractionMetadata:
    schema_version: str = EXTRACTION_RESULT_SCHEMA_VERSION
    provider: str | None = None
    model: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.schema_version, "schema_version")
        _ensure_optional_non_empty_text(self.provider, "provider")
        _ensure_optional_non_empty_text(self.model, "model")

    def to_dict(self) -> dict[str, object]:
        created_at = self.created_at.isoformat() if self.created_at is not None else None
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "model": self.model,
            "created_at": created_at,
        }


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    document: DocumentInfo
    image_diagnostics: ImageDiagnostics
    raw_text: RawText
    fields: tuple[ExtractedField, ...] = field(default_factory=tuple)
    tables: tuple[ExtractedTable, ...] = field(default_factory=tuple)
    blocks: tuple[TextBlock, ...] = field(default_factory=tuple)
    warnings: tuple[Warning, ...] = field(default_factory=tuple)
    metadata: ExtractionMetadata = field(default_factory=ExtractionMetadata)

    def to_dict(self) -> dict[str, object]:
        return {
            "document": self.document.to_dict(),
            "image_diagnostics": self.image_diagnostics.to_dict(),
            "raw_text": self.raw_text.to_dict(),
            "fields": [extracted_field.to_dict() for extracted_field in self.fields],
            "tables": [table.to_dict() for table in self.tables],
            "blocks": [block.to_dict() for block in self.blocks],
            "warnings": [warning.to_dict() for warning in self.warnings],
            "metadata": self.metadata.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class ProviderJobContext:
    job_id: str
    processing_stage: JobStatus
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        _ensure_enum_member(self.processing_stage, JobStatus, "processing_stage")
        _ensure_non_empty_text(self.job_id, "job_id")

    def to_dict(self) -> dict[str, object]:
        created_at = self.created_at.isoformat() if self.created_at is not None else None
        return {
            "job_id": self.job_id,
            "processing_stage": self.processing_stage.value,
            "created_at": created_at,
        }


@dataclass(frozen=True, slots=True)
class ProviderUserRequest:
    user_mode_hint: DocumentModeHint

    def __post_init__(self) -> None:
        _ensure_enum_member(self.user_mode_hint, DocumentModeHint, "user_mode_hint")

    def to_dict(self) -> dict[str, object]:
        return {"user_mode_hint": self.user_mode_hint.value}


@dataclass(frozen=True, slots=True)
class ProviderImageReference:
    image_id: str
    provider_image_reference: str
    mime_type: str
    width: int
    height: int
    file_size_bytes: int

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.image_id, "image_id")
        _ensure_non_empty_text(
            self.provider_image_reference,
            "provider_image_reference",
        )
        _ensure_non_empty_text(self.mime_type, "mime_type")
        _ensure_positive_int(self.width, "width")
        _ensure_positive_int(self.height, "height")
        _ensure_positive_int(self.file_size_bytes, "file_size_bytes")

    def to_dict(self) -> dict[str, object]:
        return {
            "image_id": self.image_id,
            "provider_image_reference": self.provider_image_reference,
            "mime_type": self.mime_type,
            "width": self.width,
            "height": self.height,
            "file_size_bytes": self.file_size_bytes,
        }


@dataclass(frozen=True, slots=True)
class ProviderInputContext:
    job: ProviderJobContext
    user_request: ProviderUserRequest
    image: ProviderImageReference
    image_diagnostics: ImageDiagnostics
    extraction_goal: ExtractionGoal = ExtractionGoal.EXTRACT_TEXT_AND_STRUCTURE
    expected_result_shape: tuple[ExpectedResultSection, ...] = DEFAULT_EXPECTED_RESULT_SHAPE
    constraints: tuple[ProviderConstraint, ...] = DEFAULT_PROVIDER_CONSTRAINTS

    def __post_init__(self) -> None:
        _ensure_enum_member(self.extraction_goal, ExtractionGoal, "extraction_goal")
        if not self.expected_result_shape:
            msg = "expected_result_shape must contain at least one section"
            raise ValueError(msg)
        if not self.constraints:
            msg = "constraints must contain at least one constraint"
            raise ValueError(msg)
        for section in self.expected_result_shape:
            _ensure_enum_member(section, ExpectedResultSection, "expected_result_shape")
        for constraint in self.constraints:
            _ensure_enum_member(constraint, ProviderConstraint, "constraints")

    def to_dict(self) -> dict[str, object]:
        return {
            "job": self.job.to_dict(),
            "user_request": self.user_request.to_dict(),
            "image": self.image.to_dict(),
            "image_diagnostics": self.image_diagnostics.to_dict(),
            "extraction_goal": self.extraction_goal.value,
            "expected_result_shape": [
                section.value for section in self.expected_result_shape
            ],
            "constraints": [constraint.value for constraint in self.constraints],
        }


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_optional_non_empty_text(value: str | None, field_name: str) -> None:
    if value is not None:
        _ensure_non_empty_text(value, field_name)


def _ensure_enum_member(
    value: object,
    enum_type: type[Enum],
    field_name: str,
) -> None:
    if not isinstance(value, enum_type):
        msg = f"{field_name} must be a {enum_type.__name__} value"
        raise ValueError(msg)


def _ensure_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or value <= 0:
        msg = f"{field_name} must be a positive integer"
        raise ValueError(msg)


def _ensure_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or value < 0:
        msg = f"{field_name} must be a non-negative integer"
        raise ValueError(msg)


def _ensure_optional_positive_int(value: int | None, field_name: str) -> None:
    if value is not None:
        _ensure_positive_int(value, field_name)


def _ensure_positive_float(value: float, field_name: str) -> None:
    if isinstance(value, bool) or not isfinite(value) or value <= 0:
        msg = f"{field_name} must be a positive finite number"
        raise ValueError(msg)


def _ensure_optional_non_negative_number(
    value: float | None,
    field_name: str,
) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isfinite(value) or value < 0:
        msg = f"{field_name} must be a non-negative finite number"
        raise ValueError(msg)


def _ensure_optional_unit_interval(value: float | None, field_name: str) -> None:
    if value is None:
        return
    if isinstance(value, bool) or not isfinite(value) or value < 0 or value > 1:
        msg = f"{field_name} must be between 0 and 1"
        raise ValueError(msg)
