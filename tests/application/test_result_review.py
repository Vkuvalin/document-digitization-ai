from __future__ import annotations

from document_digitization_ai.application.result_review import (
    build_result_review_payload,
    derive_table_facts,
)
from document_digitization_ai.contracts import (
    DetectedDocumentType,
    DocumentInfo,
    DocumentModeHint,
    ExtractedField,
    ExtractedTable,
    ExtractionResult,
    FieldSource,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageShape,
    RawText,
    TableRow,
)


def test_derive_table_facts_from_two_column_label_value_table() -> None:
    result = _result(
        tables=(
            ExtractedTable(
                title="Prenatal labs",
                columns=("TEST", "RESULTS/RATIONALE"),
                rows=(
                    TableRow(cells=("Blood type and Rh", "A+ / absc")),
                    TableRow(cells=("Blood type and Rh", "A+ / absc")),
                    TableRow(cells=("Antibody Screen", "neg")),
                ),
            ),
        ),
    )

    facts = derive_table_facts(result)

    assert [(fact.label, fact.value) for fact in facts] == [
        ("Blood type and Rh", "A+ / absc"),
        ("Antibody Screen", "neg"),
    ]
    assert facts[0].source_table == "Prenatal labs"
    assert facts[0].source_row_index == 1
    assert facts[0].confidence is None


def test_derive_table_facts_from_multicolumn_lab_table_with_context_notes() -> None:
    result = _result(
        tables=(
            ExtractedTable(
                title="Lab tests done on baby",
                columns=("TEST", "REASON ORDERED", "DATE/TIME", "RESULTS"),
                rows=(
                    TableRow(
                        cells=("Bilirubin total", "Routine check", "01/31/22", "1.4"),
                        confidence=0.74,
                    ),
                ),
            ),
        ),
    )

    facts = derive_table_facts(result)

    assert len(facts) == 1
    assert facts[0].label == "Bilirubin total"
    assert facts[0].value == "1.4"
    assert facts[0].note == "REASON ORDERED: Routine check; DATE/TIME: 01/31/22"
    assert facts[0].confidence == 0.74


def test_derive_table_facts_skips_duplicates_with_standalone_fields() -> None:
    result = _result(
        fields=(
            ExtractedField(
                label="Blood type and Rh",
                value="A+ / absc",
                confidence=0.9,
                source=FieldSource.DETECTED,
            ),
        ),
        tables=(
            ExtractedTable(
                title="Prenatal labs",
                columns=("Test", "Result"),
                rows=(
                    TableRow(cells=("Blood type and Rh", "A+ / absc")),
                    TableRow(cells=("Antibody Screen", "neg")),
                ),
            ),
        ),
    )

    facts = derive_table_facts(result)

    assert [(fact.label, fact.value) for fact in facts] == [("Antibody Screen", "neg")]


def test_derive_table_facts_skips_unsafe_rows_and_ambiguous_tables() -> None:
    result = _result(
        tables=(
            ExtractedTable(
                title="Rows to skip",
                columns=("Field", "Value"),
                rows=(
                    TableRow(cells=("Field", "Value")),
                    TableRow(cells=("", "Present")),
                    TableRow(cells=("Status", "")),
                    TableRow(cells=("—", "—")),
                    TableRow(cells=("Same", "Same")),
                ),
            ),
            ExtractedTable(
                title="Ambiguous line items",
                columns=("Product", "Count", "Price", "Total"),
                rows=(TableRow(cells=("Apples", "3", "10", "30")),),
            ),
        ),
    )

    assert derive_table_facts(result) == ()


def test_build_result_review_payload_caps_derived_facts_without_mutating_result() -> None:
    result = _result(
        tables=(
            ExtractedTable(
                title="Many values",
                columns=("Field", "Value"),
                rows=(
                    TableRow(cells=("One", "1")),
                    TableRow(cells=("Two", "2")),
                    TableRow(cells=("Three", "3")),
                ),
            ),
        ),
    )
    original_tables = result.to_dict()["tables"]

    payload = build_result_review_payload(result, max_derived_facts=2)

    assert payload["derived_table_facts_limit"] == 2
    assert payload["derived_table_facts_truncated"] is True
    facts = payload["derived_table_facts"]
    assert isinstance(facts, list)
    assert [fact["label"] for fact in facts] == ["One", "Two"]
    assert result.to_dict()["tables"] == original_tables
    assert "review" not in result.to_dict()


def _result(
    *,
    fields: tuple[ExtractedField, ...] = (),
    tables: tuple[ExtractedTable, ...] = (),
) -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            language="en",
        ),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/jpeg",
                file_size_bytes=123,
                file_extension=".jpg",
            ),
            image=ImageShape.from_dimensions(width=120, height=120),
        ),
        raw_text=RawText(text="Text"),
        fields=fields,
        tables=tables,
    )
