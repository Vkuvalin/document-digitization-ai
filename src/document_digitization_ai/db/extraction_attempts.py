from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from math import isfinite
import re

from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.db.models import (
    ExtractionAttempt,
    ExtractionAttemptStatus,
    utc_now,
)
from document_digitization_ai.db.repository import (
    ExtractionAttemptRepository,
    InvalidExtractionAttemptStatusTransitionError,
)
from document_digitization_ai.storage.artifacts import validate_relative_artifact_path


MAX_ERROR_MESSAGE_LENGTH = 1000

_ALLOWED_ATTEMPT_TRANSITIONS: Mapping[
    ExtractionAttemptStatus,
    frozenset[ExtractionAttemptStatus],
] = {
    ExtractionAttemptStatus.PENDING: frozenset(
        {
            ExtractionAttemptStatus.RUNNING,
            ExtractionAttemptStatus.FAILED,
        }
    ),
    ExtractionAttemptStatus.RUNNING: frozenset(
        {
            ExtractionAttemptStatus.SUCCEEDED,
            ExtractionAttemptStatus.FAILED,
        }
    ),
    ExtractionAttemptStatus.SUCCEEDED: frozenset(),
    ExtractionAttemptStatus.FAILED: frozenset(),
}

_REQUEST_TEXT_KEYS = frozenset(
    {
        "media_backend",
        "provider_name",
        "model_name",
        "schema_version",
        "schema_mode",
        "staged_media_kind",
        "media_url_host",
        "prompt_profile",
        "prompt_version",
        "prompt_hash",
        "response_format_schema_hash",
    }
)
_REQUEST_INT_KEYS = frozenset({"media_count"})
_REQUEST_BOOL_KEYS = frozenset(
    {
        "external_upload_performed",
        "media_url_present",
        "structured_outputs_enabled",
        "provider_require_parameters",
    }
)

_RESPONSE_TEXT_KEYS = frozenset(
    {
        "provider_response_id",
        "finish_reason",
        "model_name",
    }
)
_RESPONSE_BOOL_KEYS = frozenset({"usable_content"})
_RESPONSE_INT_KEYS = frozenset(
    {
        "raw_text_length",
        "response_size_bytes",
        "choice_count",
        "warning_count",
        "table_count",
        "field_count",
        "block_count",
    }
)
_RESPONSE_FLOAT_KEYS = frozenset({"provider_seconds"})
_USAGE_KEYS = frozenset({"prompt_tokens", "completion_tokens", "total_tokens"})

_DEFAULT_RETRYABLE_ERROR_TYPES = frozenset(
    {
        "ProviderRateLimitError",
        "ProviderTimeoutError",
        "ProviderUnavailableError",
    }
)

_SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[^\s,;]+"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)((?:OPENROUTER|IMGBB)_API_KEY\s*=\s*)[^\s,;]+"),
)
_WINDOWS_ABSOLUTE_PATH_PATTERN = re.compile(r"[A-Za-z]:\\[^\s,;]+")
_POSIX_ABSOLUTE_PATH_PATTERN = re.compile(r"(?<!:)\/(?:[^\s,;:]+\/)+[^\s,;:]+")


@dataclass(frozen=True, slots=True)
class ExtractionAttemptFailureMetadata:
    error_type: str
    error_message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class ExtractionAttemptLifecycleService:
    session_factory: Callable[[], AsyncSession]

    async def create_attempt_for_job(
        self,
        *,
        job_id: str,
        provider_name: str,
        model_name: str,
        schema_version: str,
        schema_mode: str,
        request_metadata: Mapping[str, object] | None = None,
    ) -> ExtractionAttempt:
        provider_name = _require_text(provider_name, "provider_name")
        model_name = _require_text(model_name, "model_name")
        schema_version = _require_text(schema_version, "schema_version")
        schema_mode = _require_text(schema_mode, "schema_mode")
        safe_metadata = build_safe_request_metadata(
            provider_name=provider_name,
            model_name=model_name,
            schema_version=schema_version,
            schema_mode=schema_mode,
            metadata=request_metadata,
        )

        async with self.session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            attempt = await repository.create_attempt(
                job_id=job_id,
                attempt_number=await repository.get_next_attempt_number(job_id),
                provider_name=provider_name,
                model_name=model_name,
                schema_version=schema_version,
                schema_mode=schema_mode,
                request_metadata_json=safe_metadata,
            )
            await session.commit()
            return attempt

    async def start_attempt(self, attempt_id: str) -> ExtractionAttempt:
        async with self.session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            attempt = await repository.require_attempt(attempt_id)
            _ensure_expected_transition(
                attempt,
                expected_status=ExtractionAttemptStatus.PENDING,
                next_status=ExtractionAttemptStatus.RUNNING,
            )
            attempt.status = ExtractionAttemptStatus.RUNNING
            attempt.started_at = utc_now()
            await repository.save(attempt)
            await session.commit()
            return attempt

    async def record_provider_response_artifacts(
        self,
        attempt_id: str,
        *,
        raw_response_artifact_path: str | None = None,
        raw_response_size_bytes: int | None = None,
        sanitized_response_artifact_path: str | None = None,
        sanitized_response_size_bytes: int | None = None,
    ) -> ExtractionAttempt:
        async with self.session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            attempt = await repository.require_attempt(attempt_id)
            _ensure_expected_status(
                attempt,
                expected_status=ExtractionAttemptStatus.RUNNING,
                operation="artifact reference update",
            )
            attempt.raw_response_artifact_path = _optional_artifact_path(
                raw_response_artifact_path,
                "raw_response_artifact_path",
            )
            attempt.raw_response_size_bytes = _optional_non_negative_int(
                raw_response_size_bytes,
                "raw_response_size_bytes",
            )
            attempt.sanitized_response_artifact_path = _optional_artifact_path(
                sanitized_response_artifact_path,
                "sanitized_response_artifact_path",
            )
            attempt.sanitized_response_size_bytes = _optional_non_negative_int(
                sanitized_response_size_bytes,
                "sanitized_response_size_bytes",
            )
            await repository.save(attempt)
            await session.commit()
            return attempt

    async def record_media_staging_metadata(
        self,
        attempt_id: str,
        *,
        metadata: Mapping[str, object],
    ) -> ExtractionAttempt:
        async with self.session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            attempt = await repository.require_attempt(attempt_id)
            _ensure_expected_status(
                attempt,
                expected_status=ExtractionAttemptStatus.RUNNING,
                operation="media staging metadata update",
            )
            merged_metadata = {
                **attempt.request_metadata_json,
                **dict(metadata),
            }
            attempt.request_metadata_json = build_safe_request_metadata(
                provider_name=attempt.provider_name,
                model_name=attempt.model_name,
                schema_version=attempt.schema_version,
                schema_mode=attempt.schema_mode,
                metadata=merged_metadata,
            )
            await repository.save(attempt)
            await session.commit()
            return attempt

    async def complete_attempt_success(
        self,
        attempt_id: str,
        *,
        validation_outcome: str | StrEnum,
        validation_issue_count: int,
        response_metadata: Mapping[str, object] | None = None,
        raw_response_artifact_path: str | None = None,
        raw_response_size_bytes: int | None = None,
        sanitized_response_artifact_path: str | None = None,
        sanitized_response_size_bytes: int | None = None,
    ) -> ExtractionAttempt:
        async with self.session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            attempt = await repository.require_attempt(attempt_id)
            _ensure_expected_transition(
                attempt,
                expected_status=ExtractionAttemptStatus.RUNNING,
                next_status=ExtractionAttemptStatus.SUCCEEDED,
            )
            finished_at = utc_now()
            attempt.status = ExtractionAttemptStatus.SUCCEEDED
            attempt.finished_at = finished_at
            attempt.duration_ms = _duration_ms(attempt.started_at, finished_at)
            attempt.validation_outcome = _require_text(
                _enum_value(validation_outcome),
                "validation_outcome",
            )
            attempt.validation_issue_count = _non_negative_int(
                validation_issue_count,
                "validation_issue_count",
            )
            attempt.response_metadata_json = build_safe_response_metadata(
                response_metadata
            )
            attempt.raw_response_artifact_path = _optional_artifact_path(
                raw_response_artifact_path,
                "raw_response_artifact_path",
            )
            attempt.raw_response_size_bytes = _optional_non_negative_int(
                raw_response_size_bytes,
                "raw_response_size_bytes",
            )
            attempt.sanitized_response_artifact_path = _optional_artifact_path(
                sanitized_response_artifact_path,
                "sanitized_response_artifact_path",
            )
            attempt.sanitized_response_size_bytes = _optional_non_negative_int(
                sanitized_response_size_bytes,
                "sanitized_response_size_bytes",
            )
            await repository.save(attempt)
            await session.commit()
            return attempt

    async def complete_attempt_failure(
        self,
        attempt_id: str,
        *,
        error: Exception | str,
        expected_status: ExtractionAttemptStatus = ExtractionAttemptStatus.RUNNING,
        retryable: bool | None = None,
        error_type: str | None = None,
        raw_response_artifact_path: str | None = None,
        raw_response_size_bytes: int | None = None,
        sanitized_response_artifact_path: str | None = None,
        sanitized_response_size_bytes: int | None = None,
    ) -> ExtractionAttempt:
        async with self.session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            attempt = await repository.require_attempt(attempt_id)
            _ensure_expected_transition(
                attempt,
                expected_status=expected_status,
                next_status=ExtractionAttemptStatus.FAILED,
            )
            failure = normalize_failure_metadata(
                error,
                retryable=retryable,
                error_type=error_type,
            )
            finished_at = utc_now()
            attempt.status = ExtractionAttemptStatus.FAILED
            attempt.finished_at = finished_at
            attempt.duration_ms = _duration_ms(attempt.started_at, finished_at)
            attempt.error_type = failure.error_type
            attempt.error_message = failure.error_message
            attempt.retryable = failure.retryable
            attempt.raw_response_artifact_path = _optional_artifact_path(
                raw_response_artifact_path,
                "raw_response_artifact_path",
            )
            attempt.raw_response_size_bytes = _optional_non_negative_int(
                raw_response_size_bytes,
                "raw_response_size_bytes",
            )
            attempt.sanitized_response_artifact_path = _optional_artifact_path(
                sanitized_response_artifact_path,
                "sanitized_response_artifact_path",
            )
            attempt.sanitized_response_size_bytes = _optional_non_negative_int(
                sanitized_response_size_bytes,
                "sanitized_response_size_bytes",
            )
            await repository.save(attempt)
            await session.commit()
            return attempt


def can_transition_extraction_attempt_status(
    current: ExtractionAttemptStatus,
    next_status: ExtractionAttemptStatus,
) -> bool:
    return next_status in _ALLOWED_ATTEMPT_TRANSITIONS[current]


def build_safe_request_metadata(
    *,
    provider_name: str,
    model_name: str,
    schema_version: str,
    schema_mode: str,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    safe_metadata: dict[str, object] = {
        "provider_name": _require_text(provider_name, "provider_name"),
        "model_name": _require_text(model_name, "model_name"),
        "schema_version": _require_text(schema_version, "schema_version"),
        "schema_mode": _require_text(schema_mode, "schema_mode"),
    }
    if metadata is None:
        return safe_metadata
    for key in sorted(metadata):
        if key in safe_metadata:
            continue
        value = metadata[key]
        if key in _REQUEST_TEXT_KEYS:
            text_value = _optional_text_value(value)
            if text_value is not None:
                safe_metadata[key] = text_value
        elif key in _REQUEST_INT_KEYS:
            int_value = _optional_int_value(value)
            if int_value is not None:
                safe_metadata[key] = int_value
        elif key in _REQUEST_BOOL_KEYS and isinstance(value, bool):
            safe_metadata[key] = value
    return safe_metadata


def build_safe_response_metadata(
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    if metadata is None:
        return {}

    safe_metadata: dict[str, object] = {}
    for key in sorted(metadata):
        value = metadata[key]
        if key in _RESPONSE_TEXT_KEYS:
            text_value = _optional_text_value(value)
            if text_value is not None:
                safe_metadata[key] = text_value
        elif key in _RESPONSE_BOOL_KEYS and isinstance(value, bool):
            safe_metadata[key] = value
        elif key in _RESPONSE_INT_KEYS:
            int_value = _optional_int_value(value)
            if int_value is not None:
                safe_metadata[key] = int_value
        elif key in _RESPONSE_FLOAT_KEYS:
            float_value = _optional_float_value(value)
            if float_value is not None:
                safe_metadata[key] = float_value
        elif key == "usage":
            usage = _safe_usage_metadata(value)
            if usage:
                safe_metadata[key] = usage
    return safe_metadata


def normalize_failure_metadata(
    error: Exception | str,
    *,
    retryable: bool | None = None,
    error_type: str | None = None,
) -> ExtractionAttemptFailureMetadata:
    normalized_error_type = _require_text(
        error_type
        if error_type is not None
        else error.__class__.__name__
        if isinstance(error, Exception)
        else "Error",
        "error_type",
    )
    raw_message = str(error).strip() or normalized_error_type
    safe_message = sanitize_error_message(raw_message)
    retryable_value = (
        normalized_error_type in _DEFAULT_RETRYABLE_ERROR_TYPES
        if retryable is None
        else retryable
    )
    return ExtractionAttemptFailureMetadata(
        error_type=normalized_error_type,
        error_message=safe_message,
        retryable=retryable_value,
    )


def sanitize_error_message(
    message: str,
    *,
    max_length: int = MAX_ERROR_MESSAGE_LENGTH,
) -> str:
    safe_message = message.replace("\r", " ").replace("\n", " ").strip()
    for pattern in _SENSITIVE_VALUE_PATTERNS:
        safe_message = pattern.sub(
            lambda match: f"{match.group(1)}[redacted]",
            safe_message,
        )
    safe_message = _WINDOWS_ABSOLUTE_PATH_PATTERN.sub("[redacted_path]", safe_message)
    safe_message = _POSIX_ABSOLUTE_PATH_PATTERN.sub("[redacted_path]", safe_message)
    if len(safe_message) <= max_length:
        return safe_message
    suffix = "...[truncated]"
    return f"{safe_message[: max_length - len(suffix)]}{suffix}"


def _ensure_expected_transition(
    attempt: ExtractionAttempt,
    *,
    expected_status: ExtractionAttemptStatus,
    next_status: ExtractionAttemptStatus,
) -> None:
    if attempt.status != expected_status:
        msg = (
            "Invalid extraction attempt status transition: expected "
            f"{expected_status.value}, got {attempt.status.value}"
        )
        raise InvalidExtractionAttemptStatusTransitionError(msg)
    if not can_transition_extraction_attempt_status(attempt.status, next_status):
        msg = (
            "Invalid extraction attempt status transition: "
            f"{attempt.status.value} -> {next_status.value}"
        )
        raise InvalidExtractionAttemptStatusTransitionError(msg)


def _ensure_expected_status(
    attempt: ExtractionAttempt,
    *,
    expected_status: ExtractionAttemptStatus,
    operation: str,
) -> None:
    if attempt.status == expected_status:
        return
    msg = (
        f"Invalid extraction attempt {operation}: expected "
        f"{expected_status.value}, got {attempt.status.value}"
    )
    raise InvalidExtractionAttemptStatusTransitionError(msg)


def _duration_ms(started_at: datetime | None, finished_at: datetime) -> int:
    if started_at is None:
        return 0
    if started_at.tzinfo is None and finished_at.tzinfo is not None:
        finished_at = finished_at.replace(tzinfo=None)
    elif started_at.tzinfo is not None and finished_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)
    return max(0, int((finished_at - started_at).total_seconds() * 1000))


def _optional_artifact_path(value: str | None, field_name: str) -> str | None:
    if value is None:
        return None
    try:
        return validate_relative_artifact_path(value)
    except ValueError as exc:
        msg = f"{field_name}: {exc}"
        raise ValueError(msg) from exc


def _require_text(value: str | StrEnum, field_name: str) -> str:
    if isinstance(value, StrEnum):
        value = value.value
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must be a non-empty string"
        raise ValueError(msg)
    return value.strip()


def _enum_value(value: str | StrEnum) -> str:
    if isinstance(value, StrEnum):
        return value.value
    return value


def _optional_text_value(value: object) -> str | None:
    if isinstance(value, StrEnum):
        value = value.value
    if not isinstance(value, str):
        return None
    value = value.strip()
    if not value:
        return None
    return value


def _optional_int_value(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _optional_float_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if not isfinite(value) or value < 0:
        return None
    return float(value)


def _safe_usage_metadata(value: object) -> dict[str, int | None]:
    if not isinstance(value, Mapping):
        return {}
    usage: dict[str, int | None] = {}
    for key in sorted(_USAGE_KEYS):
        item = value.get(key)
        if item is None:
            usage[key] = None
        else:
            int_value = _optional_int_value(item)
            if int_value is not None:
                usage[key] = int_value
    return usage


def _non_negative_int(value: int, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        msg = f"{field_name} must be a non-negative integer"
        raise ValueError(msg)
    return value


def _optional_non_negative_int(value: int | None, field_name: str) -> int | None:
    if value is None:
        return None
    return _non_negative_int(value, field_name)
