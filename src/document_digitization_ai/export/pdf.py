from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import TypeAlias

import pymupdf

from document_digitization_ai.export.markdown import (
    format_confidence,
    format_empty,
    render_reconstructed_text_markdown,
)
from document_digitization_ai.export.models import (
    ExportDocument,
    ExportSection,
    ExportSectionKind,
    ExportTableRow,
)


class PdfRenderError(RuntimeError):
    """Raised when user-facing PDF output cannot be rendered safely."""


@dataclass(frozen=True, slots=True)
class _TextParagraphBlock:
    lines: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _TextTableBlock:
    headers: tuple[str, ...]
    rows: tuple[tuple[object | None, ...], ...]


_TextBlock: TypeAlias = _TextParagraphBlock | _TextTableBlock


def render_extraction_result_pdf(
    export_document: ExportDocument,
    *,
    job_reference: str | None = None,
    created_at: datetime | None = None,
) -> bytes:
    renderer = _PdfRenderer()
    try:
        return renderer.render(
            export_document,
            job_reference=job_reference,
            created_at=created_at,
        )
    finally:
        renderer.close()


class _PdfRenderer:
    def __init__(self) -> None:
        self.font = pymupdf.Font("helv")
        if not self.font.has_glyph(ord("Р"), fallback=True):
            msg = "Configured PDF font cannot render Cyrillic labels."
            raise PdfRenderError(msg)
        self.document = pymupdf.open()
        self.page: pymupdf.Page | None = None
        self.y = _MARGIN_TOP
        self._new_page()

    def close(self) -> None:
        self.document.close()

    def render(
        self,
        export_document: ExportDocument,
        *,
        job_reference: str | None,
        created_at: datetime | None,
    ) -> bytes:
        self.add_heading(export_document.title, font_size=18)
        reference_rows: list[tuple[str, str | None]] = []
        if job_reference:
            reference_rows.append(("Задание", job_reference))
        if created_at is not None:
            reference_rows.append(("Создано", created_at.isoformat()))
        if reference_rows:
            self.add_key_values(reference_rows, font_size=9)
            self.add_gap(8)

        for section in export_document.sections:
            self._render_section(export_document, section)

        return self.document.tobytes(garbage=4, deflate=True)

    def _render_section(
        self,
        export_document: ExportDocument,
        section: ExportSection,
    ) -> None:
        if section.kind is ExportSectionKind.SUMMARY:
            self.add_section_title(section.title)
            if export_document.summary_items:
                self.add_key_values(
                    tuple((item.key, item.value) for item in export_document.summary_items)
                )
            else:
                self.add_paragraph("Сводка недоступна.")
            return

        if section.kind is ExportSectionKind.WARNINGS:
            self.add_section_title(section.title)
            if not export_document.warning_rows:
                self.add_paragraph("Предупреждений нет.")
                return
            self.add_table(
                ("Уровень", "Источник", "Сообщение"),
                tuple(
                    (row.severity, row.target, row.message)
                    for row in export_document.warning_rows
                ),
            )
            return

        if section.kind is ExportSectionKind.FIELDS:
            self.add_section_title(section.title)
            if not export_document.field_rows:
                self.add_paragraph("Поля не извлечены.")
                return
            self.add_table(
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
            return

        if section.kind is ExportSectionKind.TABLES:
            self.add_section_title(section.title)
            if not export_document.table_sections:
                self.add_paragraph("Таблицы не извлечены.")
                return
            for index, table in enumerate(export_document.table_sections, start=1):
                title = table.title or f"Таблица {index}"
                self.add_subsection_title(f"Таблица {index} - {title}")
                if not table.rows:
                    self.add_paragraph("Строки таблицы не извлечены.")
                    continue
                columns = _table_columns(table.columns, table.rows)
                rows = tuple(_padded_cells(row.cells, len(columns)) for row in table.rows)
                self.add_table(columns, rows, font_size=8)
            return

        if section.kind is ExportSectionKind.RAW_TEXT:
            self.add_section_title(section.title)
            self.add_text_blocks(render_reconstructed_text_markdown(export_document))

    def add_heading(self, text: str, *, font_size: float) -> None:
        self.add_wrapped_text(text, font_size=font_size, line_height=font_size * 1.28)
        self.add_gap(6)

    def add_section_title(self, text: str) -> None:
        self.add_gap(8)
        self.add_wrapped_text(text, font_size=14, line_height=18)
        self.add_gap(4)

    def add_subsection_title(self, text: str) -> None:
        self.add_gap(5)
        self.add_wrapped_text(text, font_size=11, line_height=14)
        self.add_gap(3)

    def add_key_values(
        self,
        rows: Sequence[tuple[object | None, object | None]],
        *,
        font_size: float = 9,
    ) -> None:
        self.add_table(("Показатель", "Значение"), rows, font_size=font_size)

    def add_paragraph(self, text: str, *, font_size: float = 9) -> None:
        paragraphs = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        line_height = font_size * 1.32
        for index, paragraph in enumerate(paragraphs):
            if index and not paragraph.strip():
                self.add_gap(line_height * 0.5)
                continue
            self.add_wrapped_text(paragraph or " ", font_size=font_size, line_height=line_height)

    def add_text_blocks(self, text: str, *, font_size: float = 9) -> None:
        blocks = _parse_text_blocks(text)
        if not blocks:
            self.add_paragraph("Текст не извлечён.", font_size=font_size)
            return

        for index, block in enumerate(blocks):
            if index:
                self.add_gap(3)
            if isinstance(block, _TextParagraphBlock):
                self.add_paragraph("\n".join(block.lines), font_size=font_size)
                continue
            self.add_table(block.headers, block.rows, font_size=8)

    def add_table(
        self,
        headers: Sequence[object | None],
        rows: Sequence[Sequence[object | None]],
        *,
        font_size: float = 9,
    ) -> None:
        if not headers:
            return
        column_count = len(headers)
        column_width = _CONTENT_WIDTH / column_count
        widths = tuple(column_width for _ in headers)
        self._add_table_row(headers, widths, font_size=font_size, is_header=True)
        for row in rows:
            self._add_table_row(
                _padded_cells(row, column_count),
                widths,
                font_size=font_size,
                is_header=False,
            )
        self.add_gap(4)

    def _add_table_row(
        self,
        values: Sequence[object | None],
        widths: Sequence[float],
        *,
        font_size: float,
        is_header: bool,
    ) -> None:
        line_height = font_size * 1.25
        cell_lines = tuple(
            self._wrap_text(format_empty(value), max(12, width - _CELL_PADDING * 2), font_size)
            for value, width in zip(values, widths, strict=True)
        )
        row_height = max(len(lines) for lines in cell_lines) * line_height + _CELL_PADDING * 2
        self.ensure_space(row_height)
        page = self._page()
        x = _MARGIN_X
        row_top = self.y
        fill = (0.94, 0.97, 1.0) if is_header else None
        for lines, width in zip(cell_lines, widths, strict=True):
            rect = pymupdf.Rect(x, row_top, x + width, row_top + row_height)
            page.draw_rect(rect, color=(0.78, 0.83, 0.9), fill=fill, width=0.45)
            text_y = row_top + _CELL_PADDING + font_size
            for line in lines:
                page.insert_text(
                    pymupdf.Point(x + _CELL_PADDING, text_y),
                    line,
                    fontname=_FONT_NAME,
                    fontsize=font_size,
                    color=(0.09, 0.13, 0.2),
                )
                text_y += line_height
            x += width
        self.y += row_height

    def add_wrapped_text(
        self,
        text: str,
        *,
        font_size: float,
        line_height: float,
    ) -> None:
        for line in self._wrap_text(text, _CONTENT_WIDTH, font_size):
            self.ensure_space(line_height)
            self._page().insert_text(
                pymupdf.Point(_MARGIN_X, self.y + font_size),
                line,
                fontname=_FONT_NAME,
                fontsize=font_size,
                color=(0.09, 0.13, 0.2),
            )
            self.y += line_height

    def add_gap(self, height: float) -> None:
        self.ensure_space(height)
        self.y += height

    def ensure_space(self, height: float) -> None:
        if self.y + height <= _PAGE_HEIGHT - _MARGIN_BOTTOM:
            return
        self._new_page()

    def _new_page(self) -> None:
        self.page = self.document.new_page(width=_PAGE_WIDTH, height=_PAGE_HEIGHT)
        self.page.insert_font(fontname=_FONT_NAME, fontbuffer=self.font.buffer)
        self.y = _MARGIN_TOP

    def _page(self) -> pymupdf.Page:
        if self.page is None:
            self._new_page()
        if self.page is None:
            msg = "PDF page could not be initialized."
            raise PdfRenderError(msg)
        return self.page

    def _wrap_text(
        self,
        text: object,
        max_width: float,
        font_size: float,
    ) -> tuple[str, ...]:
        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
        lines: list[str] = []
        for source_line in normalized.split("\n"):
            words = source_line.split()
            if not words:
                lines.append(" ")
                continue

            current = ""
            for word in words:
                parts = self._split_token(word, max_width, font_size)
                for part in parts:
                    candidate = part if not current else f"{current} {part}"
                    if self._text_length(candidate, font_size) <= max_width:
                        current = candidate
                        continue
                    if current:
                        lines.append(current)
                    current = part
            if current:
                lines.append(current)
        return tuple(lines or (" ",))

    def _split_token(
        self,
        token: str,
        max_width: float,
        font_size: float,
    ) -> tuple[str, ...]:
        if self._text_length(token, font_size) <= max_width:
            return (token,)
        parts: list[str] = []
        current = ""
        for character in token:
            candidate = f"{current}{character}"
            if self._text_length(candidate, font_size) <= max_width:
                current = candidate
                continue
            if current:
                parts.append(current)
            current = character
        if current:
            parts.append(current)
        return tuple(parts or (token,))

    def _text_length(self, text: str, font_size: float) -> float:
        return self.font.text_length(text, fontsize=int(font_size))


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


def _parse_text_blocks(text: str) -> tuple[_TextBlock, ...]:
    source_lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    blocks: list[_TextBlock] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        while paragraph_lines and not paragraph_lines[0].strip():
            paragraph_lines.pop(0)
        while paragraph_lines and not paragraph_lines[-1].strip():
            paragraph_lines.pop()
        if paragraph_lines:
            blocks.append(
                _TextParagraphBlock(tuple(line.strip() for line in paragraph_lines)),
            )
        paragraph_lines.clear()

    index = 0
    while index < len(source_lines):
        line = source_lines[index]
        if _looks_like_pipe_row(line):
            table_lines: list[str] = []
            while index < len(source_lines) and _looks_like_pipe_row(source_lines[index]):
                table_lines.append(source_lines[index])
                index += 1

            table_block = _parse_pipe_table_block(table_lines)
            if table_block is None:
                paragraph_lines.extend(table_lines)
                continue

            flush_paragraph()
            blocks.append(table_block)
            continue

        if not line.strip():
            flush_paragraph()
            index += 1
            continue

        paragraph_lines.append(line)
        index += 1

    flush_paragraph()
    return tuple(blocks)


def _looks_like_pipe_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _parse_pipe_table_block(lines: Sequence[str]) -> _TextTableBlock | None:
    rows = tuple(_split_pipe_row(line) for line in lines)
    content_rows = tuple(row for row in rows if not _is_separator_row(row))
    if len(content_rows) < 2:
        return None

    column_count = max((len(row) for row in content_rows), default=0)
    if column_count < 2:
        return None

    headers = _padded_text_cells(content_rows[0], column_count)
    body_rows = tuple(_padded_cells(row, column_count) for row in content_rows[1:])
    return _TextTableBlock(headers=headers, rows=body_rows)


def _split_pipe_row(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for character in stripped:
        if escaped:
            current.append("|" if character == "|" else f"\\{character}")
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == "|":
            cells.append("".join(current).strip())
            current = []
            continue
        current.append(character)

    if escaped:
        current.append("\\")
    cells.append("".join(current).strip())
    return tuple(cells)


def _is_separator_row(row: Sequence[str]) -> bool:
    return bool(row) and all(_is_separator_cell(cell) for cell in row)


def _is_separator_cell(cell: str) -> bool:
    normalized = cell.strip()
    return len(normalized) >= 3 and "-" in normalized and normalized.strip("-:") == ""


def _padded_text_cells(cells: Sequence[str], expected_length: int) -> tuple[str, ...]:
    if len(cells) >= expected_length:
        return tuple(cells[:expected_length])
    return tuple(cells) + ("",) * (expected_length - len(cells))


_PAGE_WIDTH = 595.0
_PAGE_HEIGHT = 842.0
_MARGIN_X = 42.0
_MARGIN_TOP = 42.0
_MARGIN_BOTTOM = 42.0
_CONTENT_WIDTH = _PAGE_WIDTH - (_MARGIN_X * 2)
_CELL_PADDING = 4.0
_FONT_NAME = "F0"
