from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


@dataclass(frozen=True, slots=True)
class BackendErrorView:
    error_type: str
    error_message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True, slots=True)
class ArtifactReference:
    kind: str
    relative_path: str
    exists: bool
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "relative_path": self.relative_path,
            "exists": self.exists,
            "content_type": self.content_type,
            "size_bytes": self.size_bytes,
            "created_at": _datetime_to_dict(self.created_at),
        }


@dataclass(frozen=True, slots=True)
class JobPreviewFileView:
    job_id: str
    path: Path | None = None
    filename: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    supports_inline_preview: bool = False
    error: BackendErrorView | None = None


@dataclass(frozen=True, slots=True)
class DeleteJobView:
    job_id: str
    deleted: bool
    artifacts_deleted: int = 0
    unsafe_artifacts_skipped: int = 0
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "deleted": self.deleted,
            "artifacts_deleted": self.artifacts_deleted,
            "unsafe_artifacts_skipped": self.unsafe_artifacts_skipped,
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class RetentionCleanupView:
    retention_days: int
    cutoff_at: datetime
    jobs_deleted: int
    artifacts_deleted: int
    unsafe_artifacts_skipped: int = 0
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "retention_days": self.retention_days,
            "cutoff_at": _datetime_to_dict(self.cutoff_at),
            "jobs_deleted": self.jobs_deleted,
            "artifacts_deleted": self.artifacts_deleted,
            "unsafe_artifacts_skipped": self.unsafe_artifacts_skipped,
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class SubmitDocumentResult:
    accepted: bool
    job_id: str | None
    status: str | None
    result_available: bool
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "job_id": self.job_id,
            "status": self.status,
            "result_available": self.result_available,
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class JobStatusView:
    job_id: str
    status: str | None
    result_available: bool
    latest_attempt_status: str | None = None
    validation_status: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "result_available": self.result_available,
            "latest_attempt_status": self.latest_attempt_status,
            "validation_status": self.validation_status,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "created_at": _datetime_to_dict(self.created_at),
            "updated_at": _datetime_to_dict(self.updated_at),
            "completed_at": _datetime_to_dict(self.completed_at),
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class JobSummary:
    job_id: str
    status: str
    result_available: bool
    document_type: str | None = None
    warning_count: int | None = None
    table_count: int | None = None
    field_count: int | None = None
    created_at: datetime | None = None
    completed_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "result_available": self.result_available,
            "document_type": self.document_type,
            "warning_count": self.warning_count,
            "table_count": self.table_count,
            "field_count": self.field_count,
            "created_at": _datetime_to_dict(self.created_at),
            "completed_at": _datetime_to_dict(self.completed_at),
        }


@dataclass(frozen=True, slots=True)
class JobHistoryView:
    jobs: tuple[JobSummary, ...]
    limit: int
    offset: int
    total: int
    status_filter: str | None = None
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "jobs": [job.to_dict() for job in self.jobs],
            "limit": self.limit,
            "offset": self.offset,
            "total": self.total,
            "status_filter": self.status_filter,
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class AttemptSummary:
    attempt_id: str
    attempt_number: int
    status: str
    provider_name: str
    model_name: str
    validation_outcome: str | None = None
    validation_issue_count: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    retryable: bool | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    duration_ms: int | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "attempt_id": self.attempt_id,
            "attempt_number": self.attempt_number,
            "status": self.status,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "validation_outcome": self.validation_outcome,
            "validation_issue_count": self.validation_issue_count,
            "error_type": self.error_type,
            "error_message": self.error_message,
            "retryable": self.retryable,
            "started_at": _datetime_to_dict(self.started_at),
            "finished_at": _datetime_to_dict(self.finished_at),
            "duration_ms": self.duration_ms,
            "created_at": _datetime_to_dict(self.created_at),
            "updated_at": _datetime_to_dict(self.updated_at),
        }


@dataclass(frozen=True, slots=True)
class ArtifactListView:
    job_id: str
    artifacts: tuple[ArtifactReference, ...]
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class JobDetailView:
    job_id: str
    summary: JobSummary | None
    status: JobStatusView | None
    attempts: tuple[AttemptSummary, ...] = field(default_factory=tuple)
    input_artifacts: tuple[ArtifactReference, ...] = field(default_factory=tuple)
    result_artifacts: tuple[ArtifactReference, ...] = field(default_factory=tuple)
    export_artifacts: tuple[ArtifactReference, ...] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "summary": None if self.summary is None else self.summary.to_dict(),
            "status": None if self.status is None else self.status.to_dict(),
            "attempts": [attempt.to_dict() for attempt in self.attempts],
            "input_artifacts": [
                artifact.to_dict() for artifact in self.input_artifacts
            ],
            "result_artifacts": [
                artifact.to_dict() for artifact in self.result_artifacts
            ],
            "export_artifacts": [
                artifact.to_dict() for artifact in self.export_artifacts
            ],
            "metadata": _json_safe(self.metadata),
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class ExtractionResultView:
    job_id: str
    result_available: bool
    result: Mapping[str, object] | None = None
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "result_available": self.result_available,
            "result": None if self.result is None else _json_safe(self.result),
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class MarkdownExportView:
    job_id: str
    result_available: bool
    markdown: str | None = None
    artifact: ArtifactReference | None = None
    error: BackendErrorView | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "result_available": self.result_available,
            "markdown": self.markdown,
            "artifact": None if self.artifact is None else self.artifact.to_dict(),
            "error": _error_to_dict(self.error),
        }


@dataclass(frozen=True, slots=True)
class PdfExportView:
    job_id: str
    result_available: bool
    pdf: bytes | None = None
    filename: str | None = None
    error: BackendErrorView | None = None


def _datetime_to_dict(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()


def _error_to_dict(value: BackendErrorView | None) -> dict[str, object] | None:
    return None if value is None else value.to_dict()


def _json_safe(value: object) -> object:
    if value is None or isinstance(value, str | bool | int | float):
        return value
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {
            str(key): _json_safe(item)
            for key, item in value.items()
            if isinstance(key, str)
        }
    if isinstance(value, tuple | list):
        return [_json_safe(item) for item in value]
    msg = f"Value is not safe for JSON DTO output: {type(value).__name__}"
    raise TypeError(msg)
