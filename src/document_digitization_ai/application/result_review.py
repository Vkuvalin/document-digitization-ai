from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from document_digitization_ai.contracts import (
    ExtractedTable,
    ExtractionResult,
    TableRow,
)

DEFAULT_DERIVED_TABLE_FACT_LIMIT = 50
_MAX_DERIVABLE_COLUMNS = 8
_SEPARATOR_RE = re.compile(r"^[\s\-—–_=|:.;,]+$")

_LABEL_COLUMN_KEYS = {
    "field",
    "item",
    "label",
    "name",
    "parameter",
    "test",
    "имя",
    "название",
    "показатель",
    "поле",
    "тест",
}

_VALUE_COLUMN_KEYS = {
    "answer",
    "rationale",
    "result",
    "results",
    "resultsrationale",
    "status",
    "value",
    "значение",
    "ответ",
    "результат",
    "статус",
}


@dataclass(frozen=True, slots=True)
class DerivedTableFact:
    label: str
    value: str
    source_table: str
    source_row_index: int
    note: str | None = None
    confidence: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "label": self.label,
            "value": self.value,
            "source": "table",
            "source_table": self.source_table,
            "source_row_index": self.source_row_index,
            "note": self.note,
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class _ColumnPlan:
    label_index: int
    value_index: int
    note_indexes: tuple[int, ...] = ()


def build_result_review_payload(
    result: ExtractionResult,
    *,
    max_derived_facts: int = DEFAULT_DERIVED_TABLE_FACT_LIMIT,
) -> dict[str, object]:
    facts, truncated = _derive_table_facts_with_limit(
        result,
        max_derived_facts=max_derived_facts,
    )
    return {
        "derived_table_facts": [fact.to_dict() for fact in facts],
        "derived_table_facts_limit": max_derived_facts,
        "derived_table_facts_truncated": truncated,
    }


def derive_table_facts(
    result: ExtractionResult,
    *,
    max_derived_facts: int = DEFAULT_DERIVED_TABLE_FACT_LIMIT,
) -> tuple[DerivedTableFact, ...]:
    facts, _truncated = _derive_table_facts_with_limit(
        result,
        max_derived_facts=max_derived_facts,
    )
    return facts


def _derive_table_facts_with_limit(
    result: ExtractionResult,
    *,
    max_derived_facts: int,
) -> tuple[tuple[DerivedTableFact, ...], bool]:
    if max_derived_facts < 1:
        return (), bool(result.tables)

    seen_fact_keys = {
        (_similarity_key(field.label), _similarity_key(field.value))
        for field in result.fields
        if field.label.strip() and field.value.strip()
    }
    facts: list[DerivedTableFact] = []
    for table_index, table in enumerate(result.tables):
        plan = _column_plan(table)
        if plan is None:
            continue
        source_table = table.title or f"Таблица {table_index + 1}"
        for row_index, row in enumerate(table.rows, start=1):
            fact = _derive_fact_from_row(
                table,
                row,
                row_index=row_index,
                source_table=source_table,
                plan=plan,
            )
            if fact is None:
                continue
            key = (_similarity_key(fact.label), _similarity_key(fact.value))
            if key in seen_fact_keys:
                continue
            if len(facts) >= max_derived_facts:
                return tuple(facts), True
            facts.append(fact)
            seen_fact_keys.add(key)
    return tuple(facts), False


def _column_plan(table: ExtractedTable) -> _ColumnPlan | None:
    column_count = len(table.columns)
    if column_count < 2 or column_count > _MAX_DERIVABLE_COLUMNS:
        return None

    if column_count == 2:
        first_is_label = _is_label_column(table.columns[0])
        second_is_value = _is_value_column(table.columns[1])
        if not first_is_label and not second_is_value:
            return None
        return _ColumnPlan(label_index=0, value_index=1)

    label_indexes = tuple(
        index for index, column in enumerate(table.columns) if _is_label_column(column)
    )
    value_indexes = tuple(
        index for index, column in enumerate(table.columns) if _is_value_column(column)
    )
    if len(label_indexes) != 1 or len(value_indexes) != 1:
        return None
    label_index = label_indexes[0]
    value_index = value_indexes[0]
    if label_index == value_index:
        return None

    note_indexes = tuple(
        index
        for index in range(column_count)
        if index not in {label_index, value_index}
    )
    return _ColumnPlan(
        label_index=label_index,
        value_index=value_index,
        note_indexes=note_indexes,
    )


def _derive_fact_from_row(
    table: ExtractedTable,
    row: TableRow,
    *,
    row_index: int,
    source_table: str,
    plan: _ColumnPlan,
) -> DerivedTableFact | None:
    label = _row_cell(row, plan.label_index)
    value = _row_cell(row, plan.value_index)
    if _is_useless_text(label) or _is_useless_text(value):
        return None
    if _similarity_key(label) == _similarity_key(value):
        return None
    if _looks_like_header_row(table, label, value, plan):
        return None

    notes = []
    for note_index in plan.note_indexes:
        note_value = _row_cell(row, note_index)
        if _is_useless_text(note_value):
            continue
        notes.append(f"{table.columns[note_index].strip()}: {note_value}")

    confidence = row.confidence if row.confidence is not None else table.confidence
    return DerivedTableFact(
        label=label,
        value=value,
        source_table=source_table,
        source_row_index=row_index,
        note="; ".join(notes) if notes else None,
        confidence=confidence,
    )


def _row_cell(row: TableRow, index: int) -> str:
    if index >= len(row.cells):
        return ""
    return row.cells[index].strip()


def _looks_like_header_row(
    table: ExtractedTable,
    label: str,
    value: str,
    plan: _ColumnPlan,
) -> bool:
    return (
        _similarity_key(label) == _similarity_key(table.columns[plan.label_index])
        and _similarity_key(value) == _similarity_key(table.columns[plan.value_index])
    )


def _is_label_column(value: str) -> bool:
    return _column_key(value) in _LABEL_COLUMN_KEYS


def _is_value_column(value: str) -> bool:
    return _column_key(value) in _VALUE_COLUMN_KEYS


def _is_useless_text(value: str) -> bool:
    text = value.strip()
    return not text or bool(_SEPARATOR_RE.fullmatch(text))


def _column_key(value: str) -> str:
    return _similarity_key(value)


def _similarity_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(character for character in normalized if character.isalnum())
