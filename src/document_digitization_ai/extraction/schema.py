from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite

from document_digitization_ai.contracts import (
    DEFAULT_EXPECTED_RESULT_SHAPE,
    DEFAULT_PROVIDER_CONSTRAINTS,
    EXTRACTION_RESULT_SCHEMA_VERSION,
    ExpectedResultSection,
    ProviderConstraint,
)
from document_digitization_ai.core import ProviderSchemaMode
from document_digitization_ai.providers import ProviderInputContext


class ExtractionSchemaError(RuntimeError):
    """Raised when extraction schema package construction fails."""


@dataclass(frozen=True, slots=True)
class ExtractionSchemaPackage:
    schema_mode: ProviderSchemaMode
    target_schema_version: str
    required_sections: tuple[ExpectedResultSection, ...]
    schema_payload: Mapping[str, object]
    constraints: tuple[ProviderConstraint, ...] = field(
        default_factory=lambda: DEFAULT_PROVIDER_CONSTRAINTS
    )

    def __post_init__(self) -> None:
        if not isinstance(self.schema_mode, ProviderSchemaMode):
            msg = "schema_mode must be a ProviderSchemaMode value"
            raise ValueError(msg)
        _ensure_non_empty_text(self.target_schema_version, "target_schema_version")
        if not self.required_sections:
            msg = "required_sections must contain at least one section"
            raise ValueError(msg)
        for section in self.required_sections:
            if not isinstance(section, ExpectedResultSection):
                msg = "required_sections must contain ExpectedResultSection values"
                raise ValueError(msg)
        for constraint in self.constraints:
            if not isinstance(constraint, ProviderConstraint):
                msg = "constraints must contain ProviderConstraint values"
                raise ValueError(msg)
        _ensure_json_object(self.schema_payload, "schema_payload")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_mode": self.schema_mode.value,
            "target_schema_version": self.target_schema_version,
            "required_sections": [section.value for section in self.required_sections],
            "schema_payload": dict(self.schema_payload),
            "constraints": [constraint.value for constraint in self.constraints],
        }


def build_extraction_schema_package(
    context: ProviderInputContext,
) -> ExtractionSchemaPackage:
    if not isinstance(context, ProviderInputContext):
        msg = "context must be a ProviderInputContext value"
        raise ExtractionSchemaError(msg)

    schema_mode = context.extraction.provider_schema_mode
    if schema_mode is ProviderSchemaMode.COMPACT:
        payload = _build_compact_schema_payload()
    elif schema_mode is ProviderSchemaMode.FULL:
        payload = _build_full_schema_payload()
    else:
        msg = f"Unsupported provider schema mode: {schema_mode}"
        raise ExtractionSchemaError(msg)

    return ExtractionSchemaPackage(
        schema_mode=schema_mode,
        target_schema_version=EXTRACTION_RESULT_SCHEMA_VERSION,
        required_sections=DEFAULT_EXPECTED_RESULT_SHAPE,
        schema_payload=payload,
        constraints=DEFAULT_PROVIDER_CONSTRAINTS,
    )


def _build_compact_schema_payload() -> dict[str, object]:
    return {
        "schema_version": EXTRACTION_RESULT_SCHEMA_VERSION,
        "schema_detail": ProviderSchemaMode.COMPACT.value,
        "type": "object",
        "required": [section.value for section in DEFAULT_EXPECTED_RESULT_SHAPE],
        "sections": {
            "document": ["user_mode_hint", "detected_type", "language", "summary"],
            "image_diagnostics": "echo diagnostics-relevant warnings only when useful",
            "raw_text": ["text", "confidence", "warnings"],
            "fields": ["label", "value", "confidence", "source", "warnings"],
            "tables": ["title", "columns", "rows", "confidence", "warnings"],
            "blocks": ["type", "text", "order", "confidence", "warnings"],
            "warnings": ["code", "message", "severity", "target"],
            "metadata": ["schema_version", "provider", "model", "created_at"],
        },
        "provider_output_is_untrusted": True,
        "validation_owner": "backend",
    }


def _build_full_schema_payload() -> dict[str, object]:
    return {
        "schema_version": EXTRACTION_RESULT_SCHEMA_VERSION,
        "schema_detail": ProviderSchemaMode.FULL.value,
        "type": "object",
        "additionalProperties": False,
        "required": [section.value for section in DEFAULT_EXPECTED_RESULT_SHAPE],
        "properties": {
            "document": {
                "description": "Document-level interpretation; user mode hint is guidance only.",
                "required": [
                    "user_mode_hint",
                    "detected_type",
                    "detected_type_confidence",
                    "language",
                    "summary",
                ],
            },
            "image_diagnostics": {
                "description": "Diagnostics-aware context and warnings, not extracted text.",
            },
            "raw_text": {
                "description": "Best-effort visible text with confidence and warnings.",
                "required": ["text", "confidence", "warnings"],
            },
            "fields": {
                "description": "Visible label/value pairs with source, confidence, and warnings.",
                "items": ["label", "value", "confidence", "source", "warnings"],
            },
            "tables": {
                "description": "Visible tabular structures with columns, rows, confidence, warnings.",
                "items": ["title", "columns", "rows", "confidence", "warnings"],
            },
            "blocks": {
                "description": "Ordered text blocks such as headings, paragraphs, lists, or signatures.",
                "items": ["type", "text", "order", "level", "confidence", "warnings"],
            },
            "warnings": {
                "description": "Extraction uncertainty, quality, mismatch, or partial-result warnings.",
                "items": ["code", "message", "severity", "target"],
            },
            "metadata": {
                "description": "Result metadata for validation and traceability.",
                "required": ["schema_version", "provider", "model", "created_at"],
            },
        },
        "constraints": [constraint.value for constraint in DEFAULT_PROVIDER_CONSTRAINTS],
        "provider_output_is_untrusted": True,
        "validation_owner": "backend",
    }


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_json_object(value: Mapping[str, object], field_name: str) -> None:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be a JSON object"
        raise ValueError(msg)
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            msg = f"{field_name} keys must be non-empty strings"
            raise ValueError(msg)
        _ensure_json_compatible(item, f"{field_name}.{key}")


def _ensure_json_compatible(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not isfinite(value):
            msg = f"{field_name} must be finite"
            raise ValueError(msg)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_compatible(item, f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        _ensure_json_object(value, field_name)
        return
    msg = f"{field_name} must be JSON-compatible"
    raise ValueError(msg)
