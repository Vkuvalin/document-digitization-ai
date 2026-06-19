from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from enum import StrEnum
from math import isfinite

from document_digitization_ai.contracts import (
    EXTRACTION_RESULT_SCHEMA_VERSION,
    BlockType,
    DetectedDocumentType,
    DocumentInfo,
    DocumentModeHint,
    ExtractedField,
    ExtractedTable,
    ExtractionMetadata,
    ExtractionResult,
    FieldSource,
    ImageDiagnostics,
    RawText,
    TableRow,
    TextBlock,
    Warning,
    WarningCode,
    WarningSeverity,
)
from document_digitization_ai.extraction import image_diagnostics_from_payload


class ExtractionResultReconstructionError(RuntimeError):
    """Raised when a persisted extraction result payload is malformed."""


def reconstruct_extraction_result_from_payload(
    payload: Mapping[str, object],
) -> ExtractionResult:
    result_payload = _require_mapping(payload, "extraction_result_payload")
    return ExtractionResult(
        document=_document_from_payload(result_payload.get("document")),
        image_diagnostics=_image_diagnostics_from_result_payload(
            result_payload.get("image_diagnostics")
        ),
        raw_text=_raw_text_from_payload(result_payload.get("raw_text")),
        fields=_fields_from_payload(result_payload.get("fields")),
        tables=_tables_from_payload(result_payload.get("tables")),
        blocks=_blocks_from_payload(result_payload.get("blocks")),
        warnings=_warnings_from_payload(result_payload.get("warnings"), "warnings"),
        metadata=_metadata_from_payload(result_payload.get("metadata")),
    )


def _document_from_payload(value: object) -> DocumentInfo:
    payload = _require_mapping(value, "document")
    return DocumentInfo(
        user_mode_hint=_enum_from_payload(
            payload.get("user_mode_hint"),
            DocumentModeHint,
            "document.user_mode_hint",
        ),
        detected_type=_enum_from_payload(
            payload.get("detected_type"),
            DetectedDocumentType,
            "document.detected_type",
        ),
        detected_type_confidence=_optional_unit_interval(
            payload.get("detected_type_confidence"),
            "document.detected_type_confidence",
        ),
        language=_optional_text(payload.get("language"), "document.language"),
        summary=_optional_text(payload.get("summary"), "document.summary"),
    )


def _image_diagnostics_from_result_payload(value: object) -> ImageDiagnostics:
    payload = _require_mapping(value, "image_diagnostics")
    try:
        return image_diagnostics_from_payload(payload)
    except Exception as exc:
        msg = "image_diagnostics must match persisted diagnostics schema"
        raise ExtractionResultReconstructionError(msg) from exc


def _raw_text_from_payload(value: object) -> RawText:
    payload = _require_mapping(value, "raw_text")
    return RawText(
        text=_require_string(payload.get("text"), "raw_text.text"),
        confidence=_optional_unit_interval(
            payload.get("confidence"),
            "raw_text.confidence",
        ),
        warnings=_warnings_from_payload(
            payload.get("warnings"),
            "raw_text.warnings",
        ),
    )


def _fields_from_payload(value: object) -> tuple[ExtractedField, ...]:
    if value is None:
        return ()
    items = _require_list(value, "fields")
    fields: list[ExtractedField] = []
    for index, item in enumerate(items):
        payload = _require_mapping(item, f"fields[{index}]")
        fields.append(
            ExtractedField(
                label=_require_text(payload.get("label"), f"fields[{index}].label"),
                value=_require_string(payload.get("value"), f"fields[{index}].value"),
                confidence=_optional_unit_interval(
                    payload.get("confidence"),
                    f"fields[{index}].confidence",
                ),
                source=_enum_from_payload(
                    payload.get("source"),
                    FieldSource,
                    f"fields[{index}].source",
                ),
                warnings=_warnings_from_payload(
                    payload.get("warnings"),
                    f"fields[{index}].warnings",
                ),
            )
        )
    return tuple(fields)


def _tables_from_payload(value: object) -> tuple[ExtractedTable, ...]:
    if value is None:
        return ()
    items = _require_list(value, "tables")
    return tuple(_table_from_payload(item, index) for index, item in enumerate(items))


def _table_from_payload(value: object, index: int) -> ExtractedTable:
    payload = _require_mapping(value, f"tables[{index}]")
    return ExtractedTable(
        title=_optional_text(payload.get("title"), f"tables[{index}].title"),
        columns=_non_empty_text_tuple(
            payload.get("columns"),
            f"tables[{index}].columns",
        ),
        rows=_table_rows_from_payload(payload.get("rows"), index),
        confidence=_optional_unit_interval(
            payload.get("confidence"),
            f"tables[{index}].confidence",
        ),
        warnings=_warnings_from_payload(
            payload.get("warnings"),
            f"tables[{index}].warnings",
        ),
    )


def _table_rows_from_payload(
    value: object,
    table_index: int,
) -> tuple[TableRow, ...]:
    if value is None:
        return ()
    items = _require_list(value, f"tables[{table_index}].rows")
    rows: list[TableRow] = []
    for row_index, item in enumerate(items):
        payload = _require_mapping(item, f"tables[{table_index}].rows[{row_index}]")
        rows.append(
            TableRow(
                cells=_string_tuple(
                    payload.get("cells"),
                    f"tables[{table_index}].rows[{row_index}].cells",
                ),
                confidence=_optional_unit_interval(
                    payload.get("confidence"),
                    f"tables[{table_index}].rows[{row_index}].confidence",
                ),
                warnings=_warnings_from_payload(
                    payload.get("warnings"),
                    f"tables[{table_index}].rows[{row_index}].warnings",
                ),
            )
        )
    return tuple(rows)


def _blocks_from_payload(value: object) -> tuple[TextBlock, ...]:
    if value is None:
        return ()
    items = _require_list(value, "blocks")
    blocks: list[TextBlock] = []
    for index, item in enumerate(items):
        payload = _require_mapping(item, f"blocks[{index}]")
        blocks.append(
            TextBlock(
                type=_enum_from_payload(
                    payload.get("type"),
                    BlockType,
                    f"blocks[{index}].type",
                ),
                text=_require_text(payload.get("text"), f"blocks[{index}].text"),
                order=_require_non_negative_int(
                    payload.get("order"),
                    f"blocks[{index}].order",
                ),
                level=_optional_positive_int(
                    payload.get("level"),
                    f"blocks[{index}].level",
                ),
                confidence=_optional_unit_interval(
                    payload.get("confidence"),
                    f"blocks[{index}].confidence",
                ),
                warnings=_warnings_from_payload(
                    payload.get("warnings"),
                    f"blocks[{index}].warnings",
                ),
            )
        )
    return tuple(blocks)


def _metadata_from_payload(value: object) -> ExtractionMetadata:
    if value is None:
        return ExtractionMetadata()
    payload = _require_mapping(value, "metadata")
    return ExtractionMetadata(
        schema_version=_optional_text(
            payload.get("schema_version"),
            "metadata.schema_version",
        )
        or EXTRACTION_RESULT_SCHEMA_VERSION,
        provider=_optional_text(payload.get("provider"), "metadata.provider"),
        model=_optional_text(payload.get("model"), "metadata.model"),
        created_at=_optional_datetime(payload.get("created_at"), "metadata.created_at"),
    )


def _warnings_from_payload(value: object, field_name: str) -> tuple[Warning, ...]:
    if value is None:
        return ()
    items = _require_list(value, field_name)
    warnings: list[Warning] = []
    for index, item in enumerate(items):
        payload = _require_mapping(item, f"{field_name}[{index}]")
        warnings.append(
            Warning(
                code=_enum_from_payload(
                    payload.get("code"),
                    WarningCode,
                    f"{field_name}[{index}].code",
                ),
                message=_require_text(
                    payload.get("message"),
                    f"{field_name}[{index}].message",
                ),
                severity=_enum_from_payload(
                    payload.get("severity"),
                    WarningSeverity,
                    f"{field_name}[{index}].severity",
                ),
                target=_optional_text(
                    payload.get("target"),
                    f"{field_name}[{index}].target",
                ),
            )
        )
    return tuple(warnings)


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be a JSON object"
        raise ExtractionResultReconstructionError(msg)
    return value


def _require_list(value: object, field_name: str) -> list[object]:
    if not isinstance(value, list):
        msg = f"{field_name} must be a list"
        raise ExtractionResultReconstructionError(msg)
    return value


def _enum_from_payload[T: StrEnum](
    value: object,
    enum_type: type[T],
    field_name: str,
) -> T:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        try:
            return enum_type(value)
        except ValueError:
            pass
    msg = f"{field_name} must be a valid {enum_type.__name__} value"
    raise ExtractionResultReconstructionError(msg)


def _require_string(value: object, field_name: str) -> str:
    if not isinstance(value, str):
        msg = f"{field_name} must be a string"
        raise ExtractionResultReconstructionError(msg)
    return value


def _require_text(value: object, field_name: str) -> str:
    text = _require_string(value, field_name)
    if not text.strip():
        msg = f"{field_name} must not be empty"
        raise ExtractionResultReconstructionError(msg)
    return text


def _optional_text(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name)


def _optional_datetime(value: object, field_name: str) -> datetime | None:
    if value is None:
        return None
    text = _require_text(value, field_name)
    try:
        return datetime.fromisoformat(text)
    except ValueError as exc:
        msg = f"{field_name} must be an ISO datetime"
        raise ExtractionResultReconstructionError(msg) from exc


def _optional_unit_interval(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value < 0
        or value > 1
    ):
        msg = f"{field_name} must be a finite number between 0 and 1"
        raise ExtractionResultReconstructionError(msg)
    return float(value)


def _require_non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{field_name} must be a non-negative integer"
        raise ExtractionResultReconstructionError(msg)
    return value


def _optional_positive_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{field_name} must be a positive integer"
        raise ExtractionResultReconstructionError(msg)
    return value


def _string_tuple(value: object, field_name: str) -> tuple[str, ...]:
    items = _require_sequence(value, field_name)
    values = tuple(_require_string(item, f"{field_name}[{index}]") for index, item in enumerate(items))
    if not values:
        msg = f"{field_name} must contain at least one value"
        raise ExtractionResultReconstructionError(msg)
    return values


def _non_empty_text_tuple(value: object, field_name: str) -> tuple[str, ...]:
    items = _require_sequence(value, field_name)
    values = tuple(_require_text(item, f"{field_name}[{index}]") for index, item in enumerate(items))
    if not values:
        msg = f"{field_name} must contain at least one value"
        raise ExtractionResultReconstructionError(msg)
    return values


def _require_sequence(value: object, field_name: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        msg = f"{field_name} must be a list"
        raise ExtractionResultReconstructionError(msg)
    return value
