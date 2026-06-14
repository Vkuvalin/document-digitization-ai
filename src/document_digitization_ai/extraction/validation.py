from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from math import isfinite

from document_digitization_ai.contracts import (
    EXTRACTION_RESULT_SCHEMA_VERSION,
    IMAGE_DIAGNOSTICS_SCHEMA_VERSION,
    BlockType,
    DetectedDocumentType,
    DocumentInfo,
    ExtractedField,
    ExtractedTable,
    ExtractionMetadata,
    ExtractionResult,
    FieldSource,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageQualityIndicators,
    ImageShape,
    RawText,
    TableRow,
    TextBlock,
    Warning,
    WarningCode,
    WarningSeverity,
)
from document_digitization_ai.extraction.provider import ExtractionProviderResponse
from document_digitization_ai.providers import ProviderInputContext


class ProviderOutputValidationOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class ExtractionValidationError(RuntimeError):
    """Raised when provider output cannot be reconstructed safely."""


@dataclass(frozen=True, slots=True)
class ExtractionValidationIssue:
    message: str
    target: str | None = None

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.message, "message")
        _ensure_optional_non_empty_text(self.target, "target")

    def to_warning(self) -> Warning:
        return Warning(
            code=WarningCode.VALIDATION_ERROR,
            message=self.message,
            severity=WarningSeverity.WARNING,
            target=self.target,
        )


@dataclass(frozen=True, slots=True)
class ProviderOutputValidationResult:
    outcome: ProviderOutputValidationOutcome
    extraction_result: ExtractionResult
    validation_warnings: tuple[Warning, ...] = field(default_factory=tuple)
    normalized_payload: Mapping[str, object] = field(default_factory=dict)
    provider_response: ExtractionProviderResponse | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, ProviderOutputValidationOutcome):
            msg = "outcome must be a ProviderOutputValidationOutcome value"
            raise ValueError(msg)
        if self.outcome is ProviderOutputValidationOutcome.FAILED:
            msg = "failed validation results must raise ExtractionValidationError"
            raise ValueError(msg)
        if not isinstance(self.extraction_result, ExtractionResult):
            msg = "extraction_result must be an ExtractionResult value"
            raise ValueError(msg)
        for warning in self.validation_warnings:
            if not isinstance(warning, Warning):
                msg = "validation_warnings must contain Warning values"
                raise ValueError(msg)


def validate_provider_output(
    provider_response: ExtractionProviderResponse,
    *,
    context: ProviderInputContext,
    image_diagnostics: ImageDiagnostics,
) -> ProviderOutputValidationResult:
    if not isinstance(provider_response, ExtractionProviderResponse):
        msg = "provider_response must be an ExtractionProviderResponse value"
        raise ExtractionValidationError(msg)
    if not isinstance(context, ProviderInputContext):
        msg = "context must be a ProviderInputContext value"
        raise ExtractionValidationError(msg)
    if not isinstance(image_diagnostics, ImageDiagnostics):
        msg = "image_diagnostics must be an ImageDiagnostics value"
        raise ExtractionValidationError(msg)

    payload = _require_mapping(provider_response.raw_payload, "raw_payload")
    issues: list[ExtractionValidationIssue] = []
    normalized_payload = _normalize_top_level_payload(payload, issues)

    document = _reconstruct_document(
        normalized_payload.get("document"),
        context,
        issues,
    )
    raw_text = _reconstruct_raw_text(normalized_payload.get("raw_text"), issues)
    fields = _reconstruct_fields(normalized_payload.get("fields"), issues)
    tables = _reconstruct_tables(normalized_payload.get("tables"), issues)
    blocks = _reconstruct_blocks(normalized_payload.get("blocks"), issues)
    provider_warnings = _reconstruct_provider_warnings(
        normalized_payload.get("warnings"),
        issues,
    )
    _validate_provider_metadata(normalized_payload.get("metadata"), issues)

    if _is_empty_result(raw_text, fields, tables, blocks):
        msg = "Provider output does not contain usable extraction content"
        raise ExtractionValidationError(msg)

    validation_warnings = tuple(issue.to_warning() for issue in issues)
    result_warnings = provider_warnings + validation_warnings
    outcome = (
        ProviderOutputValidationOutcome.PARTIAL
        if result_warnings
        else ProviderOutputValidationOutcome.SUCCEEDED
    )

    extraction_result = ExtractionResult(
        document=document,
        image_diagnostics=image_diagnostics,
        raw_text=raw_text,
        fields=fields,
        tables=tables,
        blocks=blocks,
        warnings=result_warnings,
        metadata=ExtractionMetadata(
            schema_version=EXTRACTION_RESULT_SCHEMA_VERSION,
            provider=provider_response.provider_name,
            model=provider_response.model_name,
        ),
    )
    return ProviderOutputValidationResult(
        outcome=outcome,
        extraction_result=extraction_result,
        validation_warnings=validation_warnings,
        normalized_payload=normalized_payload,
        provider_response=provider_response,
    )


def image_diagnostics_from_payload(payload: Mapping[str, object]) -> ImageDiagnostics:
    diagnostics = _require_mapping(payload, "image_diagnostics_payload")
    file_payload = _require_mapping(diagnostics.get("file"), "image_diagnostics.file")
    image_payload = _require_mapping(diagnostics.get("image"), "image_diagnostics.image")
    quality_payload = _optional_mapping(
        diagnostics.get("quality"),
        "image_diagnostics.quality",
    )
    warnings_payload = diagnostics.get("warnings")
    metadata_payload = _optional_mapping(
        diagnostics.get("metadata"),
        "image_diagnostics.metadata",
    )

    return ImageDiagnostics(
        file=ImageFileMetadata(
            mime_type=_require_text(file_payload.get("mime_type"), "file.mime_type"),
            file_size_bytes=_require_positive_int(
                file_payload.get("file_size_bytes"),
                "file.file_size_bytes",
            ),
            file_extension=_require_text(
                file_payload.get("file_extension"),
                "file.file_extension",
            ),
            sha256=_optional_text(file_payload.get("sha256"), "file.sha256"),
        ),
        image=ImageShape.from_dimensions(
            width=_require_positive_int(image_payload.get("width"), "image.width"),
            height=_require_positive_int(image_payload.get("height"), "image.height"),
            exif_orientation=_optional_positive_int(
                image_payload.get("exif_orientation"),
                "image.exif_orientation",
            ),
            color_mode=_optional_text(image_payload.get("color_mode"), "image.color_mode"),
            format=_optional_text(image_payload.get("format"), "image.format"),
        ),
        quality=ImageQualityIndicators(
            blur_score=_optional_non_negative_number(
                quality_payload.get("blur_score"),
                "quality.blur_score",
            ),
            sharpness_score=_optional_non_negative_number(
                quality_payload.get("sharpness_score"),
                "quality.sharpness_score",
            ),
            brightness=_optional_non_negative_number(
                quality_payload.get("brightness"),
                "quality.brightness",
            ),
            contrast=_optional_non_negative_number(
                quality_payload.get("contrast"),
                "quality.contrast",
            ),
            is_low_resolution=_optional_bool(
                quality_payload.get("is_low_resolution"),
                "quality.is_low_resolution",
            ),
            is_probably_blurry=_optional_bool(
                quality_payload.get("is_probably_blurry"),
                "quality.is_probably_blurry",
            ),
            is_low_contrast=_optional_bool(
                quality_payload.get("is_low_contrast"),
                "quality.is_low_contrast",
            ),
        ),
        warnings=_warnings_from_payload(warnings_payload, "image_diagnostics.warnings"),
        metadata=(
            dict(metadata_payload)
            if metadata_payload
            else {"schema_version": IMAGE_DIAGNOSTICS_SCHEMA_VERSION}
        ),
    )


def _normalize_top_level_payload(
    payload: Mapping[str, object],
    issues: list[ExtractionValidationIssue],
) -> dict[str, object]:
    allowed_keys = {
        "provider_payload_version",
        "document",
        "raw_text",
        "fields",
        "tables",
        "blocks",
        "warnings",
        "metadata",
    }
    extra_keys = sorted(set(payload) - allowed_keys)
    if extra_keys:
        issues.append(
            ExtractionValidationIssue(
                message=f"Provider payload has unsupported top-level keys: {', '.join(extra_keys)}",
                target="provider_payload",
            )
        )
    return {key: payload[key] for key in allowed_keys if key in payload}


def _reconstruct_document(
    value: object,
    context: ProviderInputContext,
    issues: list[ExtractionValidationIssue],
) -> DocumentInfo:
    if value is None:
        issues.append(
            ExtractionValidationIssue(
                message="Provider payload is missing document section; defaulting document type to unknown.",
                target="document",
            )
        )
        return DocumentInfo(user_mode_hint=context.document_mode_hint)
    if not isinstance(value, Mapping):
        issues.append(
            ExtractionValidationIssue(
                message="Provider document section must be an object; defaulting document type to unknown.",
                target="document",
            )
        )
        return DocumentInfo(user_mode_hint=context.document_mode_hint)

    detected_type = _enum_value_or_default(
        value.get("detected_type"),
        DetectedDocumentType,
        DetectedDocumentType.UNKNOWN,
        "document.detected_type",
        issues,
    )
    confidence = _optional_unit_interval_or_none(
        value.get("detected_type_confidence"),
        "document.detected_type_confidence",
        issues,
    )
    language = _optional_text_or_none(value.get("language"), "document.language", issues)
    summary = _optional_text_or_none(value.get("summary"), "document.summary", issues)
    return DocumentInfo(
        user_mode_hint=context.document_mode_hint,
        detected_type=detected_type,
        detected_type_confidence=confidence,
        language=language,
        summary=summary,
    )


def _reconstruct_raw_text(
    value: object,
    issues: list[ExtractionValidationIssue],
) -> RawText:
    if value is None:
        issues.append(
            ExtractionValidationIssue(
                message="Provider payload is missing raw_text section.",
                target="raw_text",
            )
        )
        return RawText(text="")
    if not isinstance(value, Mapping):
        issues.append(
            ExtractionValidationIssue(
                message="Provider raw_text section must be an object.",
                target="raw_text",
            )
        )
        return RawText(text="")
    text = value.get("text")
    if not isinstance(text, str):
        issues.append(
            ExtractionValidationIssue(
                message="Provider raw_text.text must be a string.",
                target="raw_text.text",
            )
        )
        text = ""
    return RawText(
        text=text,
        confidence=_optional_unit_interval_or_none(
            value.get("confidence"),
            "raw_text.confidence",
            issues,
        ),
        warnings=_warnings_from_payload(
            value.get("warnings"),
            "raw_text.warnings",
            issues=issues,
        ),
    )


def _reconstruct_fields(
    value: object,
    issues: list[ExtractionValidationIssue],
) -> tuple[ExtractedField, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        issues.append(
            ExtractionValidationIssue(
                message="Provider fields section must be a list; ignoring fields.",
                target="fields",
            )
        )
        return ()
    fields: list[ExtractedField] = []
    for index, item in enumerate(value):
        target = f"fields[{index}]"
        if not isinstance(item, Mapping):
            issues.append(
                ExtractionValidationIssue(
                    message="Provider field item must be an object; skipping field.",
                    target=target,
                )
            )
            continue
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            issues.append(
                ExtractionValidationIssue(
                    message="Provider field label must be a non-empty string; skipping field.",
                    target=f"{target}.label",
                )
            )
            continue
        value_text = item.get("value")
        if not isinstance(value_text, str):
            issues.append(
                ExtractionValidationIssue(
                    message="Provider field value must be a string; coercing to empty string.",
                    target=f"{target}.value",
                )
            )
            value_text = ""
        fields.append(
            ExtractedField(
                label=label,
                value=value_text,
                confidence=_optional_unit_interval_or_none(
                    item.get("confidence"),
                    f"{target}.confidence",
                    issues,
                ),
                source=_enum_value_or_default(
                    item.get("source"),
                    FieldSource,
                    FieldSource.UNKNOWN,
                    f"{target}.source",
                    issues,
                ),
                warnings=_warnings_from_payload(
                    item.get("warnings"),
                    f"{target}.warnings",
                    issues=issues,
                ),
            )
        )
    return tuple(fields)


def _reconstruct_tables(
    value: object,
    issues: list[ExtractionValidationIssue],
) -> tuple[ExtractedTable, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        issues.append(
            ExtractionValidationIssue(
                message="Provider tables section must be a list; ignoring tables.",
                target="tables",
            )
        )
        return ()
    tables: list[ExtractedTable] = []
    for index, item in enumerate(value):
        table = _reconstruct_table(item, index, issues)
        if table is not None:
            tables.append(table)
    return tuple(tables)


def _reconstruct_table(
    value: object,
    index: int,
    issues: list[ExtractionValidationIssue],
) -> ExtractedTable | None:
    target = f"tables[{index}]"
    if not isinstance(value, Mapping):
        issues.append(
            ExtractionValidationIssue(
                message="Provider table item must be an object; skipping table.",
                target=target,
            )
        )
        return None
    columns = _non_empty_string_tuple_from_sequence(
        value.get("columns"),
        f"{target}.columns",
        issues,
    )
    if not columns:
        issues.append(
            ExtractionValidationIssue(
                message="Provider table must have at least one valid column; skipping table.",
                target=f"{target}.columns",
            )
        )
        return None
    rows = _reconstruct_table_rows(value.get("rows"), columns, target, issues)
    return ExtractedTable(
        title=_optional_text_or_none(value.get("title"), f"{target}.title", issues),
        columns=columns,
        rows=rows,
        confidence=_optional_unit_interval_or_none(
            value.get("confidence"),
            f"{target}.confidence",
            issues,
        ),
        warnings=_warnings_from_payload(
            value.get("warnings"),
            f"{target}.warnings",
            issues=issues,
        ),
    )


def _reconstruct_table_rows(
    value: object,
    columns: tuple[str, ...],
    table_target: str,
    issues: list[ExtractionValidationIssue],
) -> tuple[TableRow, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        issues.append(
            ExtractionValidationIssue(
                message="Provider table rows must be a list; ignoring rows.",
                target=f"{table_target}.rows",
            )
        )
        return ()
    rows: list[TableRow] = []
    for index, row_payload in enumerate(value):
        target = f"{table_target}.rows[{index}]"
        if isinstance(row_payload, Mapping):
            cells_payload = row_payload.get("cells")
            confidence = _optional_unit_interval_or_none(
                row_payload.get("confidence"),
                f"{target}.confidence",
                issues,
            )
            warnings = _warnings_from_payload(
                row_payload.get("warnings"),
                f"{target}.warnings",
                issues=issues,
            )
        else:
            cells_payload = row_payload
            confidence = None
            warnings = ()
        cells = _string_tuple_from_sequence(cells_payload, f"{target}.cells", issues)
        if len(cells) < len(columns):
            issues.append(
                ExtractionValidationIssue(
                    message="Provider table row has fewer cells than columns; padding missing cells.",
                    target=f"{target}.cells",
                )
            )
            cells = cells + ("",) * (len(columns) - len(cells))
        if len(cells) > len(columns):
            issues.append(
                ExtractionValidationIssue(
                    message="Provider table row has more cells than columns; truncating extra cells.",
                    target=f"{target}.cells",
                )
            )
            cells = cells[: len(columns)]
        if not cells:
            issues.append(
                ExtractionValidationIssue(
                    message="Provider table row has no usable cells; skipping row.",
                    target=f"{target}.cells",
                )
            )
            continue
        rows.append(TableRow(cells=cells, confidence=confidence, warnings=warnings))
    return tuple(rows)


def _reconstruct_blocks(
    value: object,
    issues: list[ExtractionValidationIssue],
) -> tuple[TextBlock, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        issues.append(
            ExtractionValidationIssue(
                message="Provider blocks section must be a list; ignoring blocks.",
                target="blocks",
            )
        )
        return ()
    blocks: list[TextBlock] = []
    for index, item in enumerate(value):
        target = f"blocks[{index}]"
        if not isinstance(item, Mapping):
            issues.append(
                ExtractionValidationIssue(
                    message="Provider block item must be an object; skipping block.",
                    target=target,
                )
            )
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            issues.append(
                ExtractionValidationIssue(
                    message="Provider block text must be a non-empty string; skipping block.",
                    target=f"{target}.text",
                )
            )
            continue
        order = item.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 0:
            issues.append(
                ExtractionValidationIssue(
                    message="Provider block order must be a non-negative integer; using list order.",
                    target=f"{target}.order",
                )
            )
            order = index
        blocks.append(
            TextBlock(
                type=_enum_value_or_default(
                    item.get("type"),
                    BlockType,
                    BlockType.UNKNOWN,
                    f"{target}.type",
                    issues,
                ),
                text=text,
                order=order,
                level=_optional_positive_int_or_none(
                    item.get("level"),
                    f"{target}.level",
                    issues,
                ),
                confidence=_optional_unit_interval_or_none(
                    item.get("confidence"),
                    f"{target}.confidence",
                    issues,
                ),
                warnings=_warnings_from_payload(
                    item.get("warnings"),
                    f"{target}.warnings",
                    issues=issues,
                ),
            )
        )
    return tuple(blocks)


def _reconstruct_provider_warnings(
    value: object,
    issues: list[ExtractionValidationIssue],
) -> tuple[Warning, ...]:
    return _warnings_from_payload(value, "warnings", issues=issues)


def _validate_provider_metadata(
    value: object,
    issues: list[ExtractionValidationIssue],
) -> None:
    if value is None:
        return
    if not isinstance(value, Mapping):
        issues.append(
            ExtractionValidationIssue(
                message="Provider metadata section must be an object; ignoring metadata.",
                target="metadata",
            )
        )
        return
    schema_version = value.get("schema_version")
    if schema_version is not None and schema_version != EXTRACTION_RESULT_SCHEMA_VERSION:
        issues.append(
            ExtractionValidationIssue(
                message="Provider metadata schema_version does not match internal result schema.",
                target="metadata.schema_version",
            )
        )


def _warnings_from_payload(
    value: object,
    target: str,
    *,
    issues: list[ExtractionValidationIssue] | None = None,
) -> tuple[Warning, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        if issues is not None:
            issues.append(
                ExtractionValidationIssue(
                    message="Provider warnings must be a list; ignoring warnings.",
                    target=target,
                )
            )
            return ()
        raise ExtractionValidationError(f"{target} must be a list")
    warnings: list[Warning] = []
    for index, item in enumerate(value):
        warning_target = f"{target}[{index}]"
        if not isinstance(item, Mapping):
            if issues is not None:
                issues.append(
                    ExtractionValidationIssue(
                        message="Provider warning item must be an object; skipping warning.",
                        target=warning_target,
                    )
                )
                continue
            raise ExtractionValidationError(f"{warning_target} must be an object")
        code = _enum_value_or_default(
            item.get("code"),
            WarningCode,
            WarningCode.VALIDATION_ERROR,
            f"{warning_target}.code",
            issues,
        )
        severity = _enum_value_or_default(
            item.get("severity"),
            WarningSeverity,
            WarningSeverity.WARNING,
            f"{warning_target}.severity",
            issues,
        )
        message = item.get("message")
        if not isinstance(message, str) or not message.strip():
            if issues is not None:
                issues.append(
                    ExtractionValidationIssue(
                        message="Provider warning message must be a non-empty string; skipping warning.",
                        target=f"{warning_target}.message",
                    )
                )
                continue
            raise ExtractionValidationError(f"{warning_target}.message must be present")
        warnings.append(
            Warning(
                code=code,
                message=message,
                severity=severity,
                target=_optional_text_or_none(
                    item.get("target"),
                    f"{warning_target}.target",
                    issues if issues is not None else [],
                ),
            )
        )
    return tuple(warnings)


def _is_empty_result(
    raw_text: RawText,
    fields: tuple[ExtractedField, ...],
    tables: tuple[ExtractedTable, ...],
    blocks: tuple[TextBlock, ...],
) -> bool:
    return (
        not raw_text.text.strip()
        and not fields
        and not tables
        and not blocks
    )


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be a JSON object"
        raise ExtractionValidationError(msg)
    _ensure_json_compatible(value, field_name)
    return value


def _optional_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if value is None:
        return {}
    return _require_mapping(value, field_name)


def _require_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must be a non-empty string"
        raise ExtractionValidationError(msg)
    return value


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must be a non-empty string when present"
        raise ExtractionValidationError(msg)
    return value


def _optional_text_or_none(
    value: object,
    target: str,
    issues: list[ExtractionValidationIssue],
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        issues.append(
            ExtractionValidationIssue(
                message=f"{target} must be a non-empty string when present; ignoring value.",
                target=target,
            )
        )
        return None
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{field_name} must be a positive integer"
        raise ExtractionValidationError(msg)
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_positive_int(value, field_name)


def _optional_positive_int_or_none(
    value: object,
    target: str,
    issues: list[ExtractionValidationIssue],
) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        issues.append(
            ExtractionValidationIssue(
                message=f"{target} must be a positive integer when present; ignoring value.",
                target=target,
            )
        )
        return None
    return value


def _optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        msg = f"{field_name} must be a boolean when present"
        raise ExtractionValidationError(msg)
    return value


def _optional_non_negative_number(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float) or not isfinite(value) or value < 0:
        msg = f"{field_name} must be a non-negative finite number when present"
        raise ExtractionValidationError(msg)
    return float(value)


def _optional_unit_interval_or_none(
    value: object,
    target: str,
    issues: list[ExtractionValidationIssue],
) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value < 0
        or value > 1
    ):
        issues.append(
            ExtractionValidationIssue(
                message=f"{target} must be a finite number between 0 and 1; ignoring value.",
                target=target,
            )
        )
        return None
    return float(value)


def _enum_value_or_default[T: StrEnum](
    value: object,
    enum_type: type[T],
    default: T,
    target: str,
    issues: list[ExtractionValidationIssue] | None,
) -> T:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            pass
    if issues is not None:
        issues.append(
            ExtractionValidationIssue(
                message=f"{target} has unsupported value; using {default.value}.",
                target=target,
            )
        )
    return default


def _string_tuple_from_sequence(
    value: object,
    target: str,
    issues: list[ExtractionValidationIssue],
) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        issues.append(
            ExtractionValidationIssue(
                message=f"{target} must be a list of strings; using no values.",
                target=target,
            )
        )
        return ()
    values: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            issues.append(
                ExtractionValidationIssue(
                    message=f"{target}[{index}] must be a string; coercing to empty string.",
                    target=f"{target}[{index}]",
                )
            )
            values.append("")
        else:
            values.append(item)
    return tuple(values)


def _non_empty_string_tuple_from_sequence(
    value: object,
    target: str,
    issues: list[ExtractionValidationIssue],
) -> tuple[str, ...]:
    values = _string_tuple_from_sequence(value, target, issues)
    non_empty_values: list[str] = []
    for index, item in enumerate(values):
        if not item.strip():
            issues.append(
                ExtractionValidationIssue(
                    message=f"{target}[{index}] must be a non-empty string; ignoring column.",
                    target=f"{target}[{index}]",
                )
            )
            continue
        non_empty_values.append(item)
    return tuple(non_empty_values)


def _ensure_json_compatible(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not isfinite(value):
            msg = f"{field_name} must be finite"
            raise ExtractionValidationError(msg)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_compatible(item, f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                msg = f"{field_name} keys must be non-empty strings"
                raise ExtractionValidationError(msg)
            _ensure_json_compatible(item, f"{field_name}.{key}")
        return
    msg = f"{field_name} must be JSON-compatible"
    raise ExtractionValidationError(msg)


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_optional_non_empty_text(value: str | None, field_name: str) -> None:
    if value is not None:
        _ensure_non_empty_text(value, field_name)
