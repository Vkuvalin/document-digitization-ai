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
        lines.append("Сводка недоступна.")
        return lines
    lines.extend(
        _markdown_table(
            ("Показатель", "Значение"),
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
        lines.append("Предупреждений нет.")
        return lines
    lines.extend(
        _markdown_table(
            ("Уровень", "Источник", "Сообщение"),
            tuple(
                (
                    row.severity,
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
        lines.append("Поля не извлечены.")
        return lines
    lines.extend(
        _markdown_table(
            ("Поле", "Значение", "Уверенность", "Примечания"),
            tuple(
                (
                    row.label,
                    row.value,
                    format_confidence(row.confidence),
                    row.notes,
                )
                for row in export_document.field_rows
            ),
        )
    )
    return lines


def _render_tables(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.table_sections:
        lines.append("Таблицы не извлечены.")
        return lines
    for index, table in enumerate(export_document.table_sections, start=1):
        title = table.title or f"Таблица {index}"
        if index > 1:
            lines.append("")
        lines.extend((f"### Таблица {index} — {title}", ""))
        table_columns = _table_columns(table.columns, table.rows)
        if not table.rows:
            lines.append("Строки таблицы не извлечены.")
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
        lines.append("Текст не извлечён.")
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
        lines.append("Текстовые блоки не извлечены.")
        return lines
    lines.extend(
        _markdown_table(
            ("Порядок", "Тип", "Текст", "Уверенность"),
            tuple(
                (
                    row.order,
                    row.type,
                    row.text,
                    format_confidence(row.confidence),
                )
                for row in export_document.block_rows
            ),
        )
    )
    return lines


def _render_image_diagnostics(
    export_document: ExportDocument,
    section: ExportSection,
) -> list[str]:
    lines = _section_header(section)
    if not export_document.diagnostics_items:
        lines.append("Сведения о качестве изображения недоступны.")
        return lines
    lines.extend(
        _markdown_table(
            ("Показатель", "Значение"),
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
        lines.append("Метаданные извлечения недоступны.")
        return lines
    lines.extend(
        _markdown_table(
            ("Ключ", "Значение"),
            tuple((item.key, item.value) for item in export_document.metadata_items),
        )
    )
    return lines


def _section_header(section: ExportSection) -> list[str]:
    return [f"## {section.title}", ""]


def _markdown_table(
    headers: Sequence[object | None],
    rows: Sequence[Sequence[object | None]],
) -> list[str]:
    normalized_rows = [
        tuple(markdown_table_cell(header) for header in headers),
        *[
            tuple(markdown_table_cell(cell) for cell in _padded_cells(row, len(headers)))
            for row in rows
        ],
    ]
    widths = _column_widths(normalized_rows)
    lines = [
        _markdown_table_row(normalized_rows[0], widths),
        _markdown_table_row(tuple("-" * width for width in widths), widths),
    ]
    for row in normalized_rows[1:]:
        lines.append(_markdown_table_row(row, widths))
    return lines


def _column_widths(rows: Sequence[Sequence[str]]) -> tuple[int, ...]:
    column_count = max((len(row) for row in rows), default=0)
    return tuple(
        max(3, *(len(row[index]) for row in rows if index < len(row)))
        for index in range(column_count)
    )


def _markdown_table_row(row: Sequence[str], widths: Sequence[int]) -> str:
    cells = tuple(
        row[index] if index < len(row) else "—"
        for index in range(len(widths))
    )
    padded_cells = (
        cell.ljust(width) for cell, width in zip(cells, widths, strict=True)
    )
    return f"| {' | '.join(padded_cells)} |"


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
