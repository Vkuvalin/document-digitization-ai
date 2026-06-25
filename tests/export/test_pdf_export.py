from __future__ import annotations

from typing import cast

import pymupdf

from document_digitization_ai.contracts import (
    DetectedDocumentType,
    DocumentInfo,
    DocumentModeHint,
    ExtractedField,
    ExtractedTable,
    ExtractionMetadata,
    ExtractionResult,
    FieldSource,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageShape,
    RawText,
    TableRow,
    Warning,
    WarningCode,
    WarningSeverity,
)
from document_digitization_ai.export import (
    build_extraction_result_export_document,
    render_extraction_result_pdf,
)


def test_pdf_renderer_outputs_user_facing_sections_with_cyrillic_text() -> None:
    export_document = build_extraction_result_export_document(_representative_result())

    pdf = render_extraction_result_pdf(
        export_document,
        job_reference="job-pdf-001",
    )
    text = _pdf_text(pdf)

    assert pdf.startswith(b"%PDF")
    assert "Результат анализа" in text
    assert "Задание" in text
    assert "job-pdf-001" in text
    assert "Сводка" in text
    assert "Тип документа" in text
    assert "Форма" in text
    assert "Язык" in text
    assert "Русский" in text
    assert "Предупреждения" in text
    assert "Некоторые значения не уверены." in text
    assert "Поля" in text
    assert "Номер счёта" in text
    assert "Таблицы" in text
    assert "Line items" in text
    assert "Яблоки" in text
    assert "Текст" in text
    assert "Пользовательский текст результата." in text


def test_pdf_renderer_renders_text_markdown_tables_as_pdf_tables() -> None:
    raw_text = "\n".join(
        (
            "Перед таблицей.",
            "",
            "| Тест | Результат | Комментарий |",
            "| --- | --- | --- |",
            "| OCR | Да | Длинная ячейка должна переноситься внутри PDF-таблицы. |",
            "| Пустое поле | | Значение после пустой ячейки |",
            "",
            "После таблицы.",
        ),
    )
    export_document = build_extraction_result_export_document(
        _representative_result(raw_text=raw_text, tables=()),
    )

    text = _pdf_text(render_extraction_result_pdf(export_document))

    assert "Перед таблицей." in text
    assert "Тест" in text
    assert "Результат" in text
    assert "OCR" in text
    assert "Длинная ячейка должна переноситься" in text
    assert "—" in text
    assert "После таблицы." in text
    assert "| Тест | Результат | Комментарий |" not in text
    assert text.index("Перед таблицей.") < text.index("Тест") < text.index("После таблицы.")


def test_pdf_renderer_excludes_internal_debug_and_provider_metadata() -> None:
    export_document = build_extraction_result_export_document(_representative_result())

    text = _pdf_text(render_extraction_result_pdf(export_document))

    assert "Extraction Metadata" not in text
    assert "Provider" not in text
    assert "Model" not in text
    assert "openai/test-vision" not in text
    assert "Job ID" not in text
    assert "Attempt ID" not in text
    assert "provider_sanitized_response" not in text
    assert "raw_provider_response" not in text
    assert "C:\\Users" not in text
    assert "/tmp/artifacts" not in text


def _pdf_text(pdf: bytes) -> str:
    document = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        return "\n".join(cast(str, page.get_text()) for page in document)
    finally:
        document.close()


def _representative_result(
    *,
    raw_text: str = "Пользовательский текст результата.",
    tables: tuple[ExtractedTable, ...] | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            language="ru",
            summary="Квитанция с позициями.",
        ),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/jpeg",
                file_size_bytes=2048,
                file_extension=".jpg",
                sha256="sha-secret",
            ),
            image=ImageShape.from_dimensions(width=120, height=180),
            metadata={
                "source_image_path": r"C:\Users\User\image.jpg",
                "artifact_root": "/tmp/artifacts",
            },
        ),
        raw_text=RawText(text=raw_text),
        fields=(
            ExtractedField(
                label="Номер счёта",
                value="A-100",
                confidence=0.82,
                source=FieldSource.DETECTED,
            ),
        ),
        tables=tables
        if tables is not None
        else (
            ExtractedTable(
                title="Line items",
                columns=("Продукт", "Количество"),
                rows=(
                    TableRow(cells=("Яблоки", "3")),
                    TableRow(cells=("Пустая ячейка", "")),
                ),
            ),
        ),
        warnings=(
            Warning(
                code=WarningCode.PARTIAL_EXTRACTION,
                message="Некоторые значения не уверены.",
                severity=WarningSeverity.WARNING,
                target="fields",
            ),
        ),
        metadata=ExtractionMetadata(
            provider="fake",
            model="openai/test-vision",
        ),
    )
