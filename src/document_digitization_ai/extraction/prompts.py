from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite

from document_digitization_ai.contracts import (
    DEFAULT_EXPECTED_RESULT_SHAPE,
    EXTRACTION_RESULT_SCHEMA_VERSION,
    DocumentModeHint,
)
from document_digitization_ai.providers import ProviderInputContext


MODE_GUIDANCE: Mapping[DocumentModeHint, str] = {
    DocumentModeHint.AUTO: (
        "Infer the visible document structure carefully; treat the user mode hint "
        "as guidance, not truth."
    ),
    DocumentModeHint.FORM: (
        "Bias extraction toward visible label/value pairs, but do not force form "
        "output when the image contradicts the hint."
    ),
    DocumentModeHint.TABLE: (
        "Bias extraction toward visible tabular structure, preserving rows, "
        "columns, and uncertain cells where possible."
    ),
    DocumentModeHint.FREE_HANDWRITTEN_TEXT: (
        "Bias extraction toward reading order and uncertainty preservation for "
        "handwritten free text."
    ),
    DocumentModeHint.MIXED_DOCUMENT: (
        "Allow fields, tables, and free-text blocks to coexist when visible in "
        "the document."
    ),
    DocumentModeHint.PLAIN_TEXT: (
        "Bias extraction toward raw text and ordered text blocks, while still "
        "reporting visible structure when present."
    ),
}

DIAGNOSTIC_WARNING_GUIDANCE: Mapping[str, str] = {
    "low_resolution": (
        "Diagnostics indicate low resolution; preserve uncertainty for small or "
        "unclear text."
    ),
    "low_contrast": (
        "Diagnostics indicate low contrast; mark unclear text or values instead "
        "of guessing."
    ),
    "too_dark": (
        "Diagnostics indicate a dark image; avoid overconfident extraction where "
        "content is hard to see."
    ),
    "too_bright": (
        "Diagnostics indicate a bright image; avoid overconfident extraction "
        "where content is washed out."
    ),
    "exif_orientation_present": (
        "Diagnostics include EXIF orientation metadata; consider visible "
        "orientation carefully without treating metadata as extracted content."
    ),
}


class ExtractionPromptError(RuntimeError):
    """Raised when extraction prompt package construction fails."""


@dataclass(frozen=True, slots=True)
class ExtractionPromptPackage:
    system_instruction: str
    task_instruction: str
    document_mode_guidance: str
    diagnostics_guidance: tuple[str, ...]
    output_requirements: tuple[str, ...]
    uncertainty_guidance: tuple[str, ...]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.system_instruction, "system_instruction")
        _ensure_non_empty_text(self.task_instruction, "task_instruction")
        _ensure_non_empty_text(self.document_mode_guidance, "document_mode_guidance")
        _ensure_non_empty_tuple(self.diagnostics_guidance, "diagnostics_guidance")
        _ensure_non_empty_tuple(self.output_requirements, "output_requirements")
        _ensure_non_empty_tuple(self.uncertainty_guidance, "uncertainty_guidance")
        _ensure_json_object(self.metadata, "metadata")

    def to_dict(self) -> dict[str, object]:
        return {
            "system_instruction": self.system_instruction,
            "task_instruction": self.task_instruction,
            "document_mode_guidance": self.document_mode_guidance,
            "diagnostics_guidance": list(self.diagnostics_guidance),
            "output_requirements": list(self.output_requirements),
            "uncertainty_guidance": list(self.uncertainty_guidance),
            "metadata": dict(self.metadata),
        }


def build_extraction_prompt_package(
    context: ProviderInputContext,
) -> ExtractionPromptPackage:
    if not isinstance(context, ProviderInputContext):
        msg = "context must be a ProviderInputContext value"
        raise ExtractionPromptError(msg)

    mode_hint = context.document_mode_hint
    warning_codes = tuple(warning.code for warning in context.diagnostics.warnings)
    return ExtractionPromptPackage(
        system_instruction=(
            "You extract structured information from a single document image. "
            "Return only information visible in the image and keep uncertainty explicit."
        ),
        task_instruction=(
            "Extract document information, raw text, fields, tables, text blocks, "
            "warnings, and metadata according to the requested internal result shape."
        ),
        document_mode_guidance=MODE_GUIDANCE[mode_hint],
        diagnostics_guidance=_build_diagnostics_guidance(warning_codes),
        output_requirements=_build_output_requirements(),
        uncertainty_guidance=(
            "Do not invent text, labels, values, rows, columns, dates, totals, or signatures.",
            "Use explicit warnings for unreadable, ambiguous, partial, or contradictory content.",
            "Treat provider output as draft structured data that backend validation will check later.",
        ),
        metadata={
            "prompt_package_version": "extraction_prompt_v0",
            "target_schema_version": EXTRACTION_RESULT_SCHEMA_VERSION,
            "document_mode_hint": mode_hint.value,
            "diagnostics_warning_codes": list(warning_codes),
        },
    )


def _build_diagnostics_guidance(warning_codes: tuple[str, ...]) -> tuple[str, ...]:
    guidance: list[str] = [
        "Use diagnostics warnings only as image-quality guidance, not as extraction results."
    ]
    seen_codes: set[str] = set()
    for code in warning_codes:
        if code in seen_codes:
            continue
        seen_codes.add(code)
        mapped_guidance = DIAGNOSTIC_WARNING_GUIDANCE.get(code)
        if mapped_guidance is not None:
            guidance.append(mapped_guidance)
    if len(guidance) == 1 and warning_codes:
        guidance.append(
            "Diagnostics contain warnings; keep uncertain extraction explicit."
        )
    if not warning_codes:
        guidance.append("No image diagnostics warnings are present in the context.")
    return tuple(guidance)


def _build_output_requirements() -> tuple[str, ...]:
    section_names = ", ".join(section.value for section in DEFAULT_EXPECTED_RESULT_SHAPE)
    return (
        f"Target internal result schema: {EXTRACTION_RESULT_SCHEMA_VERSION}.",
        f"Expected top-level sections: {section_names}.",
        "Represent forms as fields, visible grids as tables, and ordered prose as blocks.",
        "Include warnings and metadata rather than silently dropping uncertain content.",
    )


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_non_empty_tuple(values: tuple[str, ...], field_name: str) -> None:
    if not values:
        msg = f"{field_name} must contain at least one item"
        raise ValueError(msg)
    for value in values:
        _ensure_non_empty_text(value, field_name)


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
