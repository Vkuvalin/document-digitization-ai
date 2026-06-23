from __future__ import annotations

from document_digitization_ai.contracts import (
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
from document_digitization_ai.export import (
    ExportDocument,
    ExportSection,
    ExportSectionKind,
    build_extraction_result_export_document,
    count_extraction_result_warnings,
    markdown_table_cell,
    render_extraction_result_markdown,
    render_reconstructed_text_markdown,
)
from document_digitization_ai.export.models import STABLE_EXPORT_SECTIONS


def test_renderer_outputs_user_facing_result_without_internal_metadata() -> None:
    export_document = build_extraction_result_export_document(_full_result())

    markdown = render_extraction_result_markdown(export_document)

    section_headers = [
        "## Сводка",
        "## Предупреждения",
        "## Поля",
        "## Таблицы",
        "## Текст",
    ]
    positions = [markdown.index(header) for header in section_headers]
    assert positions == sorted(positions)
    assert markdown.startswith("# Результат анализа\n")
    assert markdown.endswith("\n")
    assert "| Показатель      | Значение   |" in markdown
    assert "| Тип документа   | Форма      |" in markdown
    assert "| Язык            | Русский    |" in markdown
    assert "| Уровень        | Источник    | Сообщение                      |" in markdown
    assert "| Предупреждение | Поля        | Некоторые значения не уверены. |" in markdown
    assert "| Поле          | Значение  | Уверенность | Примечания |" in markdown
    assert "### Таблица 1 — Line items" in markdown
    assert "### Таблица 2 — Totals" in markdown
    assert "Line one\nLine two" in markdown
    assert "Квитанция с позициями." not in markdown
    assert "### Receipt heading" not in markdown
    assert "Receipt body" not in markdown
    assert "```text" not in markdown
    assert "## Extraction Metadata" not in markdown
    assert "Provider" not in markdown
    assert "openai/test-vision" not in markdown
    assert "Job ID" not in markdown
    assert "Attempt ID" not in markdown
    assert "Image Diagnostics" not in markdown
    assert "Width" not in markdown
    assert "Text Blocks" not in markdown
    assert export_document.metadata_items
    assert export_document.diagnostics_items


def test_empty_sections_render_controlled_empty_states() -> None:
    markdown = render_extraction_result_markdown(
        build_extraction_result_export_document(_empty_result())
    )

    assert "Предупреждений нет." in markdown
    assert "Поля не извлечены." in markdown
    assert "Таблицы не извлечены." in markdown
    assert "Текст не извлечён." in markdown


def test_default_sections_do_not_render_diagnostics_or_metadata_empty_states() -> None:
    markdown = render_extraction_result_markdown(
        ExportDocument(
            title="Результат анализа",
            sections=STABLE_EXPORT_SECTIONS,
        )
    )

    assert "Сведения о качестве изображения недоступны." not in markdown
    assert "Метаданные извлечения недоступны." not in markdown


def test_internal_diagnostics_and_metadata_sections_still_render_when_requested() -> None:
    markdown = render_extraction_result_markdown(
        ExportDocument(
            title="Внутренний результат",
            sections=(
                ExportSection(
                    id="image-diagnostics",
                    title="Качество изображения",
                    kind=ExportSectionKind.IMAGE_DIAGNOSTICS,
                ),
                ExportSection(
                    id="extraction-metadata",
                    title="Метаданные извлечения",
                    kind=ExportSectionKind.EXTRACTION_METADATA,
                ),
            ),
        )
    )

    assert "Сведения о качестве изображения недоступны." in markdown
    assert "Метаданные извлечения недоступны." in markdown


def test_markdown_table_cells_are_escaped_and_tables_are_padded() -> None:
    markdown = render_extraction_result_markdown(
        build_extraction_result_export_document(_full_result())
    )

    assert markdown_table_cell("A|B\nC") == r"A\|B<br>C"
    assert markdown_table_cell(None) == "—"
    assert r"Account \| ID" in markdown
    assert r"A\|B<br>C" in markdown
    assert "| Product         | Count | Column 3              |" in markdown
    assert "| --------------- | ----- | --------------------- |" in markdown
    assert "| Short row       | —     | —                     |" in markdown
    assert "| Long row        | 2     | Preserved extra value |" in markdown
    assert "---:" not in markdown


def test_builder_filters_debug_and_sensitive_metadata() -> None:
    markdown = render_extraction_result_markdown(
        build_extraction_result_export_document(_full_result())
    )

    assert "OPENROUTER_API_KEY" not in markdown
    assert "Authorization" not in markdown
    assert "delete_url" not in markdown
    assert "delete/private" not in markdown
    assert r"C:\Users\User\image.jpg" not in markdown
    assert "/tmp/artifacts" not in markdown
    assert "raw_provider_response" not in markdown
    assert "provider_request" not in markdown
    assert "full prompt" not in markdown
    assert "sha-secret" not in markdown
    assert "fake-model-v0" not in markdown
    assert "openai/test-vision" not in markdown


def test_export_document_has_stable_sections_and_structured_rows() -> None:
    export_document = build_extraction_result_export_document(_full_result())

    assert isinstance(export_document, ExportDocument)
    assert [section.id for section in export_document.sections] == [
        "summary",
        "warnings-and-uncertainty",
        "fields",
        "tables",
        "raw-text",
    ]
    assert [section.kind for section in export_document.sections] == [
        ExportSectionKind.SUMMARY,
        ExportSectionKind.WARNINGS,
        ExportSectionKind.FIELDS,
        ExportSectionKind.TABLES,
        ExportSectionKind.RAW_TEXT,
    ]
    assert export_document.warning_rows[0].code == "partial_extraction"
    assert export_document.warning_rows[0].severity == "Предупреждение"
    assert export_document.warning_rows[0].target == "Поля"
    assert export_document.field_rows[0].label == "Account | ID"
    assert export_document.table_sections[0].rows[2].cells[-1] == (
        "Preserved extra value"
    )
    assert any(item.key == "Provider" for item in export_document.metadata_items)
    assert any(item.key == "Model" for item in export_document.metadata_items)


def test_warning_count_uses_all_exported_warning_sources() -> None:
    assert count_extraction_result_warnings(_full_result()) == 2


def test_reconstructed_text_preserves_raw_order_and_formats_pipe_fragments() -> None:
    result = _table_like_raw_result()
    export_document = build_extraction_result_export_document(result)

    reconstructed_text = render_reconstructed_text_markdown(export_document)
    markdown = render_extraction_result_markdown(export_document)

    assert reconstructed_text.startswith("Data Collection: Lab Tests")
    assert "### Поля" not in reconstructed_text
    assert "Document Title" not in reconstructed_text
    assert "Synthetic field value" not in reconstructed_text
    assert "### Prenatal labs" not in reconstructed_text
    assert "Prenatal labs (found on prenatal record, in chart, or computer)" in reconstructed_text
    assert "| Blood type and Rh" in reconstructed_text
    assert "| Hematocrit/Hemoglobin | —" in reconstructed_text
    assert (
        "Test | Results/Rationale\nBlood type and Rh | A+ / abc"
        not in reconstructed_text
    )
    assert reconstructed_text.index("Adapted from Newborn Assessment") > (
        reconstructed_text.index("| Hematocrit/Hemoglobin")
    )
    assert "```text" not in markdown
    assert "## Текст\n\nData Collection: Lab Tests" in markdown


def test_reconstructed_text_uses_structured_tables_for_flattened_raw_text() -> None:
    result = _flattened_table_raw_result()
    export_document = build_extraction_result_export_document(result)

    reconstructed_text = render_reconstructed_text_markdown(export_document)
    markdown = render_extraction_result_markdown(export_document)
    text_section = markdown.split("## Текст\n\n", maxsplit=1)[1].strip()

    assert text_section == reconstructed_text
    assert reconstructed_text.startswith("Data Collection: Lab Tests")
    assert "Form titled" not in reconstructed_text
    assert "### Поля" not in reconstructed_text
    assert "Document Title" not in reconstructed_text
    assert "Synthetic field value" not in reconstructed_text
    assert "### Prenatal labs" not in reconstructed_text
    assert "Prenatal labs (found on prenatal record, in chart, or computer)" in reconstructed_text
    assert "| Test" in reconstructed_text
    assert "Results/Rationale |" in reconstructed_text
    assert "| Blood type and Rh" in reconstructed_text
    assert "A+ / abc" in reconstructed_text
    assert "| Hematocrit/Hemoglobin | —" in reconstructed_text
    assert "| Test" in reconstructed_text
    assert "Reason Ordered | Date/Time | Results |" in reconstructed_text
    assert "| Bilirubin total" in reconstructed_text
    assert "01/31/22  | 1.4" in reconstructed_text
    assert "Test Results/Rationale\nBlood type and Rh A+ / abc" not in reconstructed_text
    assert (
        "Test Reason Ordered Date/Time Results\nBilirubin total 01/31/22 1.4"
        not in reconstructed_text
    )
    assert reconstructed_text.index("Lab tests done on baby") > (
        reconstructed_text.index("| Hematocrit/Hemoglobin")
    )
    assert reconstructed_text.index("| Bilirubin total") > (
        reconstructed_text.index("Lab tests done on baby")
    )


def test_reconstructed_text_replaces_fuzzy_flattened_table_without_duplication() -> None:
    result = _fuzzy_flattened_table_raw_result()
    export_document = build_extraction_result_export_document(result)

    reconstructed_text = render_reconstructed_text_markdown(export_document)

    assert "Проведены лабораторные анализы у ребенка" in reconstructed_text
    assert "| Тест" in reconstructed_text
    assert "Дата/время" in reconstructed_text
    assert "Результаты |" in reconstructed_text
    assert "| Общий билирубин" in reconstructed_text
    assert "31.01.22" in reconstructed_text
    assert "1.4" in reconstructed_text
    assert "Причина проведения теста Дата/время Результаты" not in reconstructed_text
    assert "Общий билирубин 31.01.2022: 1,4" not in reconstructed_text
    assert reconstructed_text.count("Общий билирубин") == 1
    assert reconstructed_text.count("С-реактивный белок") == 1
    assert "### Поля" not in reconstructed_text


def test_reconstructed_text_falls_back_to_raw_when_structured_data_is_missing() -> None:
    result = ExtractionResult(
        document=DocumentInfo(user_mode_hint=DocumentModeHint.AUTO),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/png",
                file_size_bytes=1,
                file_extension=".png",
            ),
            image=ImageShape.from_dimensions(width=1, height=1),
        ),
        raw_text=RawText(text="Only raw text\nSecond line"),
    )

    reconstructed_text = render_reconstructed_text_markdown(
        build_extraction_result_export_document(result)
    )

    assert reconstructed_text == "Only raw text\nSecond line"


def _full_result() -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            detected_type_confidence=0.93,
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
            image=ImageShape.from_dimensions(
                width=120,
                height=180,
                color_mode="RGB",
                format="JPEG",
            ),
            quality=ImageQualityIndicators(
                blur_score=1.2,
                sharpness_score=9.4,
                brightness=128.0,
                contrast=42.0,
                is_low_resolution=False,
                is_probably_blurry=False,
                is_low_contrast=False,
            ),
            warnings=(
                Warning(
                    code=WarningCode.LOW_CONTRAST,
                    message="Контраст ниже ожидаемого.",
                    target="image",
                ),
            ),
            metadata={
                "schema_version": "image_diagnostics_v0",
                "api_key": "OPENROUTER_API_KEY=secret",
                "authorization": "Authorization: Bearer secret",
                "delete_url": "https://ibb.co/delete/private",
                "source_image_path": r"C:\Users\User\image.jpg",
                "artifact_root": "/tmp/artifacts",
            },
        ),
        raw_text=RawText(text="Line one\nLine two", confidence=0.91),
        fields=(
            ExtractedField(
                label="Account | ID",
                value="A|B\nC",
                confidence=0.82,
                source=FieldSource.DETECTED,
            ),
        ),
        tables=(
            ExtractedTable(
                title="Line items",
                columns=("Product", "Count"),
                rows=(
                    TableRow(cells=("Apples | green", "3")),
                    TableRow(cells=("Short row",)),
                    TableRow(cells=("Long row", "2", "Preserved extra value")),
                ),
                confidence=0.88,
            ),
            ExtractedTable(
                title="Totals",
                columns=("Label", "Value"),
                rows=(TableRow(cells=("Total", "100")),),
            ),
        ),
        blocks=(
            TextBlock(
                type=BlockType.PARAGRAPH,
                text="Receipt body",
                order=2,
                confidence=0.75,
            ),
            TextBlock(
                type=BlockType.HEADING,
                text="Receipt heading",
                order=1,
                confidence=0.95,
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


def _table_like_raw_result() -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            language="en",
            summary="Data Collection: Lab Tests",
        ),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/jpeg",
                file_size_bytes=2048,
                file_extension=".jpg",
            ),
            image=ImageShape.from_dimensions(width=120, height=180),
        ),
        raw_text=RawText(
            text=(
                "Data Collection: Lab Tests\n"
                "\n"
                "Prenatal labs (found on prenatal record, in chart, or computer)\n"
                "\n"
                "Test | Results/Rationale\n"
                "Blood type and Rh | A+ / abc\n"
                "Antibody Screen | neg\n"
                "Hematocrit/Hemoglobin |\n"
                "\n"
                "Adapted from Newborn Assessment Care Plan created by S. Winn-Corey "
                "5/2014, used with permission."
            )
        ),
        fields=(
            ExtractedField(
                label="Document Title",
                value="Synthetic field value",
                source=FieldSource.DETECTED,
            ),
        ),
        tables=(
            ExtractedTable(
                title="Prenatal labs",
                columns=("Test", "Results/Rationale"),
                rows=(
                    TableRow(cells=("Blood type and Rh", "A+ / abc")),
                    TableRow(cells=("Antibody Screen", "neg")),
                ),
            ),
        ),
    )


def _flattened_table_raw_result() -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            language="en",
            summary="Data Collection: Lab Tests",
        ),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/jpeg",
                file_size_bytes=2048,
                file_extension=".jpg",
            ),
            image=ImageShape.from_dimensions(width=120, height=180),
        ),
        raw_text=RawText(
            text=(
                "Data Collection: Lab Tests\n"
                "\n"
                "Prenatal labs (found on prenatal record, in chart, or computer)\n"
                "\n"
                "Test Results/Rationale\n"
                "Blood type and Rh A+ / abc\n"
                "Antibody Screen neg\n"
                "Hematocrit/Hemoglobin\n"
                "\n"
                "Lab tests done on baby (e.g. glucose, bilirubin, etc.). "
                "State rationale for labs ordered.\n"
                "\n"
                "Test Reason Ordered Date/Time Results\n"
                "Bilirubin total 01/31/22 1.4\n"
                "--- direct 1/31/22 0.3\n"
                "CBC CRP\n"
                "CRP 1/31/22 < 0.3"
            )
        ),
        fields=(
            ExtractedField(
                label="Document Title",
                value="Synthetic field value",
                source=FieldSource.DETECTED,
            ),
        ),
        tables=(
            ExtractedTable(
                title="Prenatal labs",
                columns=("Test", "Results/Rationale"),
                rows=(
                    TableRow(cells=("Blood type and Rh", "A+ / abc")),
                    TableRow(cells=("Antibody Screen", "neg")),
                    TableRow(cells=("Hematocrit/Hemoglobin",)),
                ),
            ),
            ExtractedTable(
                title="Lab tests",
                columns=("Test", "Reason Ordered", "Date/Time", "Results"),
                rows=(
                    TableRow(cells=("Bilirubin total", "", "01/31/22", "1.4")),
                    TableRow(cells=("--- direct", "", "1/31/22", "0.3")),
                    TableRow(cells=("CBC CRP",)),
                    TableRow(cells=("CRP", "", "1/31/22", "< 0.3")),
                ),
            ),
        ),
    )


def _fuzzy_flattened_table_raw_result() -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            language="ru",
            summary="Лабораторные анализы",
        ),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/png",
                file_size_bytes=2048,
                file_extension=".png",
            ),
            image=ImageShape.from_dimensions(width=120, height=180),
        ),
        raw_text=RawText(
            text=(
                "Проведены лабораторные анализы у ребенка (например, уровень "
                "глюкозы, билирубина и т. д.). Обоснуйте назначение этих анализов.\n"
                "\n"
                "Причина проведения теста Дата/время Результаты\n"
                "Общий билирубин 31.01.2022: 1,4\n"
                "--- dwd 11/31/22 0.3\n"
                "... влажный 31.01.22 17.1 (H)\n"
                ". POCT 31.01.22 91 мг/дл\n"
                "CBC CRP\n"
                "глюкоза\n"
                "С-реактивный белок 31.01.2022 < 0,3\n"
                "Посев крови на стрептококк группы B 1/25"
            )
        ),
        tables=(
            ExtractedTable(
                title="Лабораторные анализы",
                columns=("Тест", "Причина заказа", "Дата/время", "Результаты"),
                rows=(
                    TableRow(cells=("Общий билирубин", "", "31.01.22", "1.4")),
                    TableRow(cells=("--- dwd", "", "11/31/22", "0.3")),
                    TableRow(cells=("... влажный", "", "31.01.22", "17.1 (H)")),
                    TableRow(cells=(". POCT", "", "31.01.22", "91 мг/дл")),
                    TableRow(cells=("CBC CRP",)),
                    TableRow(cells=("глюкоза",)),
                    TableRow(cells=("С-реактивный белок", "", "31.01.22", "< 0.3")),
                    TableRow(cells=("Посев крови", "1/25", "стрептококк группы B")),
                ),
            ),
        ),
    )


def _empty_result() -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(user_mode_hint=DocumentModeHint.AUTO),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/png",
                file_size_bytes=1,
                file_extension=".png",
            ),
            image=ImageShape.from_dimensions(width=1, height=1),
        ),
        raw_text=RawText(text=""),
    )
