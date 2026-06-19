from __future__ import annotations

from collections.abc import Sequence

from document_digitization_ai.export.models import (
    ExportDocument,
    ExportSection,
    ExportSectionKind,
    ExportTableRow,
)


def render_extraction_result_markdown(export_document: ExportDocument) -> str:
    lines: list[str] = [f"# {export_document.title}", ""]

    section_renderers = {
        ExportSectionKind.SUMMARY: _render_summary,
        ExportSectionKind.WARNINGS: _render_warnings,
        ExportSectionKind.FIELDS: _render_fields,
        ExportSectionKind.TABLES: _render_tables,
        ExportSectionKind.RAW_TEXT: _render_raw_text,
        ExportSectionKind.TEXT_BLOCKS: _render_text_blocks,
        ExportSectionKind.IMAGE_DIAGNOSTICS: _render_image_diagnostics,
        ExportSectionKind.EXTRACTION_METADATA: _render_extraction_metadata,
    }
    for section in export_document.sections:
        section_lines = section_renderers[section.kind](export_document, section)
        lines.extend(section_lines)
        lines.append("")

    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines) + "\n"


def markdown_table_cell(value: object | None) -> str:
    text = format_empty(value)
    if text == "—":
        return text
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    normalized_lines = [" ".join(line.split()) for line in text.split("\n")]
    text = "<br>".join(normalized_lines)
    return text.replace("|", r"\|")


def format_empty(value: object | None) -> str:
    if value is None:
        return "—"
    text = str(value)
    if not text.strip():
        return "—"
    return text


def format_confidence(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}"


def _render_summary(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.summary_items:
        lines.append("No summary is available.")
        return lines
    lines.extend(
        _markdown_table(
            ("Item", "Value"),
            tuple((item.key, item.value) for item in export_document.summary_items),
        )
    )
    return lines


def _render_warnings(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.warning_rows:
        lines.append("No warnings were reported.")
        return lines
    lines.extend(
        _markdown_table(
            ("Severity", "Code", "Target", "Message"),
            tuple(
                (
                    row.severity,
                    row.code,
                    row.target,
                    row.message,
                )
                for row in export_document.warning_rows
            ),
        )
    )
    return lines


def _render_fields(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.field_rows:
        lines.append("No standalone fields were extracted.")
        return lines
    lines.extend(
        _markdown_table(
            ("Label", "Value", "Confidence", "Notes"),
            tuple(
                (
                    row.label,
                    row.value,
                    format_confidence(row.confidence),
                    row.notes,
                )
                for row in export_document.field_rows
            ),
            aligns=("", "", "---:", ""),
        )
    )
    return lines


def _render_tables(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.table_sections:
        lines.append("No tables were extracted.")
        return lines
    for index, table in enumerate(export_document.table_sections, start=1):
        title = table.title or f"Table {index}"
        lines.extend(("", f"### Table {index} — {title}", ""))
        table_columns = _table_columns(table.columns, table.rows)
        if not table.rows:
            lines.append("No rows were extracted for this table.")
            continue
        rows = tuple(_padded_cells(row.cells, len(table_columns)) for row in table.rows)
        lines.extend(_markdown_table(table_columns, rows))
    return lines


def _render_raw_text(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    raw_text = export_document.raw_text
    if raw_text is None or not raw_text.strip():
        lines.append("No raw text was extracted.")
        return lines
    fence = _code_fence_ticks(raw_text)
    lines.append(f"{fence}text")
    lines.extend(raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    lines.append(fence)
    return lines


def _render_text_blocks(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.block_rows:
        lines.append("No text blocks were extracted.")
        return lines
    lines.extend(
        _markdown_table(
            ("Order", "Type", "Text", "Confidence"),
            tuple(
                (
                    row.order,
                    row.type,
                    row.text,
                    format_confidence(row.confidence),
                )
                for row in export_document.block_rows
            ),
            aligns=("---:", "", "", "---:"),
        )
    )
    return lines


def _render_image_diagnostics(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.diagnostics_items:
        lines.append("No image diagnostics are available.")
        return lines
    lines.extend(
        _markdown_table(
            ("Metric", "Value"),
            tuple((item.key, item.value) for item in export_document.diagnostics_items),
        )
    )
    return lines


def _render_extraction_metadata(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.metadata_items:
        lines.append("No extraction metadata is available.")
        return lines
    lines.extend(
        _markdown_table(
            ("Key", "Value"),
            tuple((item.key, item.value) for item in export_document.metadata_items),
        )
    )
    return lines


def _section_header(section: ExportSection) -> list[str]:
    return [f"## {section.title}", ""]


def _markdown_table(
    headers: Sequence[object | None],
    rows: Sequence[Sequence[object | None]],
    *,
    aligns: Sequence[str] | None = None,
) -> list[str]:
    separator = _separator_row(len(headers), aligns)
    lines = [
        f"| {' | '.join(markdown_table_cell(header) for header in headers)} |",
        f"| {' | '.join(separator)} |",
    ]
    for row in rows:
        cells = _padded_cells(row, len(headers))
        lines.append(f"| {' | '.join(markdown_table_cell(cell) for cell in cells)} |")
    return lines


def _separator_row(
    count: int,
    aligns: Sequence[str] | None,
) -> tuple[str, ...]:
    separators: list[str] = []
    for index in range(count):
        if aligns is not None and index < len(aligns) and aligns[index]:
            separators.append(aligns[index])
        else:
            separators.append("---")
    return tuple(separators)


def _table_columns(
    columns: tuple[str, ...],
    rows: tuple[ExportTableRow, ...],
) -> tuple[str, ...]:
    max_cells = max((len(row.cells) for row in rows), default=0)
    width = max(len(columns), max_cells)
    resolved = list(columns)
    for index in range(len(resolved), width):
        resolved.append(f"Column {index + 1}")
    return tuple(resolved)


def _padded_cells(
    cells: Sequence[object | None],
    expected_length: int,
) -> tuple[object | None, ...]:
    if len(cells) >= expected_length:
        return tuple(cells[:expected_length])
    return tuple(cells) + (None,) * (expected_length - len(cells))


def _code_fence_ticks(value: str) -> str:
    max_backticks = 0
    current = 0
    for char in value:
        if char == "`":
            current += 1
            max_backticks = max(max_backticks, current)
        else:
            current = 0
    return "`" * max(3, max_backticks + 1)
