from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from math import isfinite
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.core import ExtractionSettings, ProviderSchemaMode, SettingsError

if TYPE_CHECKING:
    from document_digitization_ai.db import DocumentJob


class ProviderInputContextError(RuntimeError):
    """Base error for provider input context construction failures."""


class ProviderInputContextLifecycleError(ProviderInputContextError):
    """Raised when job lifecycle does not allow provider context construction."""


class ProviderInputContextStateError(ProviderInputContextError):
    """Raised when required persisted/local state is missing or invalid."""


class ProviderInputContextSettingsError(ProviderInputContextError):
    """Raised when extraction settings are insufficient for provider context."""


class SupportsToDict(Protocol):
    def to_dict(self) -> dict[str, object]: ...


@dataclass(frozen=True, slots=True)
class ProviderImageInput:
    local_path: Path
    mime_type: str
    file_size_bytes: int
    width: int | None = None
    height: int | None = None
    sha256: str | None = None

    def __post_init__(self) -> None:
        _ensure_non_empty_text(str(self.local_path), "local_path")
        _ensure_non_empty_text(self.mime_type, "mime_type")
        _ensure_positive_int(self.file_size_bytes, "file_size_bytes")
        _ensure_optional_positive_int(self.width, "width")
        _ensure_optional_positive_int(self.height, "height")
        _ensure_optional_non_empty_text(self.sha256, "sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "local_path": str(self.local_path),
            "mime_type": self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "width": self.width,
            "height": self.height,
            "sha256": self.sha256,
        }


@dataclass(frozen=True, slots=True)
class ProviderDiagnosticWarning:
    code: str
    message: str
    severity: str
    target: str | None = None

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.code, "code")
        _ensure_non_empty_text(self.message, "message")
        _ensure_non_empty_text(self.severity, "severity")
        _ensure_optional_non_empty_text(self.target, "target")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "target": self.target,
        }


@dataclass(frozen=True, slots=True)
class ProviderDiagnosticsSummary:
    diagnostics_present: bool
    warnings: tuple[ProviderDiagnosticWarning, ...]
    brightness: float | None = None
    contrast: float | None = None
    is_low_resolution: bool | None = None
    is_low_contrast: bool | None = None
    exif_orientation: int | None = None
    schema_version: str | None = None
    diagnostics_version: str | None = None

    def __post_init__(self) -> None:
        if self.diagnostics_present is not True:
            msg = "diagnostics_present must be true for built provider contexts"
            raise ValueError(msg)
        for warning in self.warnings:
            if not isinstance(warning, ProviderDiagnosticWarning):
                msg = "warnings must contain ProviderDiagnosticWarning values"
                raise ValueError(msg)
        _ensure_optional_number(self.brightness, "brightness")
        _ensure_optional_number(self.contrast, "contrast")
        _ensure_optional_positive_int(self.exif_orientation, "exif_orientation")
        _ensure_optional_non_empty_text(self.schema_version, "schema_version")
        _ensure_optional_non_empty_text(self.diagnostics_version, "diagnostics_version")

    def to_dict(self) -> dict[str, object]:
        return {
            "diagnostics_present": self.diagnostics_present,
            "warnings": [warning.to_dict() for warning in self.warnings],
            "brightness": self.brightness,
            "contrast": self.contrast,
            "is_low_resolution": self.is_low_resolution,
            "is_low_contrast": self.is_low_contrast,
            "exif_orientation": self.exif_orientation,
            "schema_version": self.schema_version,
            "diagnostics_version": self.diagnostics_version,
        }


@dataclass(frozen=True, slots=True)
class ProviderExtractionRuntimeSettings:
    model: str
    temperature: float
    timeout_seconds: int
    max_retries: int
    provider_schema_mode: ProviderSchemaMode
    structured_outputs_enabled: bool
    structured_outputs_require_parameters: bool

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.model, "model")
        if not isinstance(self.provider_schema_mode, ProviderSchemaMode):
            msg = "provider_schema_mode must be a ProviderSchemaMode value"
            raise ValueError(msg)
        _ensure_non_negative_number(self.temperature, "temperature")
        _ensure_positive_int(self.timeout_seconds, "timeout_seconds")
        _ensure_non_negative_int(self.max_retries, "max_retries")

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "provider_schema_mode": self.provider_schema_mode.value,
            "structured_outputs_enabled": self.structured_outputs_enabled,
            "structured_outputs_require_parameters": (
                self.structured_outputs_require_parameters
            ),
        }


@dataclass(frozen=True, slots=True)
class ProviderInputContext:
    job_id: str
    job_status: JobStatus
    document_mode_hint: DocumentModeHint
    image: ProviderImageInput
    diagnostics: ProviderDiagnosticsSummary
    extraction: ProviderExtractionRuntimeSettings
    staged_media: SupportsToDict | None = None

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.job_id, "job_id")
        if not isinstance(self.job_status, JobStatus):
            msg = "job_status must be a JobStatus value"
            raise ValueError(msg)
        if not isinstance(self.document_mode_hint, DocumentModeHint):
            msg = "document_mode_hint must be a DocumentModeHint value"
            raise ValueError(msg)
        if not isinstance(self.image, ProviderImageInput):
            msg = "image must be a ProviderImageInput value"
            raise ValueError(msg)
        if not isinstance(self.diagnostics, ProviderDiagnosticsSummary):
            msg = "diagnostics must be a ProviderDiagnosticsSummary value"
            raise ValueError(msg)
        if not isinstance(self.extraction, ProviderExtractionRuntimeSettings):
            msg = "extraction must be a ProviderExtractionRuntimeSettings value"
            raise ValueError(msg)

    def to_dict(self) -> dict[str, object]:
        staged_media_payload = (
            self.staged_media.to_dict() if self.staged_media is not None else None
        )
        return {
            "job_id": self.job_id,
            "job_status": self.job_status.value,
            "document_mode_hint": self.document_mode_hint.value,
            "image": self.image.to_dict(),
            "diagnostics": self.diagnostics.to_dict(),
            "extraction": self.extraction.to_dict(),
            "staged_media": staged_media_payload,
        }


def build_provider_input_context(
    job: DocumentJob,
    extraction_settings: ExtractionSettings,
) -> ProviderInputContext:
    _validate_job_lifecycle(job)
    image_path = _validate_local_image_state(job)
    diagnostics_payload = _require_mapping(
        job.image_diagnostics_payload,
        "image_diagnostics_payload",
    )
    diagnostics_summary = _build_diagnostics_summary(diagnostics_payload)
    extraction_runtime_settings = _build_extraction_runtime_settings(
        extraction_settings,
    )
    width, height, sha256 = _extract_image_facts(diagnostics_payload)

    return ProviderInputContext(
        job_id=job.id,
        job_status=job.status,
        document_mode_hint=job.user_mode_hint,
        image=ProviderImageInput(
            local_path=image_path,
            mime_type=_require_text(job.source_image_mime_type, "source_image_mime_type"),
            file_size_bytes=_require_positive_int(
                job.source_image_size_bytes,
                "source_image_size_bytes",
            ),
            width=width,
            height=height,
            sha256=sha256,
        ),
        diagnostics=diagnostics_summary,
        extraction=extraction_runtime_settings,
    )


def attach_staged_media(
    context: ProviderInputContext,
    staged_media: SupportsToDict,
) -> ProviderInputContext:
    if not isinstance(context, ProviderInputContext):
        msg = "context must be a ProviderInputContext value"
        raise ValueError(msg)
    _ensure_supports_to_dict(staged_media, "staged_media")
    return replace(context, staged_media=staged_media)


def _validate_job_lifecycle(job: DocumentJob) -> None:
    if job.status is JobStatus.IMAGE_DIAGNOSTICS_READY:
        return
    msg = (
        "Provider input context requires job status "
        f"{JobStatus.IMAGE_DIAGNOSTICS_READY.value}; got {job.status.value}"
    )
    raise ProviderInputContextLifecycleError(msg)


def _validate_local_image_state(job: DocumentJob) -> Path:
    source_image_path = _require_text(job.source_image_path, "source_image_path")
    image_path = Path(source_image_path)
    if not image_path.exists():
        msg = f"source_image_path does not exist: {image_path}"
        raise ProviderInputContextStateError(msg)
    if not image_path.is_file():
        msg = f"source_image_path must point to a file: {image_path}"
        raise ProviderInputContextStateError(msg)
    _require_text(job.source_image_mime_type, "source_image_mime_type")
    _require_positive_int(job.source_image_size_bytes, "source_image_size_bytes")
    return image_path


def _build_extraction_runtime_settings(
    extraction_settings: ExtractionSettings,
) -> ProviderExtractionRuntimeSettings:
    try:
        model_name = extraction_settings.require_model_name()
    except SettingsError as exc:
        msg = str(exc)
        raise ProviderInputContextSettingsError(msg) from exc

    provider_schema_mode = extraction_settings.provider_schema_mode
    if not isinstance(provider_schema_mode, ProviderSchemaMode):
        msg = "provider_schema_mode must be a ProviderSchemaMode value"
        raise ProviderInputContextSettingsError(msg)

    return ProviderExtractionRuntimeSettings(
        model=model_name,
        temperature=extraction_settings.temperature,
        timeout_seconds=extraction_settings.timeout_seconds,
        max_retries=extraction_settings.max_retries,
        provider_schema_mode=provider_schema_mode,
        structured_outputs_enabled=extraction_settings.structured_outputs_enabled,
        structured_outputs_require_parameters=(
            extraction_settings.structured_outputs_require_parameters
        ),
    )


def _build_diagnostics_summary(
    diagnostics_payload: Mapping[str, object],
) -> ProviderDiagnosticsSummary:
    quality = _optional_mapping(diagnostics_payload.get("quality"), "quality")
    image = _optional_mapping(diagnostics_payload.get("image"), "image")
    metadata = _optional_mapping(diagnostics_payload.get("metadata"), "metadata")
    warnings_payload = diagnostics_payload.get("warnings")
    if warnings_payload is None:
        warnings: tuple[ProviderDiagnosticWarning, ...] = ()
    else:
        warnings = _extract_warnings(warnings_payload)

    return ProviderDiagnosticsSummary(
        diagnostics_present=True,
        warnings=warnings,
        brightness=_optional_number_from_mapping(quality, "brightness"),
        contrast=_optional_number_from_mapping(quality, "contrast"),
        is_low_resolution=_optional_bool_from_mapping(quality, "is_low_resolution"),
        is_low_contrast=_optional_bool_from_mapping(quality, "is_low_contrast"),
        exif_orientation=_optional_positive_int_from_mapping(image, "exif_orientation"),
        schema_version=_optional_text_from_mapping(metadata, "schema_version"),
        diagnostics_version=_optional_text_from_mapping(metadata, "diagnostics_version"),
    )


def _extract_image_facts(
    diagnostics_payload: Mapping[str, object],
) -> tuple[int | None, int | None, str | None]:
    image = _optional_mapping(diagnostics_payload.get("image"), "image")
    file_payload = _optional_mapping(diagnostics_payload.get("file"), "file")
    width = _optional_positive_int_from_mapping(image, "width")
    height = _optional_positive_int_from_mapping(image, "height")
    sha256 = _optional_text_from_mapping(file_payload, "sha256")
    return width, height, sha256


def _extract_warnings(value: object) -> tuple[ProviderDiagnosticWarning, ...]:
    if not isinstance(value, list):
        msg = "warnings must be a list in image_diagnostics_payload"
        raise ProviderInputContextStateError(msg)

    warnings: list[ProviderDiagnosticWarning] = []
    for index, item in enumerate(value):
        mapping = _require_mapping(item, f"warnings[{index}]")
        warnings.append(
            ProviderDiagnosticWarning(
                code=_require_text_from_mapping(mapping, "code", f"warnings[{index}]"),
                message=_require_text_from_mapping(
                    mapping,
                    "message",
                    f"warnings[{index}]",
                ),
                severity=_require_text_from_mapping(
                    mapping,
                    "severity",
                    f"warnings[{index}]",
                ),
                target=_optional_text_from_mapping(mapping, "target"),
            )
        )
    return tuple(warnings)


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be present as an object"
        raise ProviderInputContextStateError(msg)
    return value


def _optional_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be an object when present"
        raise ProviderInputContextStateError(msg)
    return value


def _require_text(value: str | None, field_name: str) -> str:
    if value is None or not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must be present"
        raise ProviderInputContextStateError(msg)
    return value


def _require_text_from_mapping(
    mapping: Mapping[str, object],
    key: str,
    field_name: str,
) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name}.{key} must be present"
        raise ProviderInputContextStateError(msg)
    return value


def _optional_text_from_mapping(
    mapping: Mapping[str, object],
    key: str,
) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        msg = f"{key} must be a non-empty string when present"
        raise ProviderInputContextStateError(msg)
    return value


def _require_positive_int(value: int | None, field_name: str) -> int:
    if value is None or isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{field_name} must be present as a positive integer"
        raise ProviderInputContextStateError(msg)
    return value


def _optional_positive_int_from_mapping(
    mapping: Mapping[str, object],
    key: str,
) -> int | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{key} must be a positive integer when present"
        raise ProviderInputContextStateError(msg)
    return value


def _optional_bool_from_mapping(
    mapping: Mapping[str, object],
    key: str,
) -> bool | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        msg = f"{key} must be a boolean when present"
        raise ProviderInputContextStateError(msg)
    return value


def _optional_number_from_mapping(
    mapping: Mapping[str, object],
    key: str,
) -> float | None:
    value = mapping.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"{key} must be a number when present"
        raise ProviderInputContextStateError(msg)
    if not isfinite(value):
        msg = f"{key} must be finite when present"
        raise ProviderInputContextStateError(msg)
    return float(value)


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_optional_non_empty_text(value: str | None, field_name: str) -> None:
    if value is not None:
        _ensure_non_empty_text(value, field_name)


def _ensure_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{field_name} must be a positive integer"
        raise ValueError(msg)


def _ensure_optional_positive_int(value: int | None, field_name: str) -> None:
    if value is not None:
        _ensure_positive_int(value, field_name)


def _ensure_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{field_name} must be a non-negative integer"
        raise ValueError(msg)


def _ensure_optional_number(value: float | None, field_name: str) -> None:
    if value is None:
        return
    _ensure_non_negative_number(value, field_name)


def _ensure_non_negative_number(value: float, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int | float)
        or not isfinite(value)
        or value < 0
    ):
        msg = f"{field_name} must be a non-negative number"
        raise ValueError(msg)


def _ensure_supports_to_dict(value: object, field_name: str) -> None:
    if not callable(getattr(value, "to_dict", None)):
        msg = f"{field_name} must provide callable to_dict()"
        raise ProviderInputContextStateError(msg)
