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
    ExportSectionKind,
    build_extraction_result_export_document,
    markdown_table_cell,
    render_extraction_result_markdown,
)
from document_digitization_ai.export.models import STABLE_EXPORT_SECTIONS


def test_renderer_outputs_full_result_in_stable_section_order() -> None:
    export_document = build_extraction_result_export_document(_full_result())

    markdown = render_extraction_result_markdown(export_document)

    section_headers = [
        "## 1. Summary",
        "## 2. Warnings and Uncertainty",
        "## 3. Fields",
        "## 4. Tables",
        "## 5. Raw Text",
        "## 6. Text Blocks",
        "## 7. Image Diagnostics",
        "## 8. Extraction Metadata",
    ]
    positions = [markdown.index(header) for header in section_headers]
    assert positions == sorted(positions)
    assert markdown.startswith("# Document Extraction Result\n")
    assert markdown.endswith("\n")
    assert "| Severity | Code | Target | Message |" in markdown
    assert "| Label | Value | Confidence | Notes |" in markdown
    assert "### Table 1 — Line items" in markdown
    assert "### Table 2 — Totals" in markdown
    assert "Line one\nLine two" in markdown
    assert "| 1 | heading | Receipt heading | 0.95 |" in markdown
    assert "| Width | 120 |" in markdown
    assert "| Provider | fake |" in markdown


def test_empty_sections_render_controlled_empty_states() -> None:
    markdown = render_extraction_result_markdown(
        build_extraction_result_export_document(_empty_result())
    )

    assert "No warnings were reported." in markdown
    assert "No standalone fields were extracted." in markdown
    assert "No tables were extracted." in markdown
    assert "No raw text was extracted." in markdown
    assert "No text blocks were extracted." in markdown


def test_renderer_handles_empty_diagnostics_and_metadata_sections() -> None:
    markdown = render_extraction_result_markdown(
        ExportDocument(
            title="Document Extraction Result",
            sections=STABLE_EXPORT_SECTIONS,
        )
    )

    assert "No image diagnostics are available." in markdown
    assert "No extraction metadata is available." in markdown


def test_markdown_table_cells_are_escaped_and_tables_are_padded() -> None:
    markdown = render_extraction_result_markdown(
        build_extraction_result_export_document(_full_result())
    )

    assert markdown_table_cell("A|B\nC") == r"A\|B<br>C"
    assert markdown_table_cell(None) == "—"
    assert r"Account \| ID" in markdown
    assert r"A\|B<br>C" in markdown
    assert "| Short row | — | — |" in markdown
    assert "| Long row | 2 | Preserved extra value |" in markdown
    assert "| Product | Count | Column 3 |" in markdown


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


def test_export_document_has_stable_sections_and_structured_rows() -> None:
    export_document = build_extraction_result_export_document(_full_result())

    assert isinstance(export_document, ExportDocument)
    assert [section.id for section in export_document.sections] == [
        "summary",
        "warnings-and-uncertainty",
        "fields",
        "tables",
        "raw-text",
        "text-blocks",
        "image-diagnostics",
        "extraction-metadata",
    ]
    assert [section.kind for section in export_document.sections] == [
        ExportSectionKind.SUMMARY,
        ExportSectionKind.WARNINGS,
        ExportSectionKind.FIELDS,
        ExportSectionKind.TABLES,
        ExportSectionKind.RAW_TEXT,
        ExportSectionKind.TEXT_BLOCKS,
        ExportSectionKind.IMAGE_DIAGNOSTICS,
        ExportSectionKind.EXTRACTION_METADATA,
    ]
    assert export_document.warning_rows[0].code == "partial_extraction"
    assert export_document.field_rows[0].label == "Account | ID"
    assert export_document.table_sections[0].rows[2].cells[-1] == (
        "Preserved extra value"
    )


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
