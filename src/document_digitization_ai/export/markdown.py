from __future__ import annotations

from collections.abc import Sequence
import re

from document_digitization_ai.export.models import (
    ExportDocument,
    ExportSection,
    ExportSectionKind,
    ExportTableRow,
    ExportTableSection,
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


def render_reconstructed_text_markdown(export_document: ExportDocument) -> str:
    return "\n".join(_reconstructed_text_lines(export_document)).strip()


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
    lines.extend(render_reconstructed_text_markdown(export_document).split("\n"))
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


def _reconstructed_text_lines(export_document: ExportDocument) -> list[str]:
    raw_text = _clean_text(export_document.raw_text)
    if raw_text is None:
        if export_document.table_sections:
            return _structured_tables_text_lines(export_document.table_sections)
        return ["Текст не извлечён."]
    lines, has_formatted_tables = _normalize_raw_text_lines(raw_text)
    if has_formatted_tables or not export_document.table_sections:
        return lines
    return _merge_structured_tables_into_text(lines, export_document.table_sections)


def _normalize_raw_text_lines(value: str) -> tuple[list[str], bool]:
    source_lines = value.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[str] = []
    has_formatted_tables = False

    index = 0
    while index < len(source_lines):
        line = source_lines[index]
        if not _pipe_candidate(line):
            lines.append(_normalize_text_line(line))
            index += 1
            continue

        block_end = index
        while block_end < len(source_lines) and _pipe_candidate(source_lines[block_end]):
            block_end += 1

        table_lines = _normalized_pipe_table(source_lines[index:block_end])
        if table_lines is None:
            lines.extend(
                _normalize_text_line(block_line)
                for block_line in source_lines[index:block_end]
            )
        else:
            lines.extend(table_lines)
            has_formatted_tables = True
        index = block_end

    return lines, has_formatted_tables


def _merge_structured_tables_into_text(
    lines: Sequence[str],
    table_sections: Sequence[ExportTableSection],
) -> list[str]:
    replacements: dict[int, list[str]] = {}
    consumed_line_indexes: set[int] = set()
    unmatched_tables: list[ExportTableSection] = []
    search_start = 0

    for table in table_sections:
        table_lines = _structured_table_lines(table)
        if not table_lines:
            continue

        matched_indexes = _find_structured_table_line_indexes(
            lines,
            table,
            consumed_line_indexes,
            search_start,
        )
        if not matched_indexes:
            unmatched_tables.append(table)
            continue

        replacements[matched_indexes[0]] = table_lines
        consumed_line_indexes.update(matched_indexes)
        search_start = matched_indexes[-1] + 1

    output: list[str] = []
    for index, line in enumerate(lines):
        replacement = replacements.get(index)
        if replacement is not None:
            if output and output[-1] != "":
                output.append("")
            output.extend(replacement)

        if index in consumed_line_indexes:
            continue

        output.append(line)

    if unmatched_tables:
        if output and output[-1] != "":
            output.append("")
        for table in unmatched_tables:
            table_lines = _structured_table_lines(table)
            if not table_lines:
                continue
            if output and output[-1] != "":
                output.append("")
            output.extend(table_lines)

    return _trim_blank_edges(output)


def _structured_tables_text_lines(
    table_sections: Sequence[ExportTableSection],
) -> list[str]:
    lines: list[str] = []
    for table in table_sections:
        table_lines = _structured_table_lines(table)
        if not table_lines:
            continue
        if lines:
            lines.append("")
        lines.extend(table_lines)
    return lines or ["Текст не извлечён."]


def _structured_table_lines(table: ExportTableSection) -> list[str]:
    table_columns = _table_columns(table.columns, table.rows)
    if not table_columns:
        return []
    rows = tuple(_padded_cells(row.cells, len(table_columns)) for row in table.rows)
    return _markdown_table(table_columns, rows)


def _find_structured_table_line_indexes(
    lines: Sequence[str],
    table: ExportTableSection,
    consumed_line_indexes: set[int],
    start_index: int,
) -> tuple[int, ...]:
    sequence = _structured_table_match_sequence(table)
    expected = tuple(item for item in sequence if item)
    if not expected:
        return ()

    candidates = tuple(
        index
        for index in range(max(0, start_index), len(lines))
        if index not in consumed_line_indexes and _match_key(lines[index])
    )
    for offset in range(len(candidates)):
        matched: list[int] = []
        for expected_offset, expected_key in enumerate(expected):
            candidate_offset = offset + expected_offset
            if candidate_offset >= len(candidates):
                break
            line_index = candidates[candidate_offset]
            if _match_key(lines[line_index]) != expected_key:
                break
            matched.append(line_index)
        if len(matched) == len(expected):
            return tuple(matched)
    return _find_fuzzy_structured_table_line_indexes(
        lines,
        table,
        consumed_line_indexes,
        start_index,
    )


def _find_fuzzy_structured_table_line_indexes(
    lines: Sequence[str],
    table: ExportTableSection,
    consumed_line_indexes: set[int],
    start_index: int,
) -> tuple[int, ...]:
    row_patterns = tuple(
        pattern for row in table.rows if (pattern := _match_parts(row.cells))
    )
    if not row_patterns:
        return ()

    candidates = tuple(
        index
        for index in range(max(0, start_index), len(lines))
        if index not in consumed_line_indexes and _match_key(lines[index])
    )
    for offset in range(len(candidates)):
        matched: list[int] = []
        for row_offset, row_pattern in enumerate(row_patterns):
            candidate_offset = offset + row_offset
            if candidate_offset >= len(candidates):
                break
            line_index = candidates[candidate_offset]
            if not _line_contains_parts(_match_key(lines[line_index]), row_pattern):
                break
            matched.append(line_index)
        if len(matched) == len(row_patterns):
            header_index = _preceding_header_index(
                lines,
                table,
                candidates,
                offset,
            )
            if header_index is not None:
                return (header_index, *matched)
            return tuple(matched)
    return ()


def _preceding_header_index(
    lines: Sequence[str],
    table: ExportTableSection,
    candidates: Sequence[int],
    row_offset: int,
) -> int | None:
    if row_offset <= 0:
        return None
    header_index = candidates[row_offset - 1]
    if _line_matches_table_header(_match_key(lines[header_index]), table):
        return header_index
    return None


def _line_matches_table_header(line: str, table: ExportTableSection) -> bool:
    parts = _match_parts(_table_columns(table.columns, table.rows))
    if len(parts) < 2:
        return False
    matched_parts = sum(1 for part in parts if part in line)
    return matched_parts >= max(2, len(parts) - 1)


def _line_contains_parts(line: str, parts: Sequence[str]) -> bool:
    return bool(parts) and all(part in line for part in parts)


def _structured_table_match_sequence(table: ExportTableSection) -> tuple[str, ...]:
    table_columns = _table_columns(table.columns, table.rows)
    return tuple(
        item
        for item in (
            _flat_match_line(table_columns),
            *(_flat_match_line(row.cells) for row in table.rows),
        )
        if item
    )


def _flat_match_line(cells: Sequence[object | None]) -> str:
    return _match_key(" ".join(_match_parts(cells)))


def _match_parts(cells: Sequence[object | None]) -> tuple[str, ...]:
    parts = [
        _match_key(cell_text)
        for cell in cells
        if (cell_text := _clean_text(cell)) is not None
    ]
    return tuple(part for part in parts if part)


def _match_key(value: str) -> str:
    text = _normalize_text_line(value).casefold()
    text = re.sub(r"(?<=\d),(?=\d)", ".", text)
    text = re.sub(r"\b(\d{1,2})[./](\d{1,2})[./]20(\d{2})\b", r"\1.\2.\3", text)
    text = text.replace(":", " ")
    return _normalize_text_line(text)


def _trim_blank_edges(lines: Sequence[str]) -> list[str]:
    output = list(lines)
    while output and output[0] == "":
        output.pop(0)
    while output and output[-1] == "":
        output.pop()
    return output


def _normalized_pipe_table(raw_lines: Sequence[str]) -> list[str] | None:
    parsed_rows = [
        row
        for row in (_split_pipe_row(line) for line in raw_lines)
        if row and not _separator_row(row)
    ]
    if len(parsed_rows) < 2:
        return None

    column_count = max((len(row) for row in parsed_rows), default=0)
    if column_count < 2:
        return None

    rows_with_multiple_cells = sum(1 for row in parsed_rows if len(row) >= 2)
    if rows_with_multiple_cells < 2:
        return None

    header = _padded_cells(parsed_rows[0], column_count)
    rows = tuple(_padded_cells(row, column_count) for row in parsed_rows[1:])
    return _markdown_table(header, rows)


def _split_pipe_row(line: str) -> tuple[str, ...]:
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
        if text.endswith("|"):
            text = text[:-1]
    return tuple(_normalize_text_line(cell) for cell in text.split("|"))


def _separator_row(cells: Sequence[str]) -> bool:
    return all(_separator_cell(cell) for cell in cells)


def _separator_cell(value: str) -> bool:
    text = value.strip()
    return bool(text) and all(char in "-:" for char in text)


def _pipe_candidate(line: str) -> bool:
    return "|" in line and bool(line.strip())


def _normalize_text_line(value: str) -> str:
    if not value.strip():
        return ""
    return " ".join(value.split())


def _clean_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
