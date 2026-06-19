from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum

from document_digitization_ai.contracts import ExtractionResult, Warning
from document_digitization_ai.db.models import DocumentJob, ExtractionAttempt
from document_digitization_ai.export.models import (
    STABLE_EXPORT_SECTIONS,
    ExportDocument,
    ExportFieldRow,
    ExportKeyValueItem,
    ExportTableRow,
    ExportTableSection,
    ExportTextBlockRow,
    ExportWarningRow,
)


def build_extraction_result_export_document(
    result: ExtractionResult,
    *,
    job: DocumentJob | None = None,
    attempt: ExtractionAttempt | None = None,
) -> ExportDocument:
    warning_rows = _build_warning_rows(result)
    return ExportDocument(
        title="Document Extraction Result",
        sections=STABLE_EXPORT_SECTIONS,
        summary_items=_build_summary_items(
            result,
            warning_count=len(warning_rows),
            job=job,
            attempt=attempt,
        ),
        warning_rows=warning_rows,
        field_rows=_build_field_rows(result),
        table_sections=_build_table_sections(result),
        raw_text=result.raw_text.text,
        block_rows=_build_block_rows(result),
        diagnostics_items=_build_diagnostics_items(result),
        metadata_items=_build_metadata_items(result, job=job, attempt=attempt),
    )


def _build_summary_items(
    result: ExtractionResult,
    *,
    warning_count: int,
    job: DocumentJob | None,
    attempt: ExtractionAttempt | None,
) -> tuple[ExportKeyValueItem, ...]:
    document = result.document
    return (
        ExportKeyValueItem("Document type", document.detected_type.value),
        ExportKeyValueItem("Language", document.language),
        ExportKeyValueItem(
            "Validation outcome",
            _validation_outcome(job=job, attempt=attempt),
        ),
        ExportKeyValueItem("Field count", str(len(result.fields))),
        ExportKeyValueItem("Table count", str(len(result.tables))),
        ExportKeyValueItem("Warning count", str(warning_count)),
        ExportKeyValueItem("Raw text length", str(len(result.raw_text.text))),
    )


def _validation_outcome(
    *,
    job: DocumentJob | None,
    attempt: ExtractionAttempt | None,
) -> str:
    if job is not None and job.validation_status:
        return job.validation_status
    if attempt is not None and attempt.validation_outcome:
        return attempt.validation_outcome
    return "unknown"


def _build_warning_rows(result: ExtractionResult) -> tuple[ExportWarningRow, ...]:
    rows: list[ExportWarningRow] = []
    rows.extend(_warning_rows(result.warnings, default_target="result"))
    rows.extend(_warning_rows(result.raw_text.warnings, default_target="raw_text"))
    rows.extend(
        _warning_rows(
            result.image_diagnostics.warnings,
            default_target="image_diagnostics",
        )
    )
    for field in result.fields:
        rows.extend(_warning_rows(field.warnings, default_target=f"field:{field.label}"))
    for table_index, table in enumerate(result.tables, start=1):
        table_target = f"table:{table.title or table_index}"
        rows.extend(_warning_rows(table.warnings, default_target=table_target))
        for row_index, row in enumerate(table.rows, start=1):
            rows.extend(
                _warning_rows(
                    row.warnings,
                    default_target=f"{table_target}:row:{row_index}",
                )
            )
    for block in result.blocks:
        rows.extend(
            _warning_rows(block.warnings, default_target=f"block:{block.order}")
        )
    return tuple(rows)


def _warning_rows(
    warnings: Iterable[Warning],
    *,
    default_target: str,
) -> tuple[ExportWarningRow, ...]:
    return tuple(
        ExportWarningRow(
            severity=warning.severity.value,
            code=warning.code.value,
            target=warning.target or default_target,
            message=warning.message,
        )
        for warning in warnings
    )


def _build_field_rows(result: ExtractionResult) -> tuple[ExportFieldRow, ...]:
    rows: list[ExportFieldRow] = []
    for field in result.fields:
        rows.append(
            ExportFieldRow(
                label=field.label,
                value=field.value,
                confidence=field.confidence,
                notes=_warning_notes(field.warnings),
            )
        )
    return tuple(rows)


def _build_table_sections(result: ExtractionResult) -> tuple[ExportTableSection, ...]:
    sections: list[ExportTableSection] = []
    for index, table in enumerate(result.tables, start=1):
        sections.append(
            ExportTableSection(
                id=f"table-{index}",
                title=table.title,
                columns=table.columns,
                rows=tuple(ExportTableRow(cells=row.cells) for row in table.rows),
                confidence=table.confidence,
            )
        )
    return tuple(sections)


def _build_block_rows(result: ExtractionResult) -> tuple[ExportTextBlockRow, ...]:
    return tuple(
        ExportTextBlockRow(
            order=block.order,
            type=block.type.value,
            text=block.text,
            confidence=block.confidence,
        )
        for block in sorted(result.blocks, key=lambda block: block.order)
    )


def _build_diagnostics_items(result: ExtractionResult) -> tuple[ExportKeyValueItem, ...]:
    diagnostics = result.image_diagnostics
    image = diagnostics.image
    quality = diagnostics.quality
    candidates: tuple[tuple[str, str, object | None], ...] = (
        ("MIME type", "mime_type", diagnostics.file.mime_type),
        ("File size bytes", "file_size_bytes", diagnostics.file.file_size_bytes),
        ("File extension", "file_extension", diagnostics.file.file_extension),
        ("Width", "width", image.width),
        ("Height", "height", image.height),
        ("Orientation", "orientation", image.orientation.value),
        ("Color mode", "color_mode", image.color_mode),
        ("Image format", "format", image.format),
        ("EXIF orientation", "exif_orientation", image.exif_orientation),
        ("Blur score", "blur_score", quality.blur_score),
        ("Sharpness score", "sharpness_score", quality.sharpness_score),
        ("Brightness", "brightness", quality.brightness),
        ("Contrast", "contrast", quality.contrast),
        ("Low resolution", "is_low_resolution", quality.is_low_resolution),
        ("Probably blurry", "is_probably_blurry", quality.is_probably_blurry),
        ("Low contrast", "is_low_contrast", quality.is_low_contrast),
        (
            "Diagnostics schema version",
            "schema_version",
            diagnostics.metadata.get("schema_version"),
        ),
    )
    return tuple(
        ExportKeyValueItem(label, _format_metadata_value(value))
        for label, key, value in candidates
        if _is_safe_metadata_pair(key, value)
    )


def _build_metadata_items(
    result: ExtractionResult,
    *,
    job: DocumentJob | None,
    attempt: ExtractionAttempt | None,
) -> tuple[ExportKeyValueItem, ...]:
    metadata = result.metadata
    candidates: list[tuple[str, str, object | None]] = [
        ("Schema version", "schema_version", metadata.schema_version),
        ("Provider", "provider", metadata.provider),
        ("Model", "model", metadata.model),
        ("Created at", "created_at", metadata.created_at),
    ]
    if job is not None:
        candidates.extend(
            [
                ("Job ID", "job_id", job.id),
                ("Job status", "job_status", job.status.value),
                ("Validation status", "validation_status", job.validation_status),
                ("Completed attempt ID", "completed_attempt_id", job.completed_attempt_id),
            ]
        )
    if attempt is not None:
        candidates.extend(
            [
                ("Attempt ID", "attempt_id", attempt.id),
                ("Attempt status", "attempt_status", attempt.status.value),
                ("Attempt number", "attempt_number", attempt.attempt_number),
                ("Attempt provider", "attempt_provider", attempt.provider_name),
                ("Attempt model", "attempt_model", attempt.model_name),
                ("Attempt schema version", "attempt_schema_version", attempt.schema_version),
                ("Attempt schema mode", "attempt_schema_mode", attempt.schema_mode),
                ("Validation outcome", "validation_outcome", attempt.validation_outcome),
                (
                    "Validation issue count",
                    "validation_issue_count",
                    attempt.validation_issue_count,
                ),
            ]
        )
    return tuple(
        ExportKeyValueItem(label, _format_metadata_value(value))
        for label, key, value in candidates
        if _is_safe_metadata_pair(key, value)
    )


def _warning_notes(warnings: Iterable[Warning]) -> str | None:
    messages = [warning.message for warning in warnings]
    if not messages:
        return None
    return "; ".join(messages)


def _format_metadata_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _is_safe_metadata_pair(key: str, value: object | None) -> bool:
    if value is None:
        return True
    key_text = key.lower()
    value_text = str(value)
    combined = f"{key_text} {value_text.lower()}"
    if any(token in combined for token in _SENSITIVE_TOKENS):
        return False
    return not _looks_like_absolute_path(value_text)


def _looks_like_absolute_path(value: str) -> bool:
    text = value.strip()
    if len(text) >= 3 and text[1] == ":" and text[2] in {"\\", "/"}:
        return True
    return text.startswith(("/", "\\\\"))


_SENSITIVE_TOKENS: tuple[str, ...] = (
    ".env",
    "api_key",
    "apikey",
    "authorization",
    "bearer ",
    "delete_url",
    "raw_provider_response",
    "raw response",
    "provider_request",
    "full prompt",
    "prompt package",
    "artifact_root",
    "artifact root",
    "local_path",
    "source_image_path",
    "password",
    "secret",
    "token",
)
