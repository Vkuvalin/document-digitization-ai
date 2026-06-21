from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ExportSectionKind(StrEnum):
    SUMMARY = "summary"
    WARNINGS = "warnings"
    FIELDS = "fields"
    TABLES = "tables"
    RAW_TEXT = "raw_text"
    TEXT_BLOCKS = "text_blocks"
    IMAGE_DIAGNOSTICS = "image_diagnostics"
    EXTRACTION_METADATA = "extraction_metadata"


@dataclass(frozen=True, slots=True)
class ExportSection:
    id: str
    title: str
    kind: ExportSectionKind


@dataclass(frozen=True, slots=True)
class ExportKeyValueItem:
    key: str
    value: str | None


@dataclass(frozen=True, slots=True)
class ExportWarningRow:
    severity: str
    code: str
    target: str | None
    message: str


@dataclass(frozen=True, slots=True)
class ExportFieldRow:
    label: str
    value: str | None
    confidence: float | None
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class ExportTableRow:
    cells: tuple[str | None, ...]


@dataclass(frozen=True, slots=True)
class ExportTableSection:
    id: str
    title: str | None
    columns: tuple[str, ...]
    rows: tuple[ExportTableRow, ...]
    confidence: float | None = None


@dataclass(frozen=True, slots=True)
class ExportTextBlockRow:
    order: int
    type: str
    text: str
    confidence: float | None


@dataclass(frozen=True, slots=True)
class ExportDocument:
    title: str
    sections: tuple[ExportSection, ...]
    summary_items: tuple[ExportKeyValueItem, ...] = field(default_factory=tuple)
    warning_rows: tuple[ExportWarningRow, ...] = field(default_factory=tuple)
    field_rows: tuple[ExportFieldRow, ...] = field(default_factory=tuple)
    table_sections: tuple[ExportTableSection, ...] = field(default_factory=tuple)
    raw_text: str | None = None
    block_rows: tuple[ExportTextBlockRow, ...] = field(default_factory=tuple)
    diagnostics_items: tuple[ExportKeyValueItem, ...] = field(default_factory=tuple)
    metadata_items: tuple[ExportKeyValueItem, ...] = field(default_factory=tuple)


STABLE_EXPORT_SECTIONS: tuple[ExportSection, ...] = (
    ExportSection(
        id="summary",
        title="Сводка",
        kind=ExportSectionKind.SUMMARY,
    ),
    ExportSection(
        id="warnings-and-uncertainty",
        title="Предупреждения",
        kind=ExportSectionKind.WARNINGS,
    ),
    ExportSection(id="fields", title="Поля", kind=ExportSectionKind.FIELDS),
    ExportSection(id="tables", title="Таблицы", kind=ExportSectionKind.TABLES),
    ExportSection(
        id="raw-text",
        title="Текст",
        kind=ExportSectionKind.RAW_TEXT,
    ),
)
