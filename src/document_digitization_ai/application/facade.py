from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from mimetypes import guess_type
from pathlib import Path, PureWindowsPath
from uuid import uuid4

from document_digitization_ai.application.dtos import (
    ArtifactListView,
    ArtifactReference,
    AttemptSummary,
    BackendErrorView,
    DeleteJobView,
    ExtractionResultView,
    JobDetailView,
    JobHistoryView,
    JobPreviewFileView,
    JobStatusView,
    JobSummary,
    MarkdownExportView,
    RetentionCleanupView,
    SubmitDocumentResult,
)
from document_digitization_ai.application.result_review import build_result_review_payload
from document_digitization_ai.application.runtime import LocalDocumentApplication
from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.db import (
    DocumentJob,
    DocumentJobRepository,
    ExtractionAttempt,
    ExtractionAttemptRepository,
    sanitize_error_message,
)
from document_digitization_ai.export import (
    ExtractionResultReconstructionError,
    build_extraction_result_export_document,
    count_extraction_result_warnings,
    reconstruct_extraction_result_from_payload,
    render_reconstructed_text_markdown,
)
from document_digitization_ai.services import DocumentExtractionWorkflowError
from document_digitization_ai.storage import (
    ArtifactLayoutError,
    MarkdownExportArtifactLayout,
    delete_artifact_tree,
)
from document_digitization_ai.storage.artifacts import validate_relative_artifact_path


_MAX_JOB_HISTORY_LIMIT = 100
_FILE_SUBMISSION_DIR = "_facade_file_submissions"
_INLINE_PREVIEW_CONTENT_TYPES = frozenset(
    {
        "application/pdf",
        "image/bmp",
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/tiff",
        "image/webp",
    }
)


@dataclass(frozen=True, slots=True)
class _JobSnapshot:
    id: str
    status: JobStatus
    user_mode_hint: DocumentModeHint
    source_image_path: str | None
    source_image_mime_type: str | None
    source_image_size_bytes: int | None
    extraction_result_payload: Mapping[str, object] | None
    validation_status: str | None
    completed_attempt_id: str | None
    error_message: str | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class _AttemptSnapshot:
    id: str
    job_id: str
    attempt_number: int
    status: str
    provider_name: str
    model_name: str
    sanitized_response_artifact_path: str | None
    sanitized_response_size_bytes: int | None
    validation_outcome: str | None
    validation_issue_count: int | None
    error_type: str | None
    error_message: str | None
    retryable: bool | None
    started_at: datetime | None
    finished_at: datetime | None
    duration_ms: int | None
    created_at: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True, slots=True)
class _ArtifactGroups:
    input_artifacts: tuple[ArtifactReference, ...]
    result_artifacts: tuple[ArtifactReference, ...]
    export_artifacts: tuple[ArtifactReference, ...]
    error: BackendErrorView | None = None

    @property
    def all_artifacts(self) -> tuple[ArtifactReference, ...]:
        return (
            *self.input_artifacts,
            *self.result_artifacts,
            *self.export_artifacts,
        )


@dataclass(frozen=True, slots=True)
class _StorageCleanupResult:
    artifacts_deleted: int
    unsafe_artifacts_skipped: int = 0


class DocumentProcessingFacade:
    def __init__(self, application: LocalDocumentApplication) -> None:
        self._application = application

    async def initialize_database(self) -> None:
        await self._application.initialize_database()

    async def close(self) -> None:
        await self._application.close()

    async def submit_document_from_path(
        self,
        path: str | Path,
        *,
        filename: str | None = None,
        user_mode_hint: DocumentModeHint = DocumentModeHint.AUTO,
    ) -> SubmitDocumentResult:
        if filename is not None:
            try:
                _safe_submission_filename(filename)
            except ValueError:
                return _submit_error("invalid_input", "Submitted filename is invalid.")

        source_path = Path(path)
        if not _is_supported_source_file(source_path):
            return _submit_error(
                "invalid_input",
                "Source document path does not point to a supported file.",
            )

        try:
            result = await self._application.run_real_extraction_from_image(
                source_path,
                user_mode_hint,
            )
        except DocumentExtractionWorkflowError as exc:
            return _submit_error(
                _submit_error_type(exc),
                _safe_processing_error_message(exc),
            )

        return SubmitDocumentResult(
            accepted=True,
            job_id=result.job_id,
            status=result.status.value,
            result_available=result.result_available,
        )

    async def submit_document_file(
        self,
        filename: str,
        content_type: str,
        data: bytes | bytearray | memoryview,
        *,
        user_mode_hint: DocumentModeHint = DocumentModeHint.AUTO,
    ) -> SubmitDocumentResult:
        if not content_type.strip():
            return _submit_error("invalid_input", "Submitted content type is invalid.")
        try:
            safe_filename = _safe_submission_filename(filename)
        except ValueError:
            return _submit_error("invalid_input", "Submitted filename is invalid.")

        data_bytes = bytes(data)
        if not data_bytes:
            return _submit_error("invalid_input", "Submitted file is empty.")

        staging_dir = (
            self._application.settings.storage.uploads_dir
            / _FILE_SUBMISSION_DIR
            / uuid4().hex
        )
        staged_path = staging_dir / safe_filename
        try:
            staging_dir.mkdir(parents=True, exist_ok=False)
            staged_path.write_bytes(data_bytes)
            return await self.submit_document_from_path(
                staged_path,
                filename=safe_filename,
                user_mode_hint=user_mode_hint,
            )
        except OSError:
            return _submit_error(
                "artifact_write_failed",
                "Submitted file could not be staged.",
            )
        finally:
            _cleanup_staged_submission_file(staged_path, staging_dir)

    async def get_job_status(self, job_id: str) -> JobStatusView:
        async with self._application._session_factory() as session:
            job = await DocumentJobRepository(session).get_job(job_id)
            if job is None:
                return _job_status_not_found(job_id)
            latest_attempt = await ExtractionAttemptRepository(
                session
            ).get_latest_attempt_for_job(job.id)
            return _status_view_from_snapshots(
                _snapshot_job(job),
                _snapshot_attempt(latest_attempt) if latest_attempt is not None else None,
            )

    async def list_jobs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: JobStatus | str | None = None,
    ) -> JobHistoryView:
        validation_error = _validate_history_pagination(limit, offset)
        if validation_error is not None:
            return JobHistoryView(
                jobs=(),
                limit=limit,
                offset=offset,
                total=0,
                error=validation_error,
            )

        status_filter, status_error = _coerce_status_filter(status)
        if status_error is not None:
            return JobHistoryView(
                jobs=(),
                limit=limit,
                offset=offset,
                total=0,
                error=status_error,
            )

        safe_limit = min(limit, _MAX_JOB_HISTORY_LIMIT)
        async with self._application._session_factory() as session:
            job_repository = DocumentJobRepository(session)
            attempt_repository = ExtractionAttemptRepository(session)
            jobs = await job_repository.list_jobs(
                limit=safe_limit,
                offset=offset,
                status=status_filter,
            )
            total = await job_repository.count_jobs(status=status_filter)
            summaries: list[JobSummary] = []
            for job in jobs:
                latest_attempt = await attempt_repository.get_latest_attempt_for_job(
                    job.id
                )
                summaries.append(
                    _summary_from_snapshots(
                        _snapshot_job(job),
                        (
                            _snapshot_attempt(latest_attempt)
                            if latest_attempt is not None
                            else None
                        ),
                    )
                )

        return JobHistoryView(
            jobs=tuple(summaries),
            limit=safe_limit,
            offset=offset,
            total=total,
            status_filter=None if status_filter is None else status_filter.value,
        )

    async def get_job_detail(self, job_id: str) -> JobDetailView:
        async with self._application._session_factory() as session:
            job_repository = DocumentJobRepository(session)
            attempt_repository = ExtractionAttemptRepository(session)
            job = await job_repository.get_job(job_id)
            if job is None:
                error = _not_found_error()
                return JobDetailView(
                    job_id=job_id,
                    summary=None,
                    status=None,
                    error=error,
                )
            attempts = await attempt_repository.list_attempts_for_job(job.id)
            job_snapshot = _snapshot_job(job)
            attempt_snapshots = tuple(_snapshot_attempt(attempt) for attempt in attempts)

        latest_attempt = attempt_snapshots[-1] if attempt_snapshots else None
        artifact_groups = _artifact_groups_for_job(
            self._application,
            job_snapshot,
            attempt_snapshots,
        )
        return JobDetailView(
            job_id=job_snapshot.id,
            summary=_summary_from_snapshots(job_snapshot, latest_attempt),
            status=_status_view_from_snapshots(job_snapshot, latest_attempt),
            attempts=tuple(
                _attempt_summary_from_snapshot(attempt)
                for attempt in attempt_snapshots
            ),
            input_artifacts=artifact_groups.input_artifacts,
            result_artifacts=artifact_groups.result_artifacts,
            export_artifacts=artifact_groups.export_artifacts,
            metadata=_job_metadata(job_snapshot),
            error=artifact_groups.error,
        )

    async def get_extraction_result(self, job_id: str) -> ExtractionResultView:
        async with self._application._session_factory() as session:
            job = await DocumentJobRepository(session).get_job(job_id)
            if job is None:
                return ExtractionResultView(
                    job_id=job_id,
                    result_available=False,
                    error=_not_found_error(),
                )
            payload = job.extraction_result_payload

        if payload is None:
            return ExtractionResultView(
                job_id=job_id,
                result_available=False,
                error=BackendErrorView(
                    error_type="result_unavailable",
                    error_message="Document job does not have an extraction result.",
                ),
            )

        try:
            result = reconstruct_extraction_result_from_payload(payload)
        except ExtractionResultReconstructionError:
            return ExtractionResultView(
                job_id=job_id,
                result_available=False,
                error=BackendErrorView(
                    error_type="malformed_result_payload",
                    error_message="Persisted extraction result payload is malformed.",
                ),
            )

        result_payload = result.to_dict()
        result_payload["review"] = build_result_review_payload(result)
        result_payload["presentation"] = {
            "text_markdown": render_reconstructed_text_markdown(
                build_extraction_result_export_document(result)
            )
        }
        return ExtractionResultView(
            job_id=job_id,
            result_available=True,
            result=result_payload,
        )

    async def get_result_markdown(
        self,
        job_id: str,
        *,
        write_artifact: bool = False,
    ) -> MarkdownExportView:
        result = await self._application.export_result_markdown(
            job_id,
            write_artifact=write_artifact,
        )
        if not result.result_available:
            return MarkdownExportView(
                job_id=result.job_id,
                result_available=False,
                error=BackendErrorView(
                    error_type=result.error_type or "result_unavailable",
                    error_message=(
                        result.error_message
                        or "Document job does not have an extraction result."
                    ),
                ),
            )

        artifact = None
        if result.artifact_path is not None:
            artifact = _result_artifact_reference(
                self._application,
                kind="markdown_export",
                relative_path=result.artifact_path,
                content_type="text/markdown; charset=utf-8",
            )
        return MarkdownExportView(
            job_id=result.job_id,
            result_available=True,
            markdown=result.markdown,
            artifact=artifact,
        )

    async def get_job_artifacts(self, job_id: str) -> ArtifactListView:
        artifact_job_id_error = _validate_artifact_job_id(self._application, job_id)
        if artifact_job_id_error is not None:
            return ArtifactListView(
                job_id=job_id,
                artifacts=(),
                error=artifact_job_id_error,
            )

        async with self._application._session_factory() as session:
            job_repository = DocumentJobRepository(session)
            attempt_repository = ExtractionAttemptRepository(session)
            job = await job_repository.get_job(job_id)
            if job is None:
                return ArtifactListView(
                    job_id=job_id,
                    artifacts=(),
                    error=_not_found_error(),
                )
            attempts = await attempt_repository.list_attempts_for_job(job.id)
            job_snapshot = _snapshot_job(job)
            attempt_snapshots = tuple(_snapshot_attempt(attempt) for attempt in attempts)

        artifact_groups = _artifact_groups_for_job(
            self._application,
            job_snapshot,
            attempt_snapshots,
        )
        return ArtifactListView(
            job_id=job_snapshot.id,
            artifacts=artifact_groups.all_artifacts,
            error=artifact_groups.error,
        )

    async def get_job_preview_file(self, job_id: str) -> JobPreviewFileView:
        artifact_job_id_error = _validate_artifact_job_id(self._application, job_id)
        if artifact_job_id_error is not None:
            return JobPreviewFileView(job_id=job_id, error=artifact_job_id_error)

        async with self._application._session_factory() as session:
            job = await DocumentJobRepository(session).get_job(job_id)
            if job is None:
                return JobPreviewFileView(job_id=job_id, error=_not_found_error())
            job_snapshot = _snapshot_job(job)

        if job_snapshot.source_image_path is None:
            return JobPreviewFileView(
                job_id=job_id,
                error=BackendErrorView(
                    error_type="artifact_not_found",
                    error_message="Original uploaded file was not found.",
                ),
            )

        try:
            target_path = _safe_upload_file_path(
                self._application,
                job_snapshot.source_image_path,
            )
        except (OSError, ValueError):
            return JobPreviewFileView(
                job_id=job_id,
                error=BackendErrorView(
                    error_type="artifact_access_denied",
                    error_message="Original uploaded file is not safe to serve.",
                ),
            )

        if not target_path.is_file():
            return JobPreviewFileView(
                job_id=job_id,
                error=BackendErrorView(
                    error_type="artifact_not_found",
                    error_message="Original uploaded file was not found.",
                ),
            )

        content_type = _safe_preview_content_type(
            target_path,
            job_snapshot.source_image_mime_type,
        )
        return JobPreviewFileView(
            job_id=job_snapshot.id,
            path=target_path,
            filename=_safe_download_filename(target_path.name),
            content_type=content_type,
            size_bytes=target_path.stat().st_size,
            supports_inline_preview=content_type in _INLINE_PREVIEW_CONTENT_TYPES,
        )

    async def delete_job(self, job_id: str) -> DeleteJobView:
        artifact_job_id_error = _validate_artifact_job_id(self._application, job_id)
        if artifact_job_id_error is not None:
            return DeleteJobView(
                job_id=job_id,
                deleted=False,
                error=artifact_job_id_error,
            )

        async with self._application._session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.get_job(job_id)
            if job is None:
                return DeleteJobView(job_id=job_id, deleted=False)

            try:
                cleanup = _cleanup_storage_for_job(self._application, job.id)
                deleted = await repository.delete_job(job.id)
                await session.commit()
            except OSError:
                await session.rollback()
                return DeleteJobView(
                    job_id=job_id,
                    deleted=False,
                    error=BackendErrorView(
                        error_type="artifact_delete_failed",
                        error_message="Stored files could not be deleted.",
                    ),
                )
            except Exception:
                await session.rollback()
                raise

        return DeleteJobView(
            job_id=job_id,
            deleted=deleted,
            artifacts_deleted=cleanup.artifacts_deleted,
            unsafe_artifacts_skipped=cleanup.unsafe_artifacts_skipped,
        )

    async def cleanup_expired_jobs(
        self,
        *,
        now: datetime | None = None,
    ) -> RetentionCleanupView:
        retention_days = self._application.settings.storage.artifact_retention_days
        now_utc = _coerce_utc_datetime(now or datetime.now(UTC))
        cutoff = now_utc - timedelta(days=retention_days)
        jobs_deleted = 0
        artifacts_deleted = 0
        unsafe_artifacts_skipped = 0

        async with self._application._session_factory() as session:
            repository = DocumentJobRepository(session)
            jobs = await repository.list_jobs_created_before(cutoff)
            try:
                for job in jobs:
                    cleanup = _cleanup_storage_for_job(self._application, job.id)
                    artifacts_deleted += cleanup.artifacts_deleted
                    unsafe_artifacts_skipped += cleanup.unsafe_artifacts_skipped
                    if await repository.delete_job(job.id):
                        jobs_deleted += 1
                await session.commit()
            except OSError:
                await session.rollback()
                return RetentionCleanupView(
                    retention_days=retention_days,
                    cutoff_at=cutoff,
                    jobs_deleted=jobs_deleted,
                    artifacts_deleted=artifacts_deleted,
                    unsafe_artifacts_skipped=unsafe_artifacts_skipped,
                    error=BackendErrorView(
                        error_type="artifact_delete_failed",
                        error_message="Stored files could not be deleted.",
                    ),
                )
            except Exception:
                await session.rollback()
                raise

        return RetentionCleanupView(
            retention_days=retention_days,
            cutoff_at=cutoff,
            jobs_deleted=jobs_deleted,
            artifacts_deleted=artifacts_deleted,
            unsafe_artifacts_skipped=unsafe_artifacts_skipped,
        )


def _safe_upload_file_path(
    application: LocalDocumentApplication,
    source_image_path: str,
) -> Path:
    uploads_root = application.settings.storage.uploads_dir.resolve()
    target_path = Path(source_image_path).resolve(strict=False)
    target_path.relative_to(uploads_root)
    return target_path


def _safe_preview_content_type(
    target_path: Path,
    persisted_content_type: str | None,
) -> str:
    guessed_content_type, _encoding = guess_type(target_path.name)
    for candidate in (persisted_content_type, guessed_content_type):
        normalized = _normalize_content_type(candidate)
        if normalized in _INLINE_PREVIEW_CONTENT_TYPES:
            return normalized
    return "application/octet-stream"


def _normalize_content_type(value: str | None) -> str:
    if value is None:
        return ""
    return value.split(";", 1)[0].strip().lower()


def _safe_download_filename(filename: str) -> str:
    value = filename.strip().replace('"', "_").replace(";", "_")
    if "\r" in value or "\n" in value:
        return "document.bin"
    try:
        return _safe_submission_filename(value)
    except ValueError:
        return "document.bin"


def _cleanup_storage_for_job(
    application: LocalDocumentApplication,
    job_id: str,
) -> _StorageCleanupResult:
    targets = (
        (application.settings.storage.uploads_dir, job_id),
        (application.settings.storage.results_dir, job_id),
        (application.settings.storage.results_dir, f"jobs/{job_id}"),
    )
    artifacts_deleted = 0
    unsafe_artifacts_skipped = 0
    for root, relative_path in targets:
        try:
            deleted_tree = delete_artifact_tree(root, relative_path)
        except ArtifactLayoutError:
            unsafe_artifacts_skipped += 1
            continue
        if deleted_tree.deleted:
            artifacts_deleted += 1
    return _StorageCleanupResult(
        artifacts_deleted=artifacts_deleted,
        unsafe_artifacts_skipped=unsafe_artifacts_skipped,
    )


def _coerce_utc_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _snapshot_job(job: DocumentJob) -> _JobSnapshot:
    return _JobSnapshot(
        id=job.id,
        status=job.status,
        user_mode_hint=job.user_mode_hint,
        source_image_path=job.source_image_path,
        source_image_mime_type=job.source_image_mime_type,
        source_image_size_bytes=job.source_image_size_bytes,
        extraction_result_payload=job.extraction_result_payload,
        validation_status=job.validation_status,
        completed_attempt_id=job.completed_attempt_id,
        error_message=job.error_message,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _snapshot_attempt(attempt: ExtractionAttempt) -> _AttemptSnapshot:
    return _AttemptSnapshot(
        id=attempt.id,
        job_id=attempt.job_id,
        attempt_number=attempt.attempt_number,
        status=attempt.status.value,
        provider_name=attempt.provider_name,
        model_name=attempt.model_name,
        sanitized_response_artifact_path=attempt.sanitized_response_artifact_path,
        sanitized_response_size_bytes=attempt.sanitized_response_size_bytes,
        validation_outcome=attempt.validation_outcome,
        validation_issue_count=attempt.validation_issue_count,
        error_type=attempt.error_type,
        error_message=attempt.error_message,
        retryable=attempt.retryable,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        duration_ms=attempt.duration_ms,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )


def _submit_error(error_type: str, error_message: str) -> SubmitDocumentResult:
    return SubmitDocumentResult(
        accepted=False,
        job_id=None,
        status=None,
        result_available=False,
        error=BackendErrorView(error_type=error_type, error_message=error_message),
    )


def _not_found_error() -> BackendErrorView:
    return BackendErrorView(
        error_type="job_not_found",
        error_message="Document job was not found.",
    )


def _job_status_not_found(job_id: str) -> JobStatusView:
    return JobStatusView(
        job_id=job_id,
        status=None,
        result_available=False,
        error=_not_found_error(),
    )


def _status_view_from_snapshots(
    job: _JobSnapshot,
    latest_attempt: _AttemptSnapshot | None,
) -> JobStatusView:
    return JobStatusView(
        job_id=job.id,
        status=job.status.value,
        result_available=job.extraction_result_payload is not None,
        latest_attempt_status=(
            None if latest_attempt is None else latest_attempt.status
        ),
        validation_status=job.validation_status,
        error_type=_job_error_type(job, latest_attempt),
        error_message=_job_error_message(job, latest_attempt),
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=None if latest_attempt is None else latest_attempt.finished_at,
    )


def _summary_from_snapshots(
    job: _JobSnapshot,
    latest_attempt: _AttemptSnapshot | None,
) -> JobSummary:
    return JobSummary(
        job_id=job.id,
        status=job.status.value,
        result_available=job.extraction_result_payload is not None,
        document_type=_document_type(job.extraction_result_payload),
        warning_count=_warning_count(job.extraction_result_payload),
        table_count=_sequence_count(job.extraction_result_payload, "tables"),
        field_count=_sequence_count(job.extraction_result_payload, "fields"),
        created_at=job.created_at,
        completed_at=None if latest_attempt is None else latest_attempt.finished_at,
    )


def _attempt_summary_from_snapshot(attempt: _AttemptSnapshot) -> AttemptSummary:
    return AttemptSummary(
        attempt_id=attempt.id,
        attempt_number=attempt.attempt_number,
        status=attempt.status,
        provider_name=attempt.provider_name,
        model_name=attempt.model_name,
        validation_outcome=attempt.validation_outcome,
        validation_issue_count=attempt.validation_issue_count,
        error_type=attempt.error_type,
        error_message=(
            None
            if attempt.error_message is None
            else sanitize_error_message(attempt.error_message)
        ),
        retryable=attempt.retryable,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        duration_ms=attempt.duration_ms,
        created_at=attempt.created_at,
        updated_at=attempt.updated_at,
    )


def _job_metadata(job: _JobSnapshot) -> dict[str, object]:
    metadata: dict[str, object] = {
        "user_mode_hint": job.user_mode_hint.value,
        "source_image_mime_type": job.source_image_mime_type,
        "source_image_size_bytes": job.source_image_size_bytes,
        "validation_status": job.validation_status,
        "completed_attempt_id": job.completed_attempt_id,
    }
    return metadata


def _job_error_type(
    job: _JobSnapshot,
    latest_attempt: _AttemptSnapshot | None,
) -> str | None:
    if latest_attempt is not None and latest_attempt.error_type is not None:
        return latest_attempt.error_type
    if job.error_message is not None:
        return "job_failed"
    return None


def _job_error_message(
    job: _JobSnapshot,
    latest_attempt: _AttemptSnapshot | None,
) -> str | None:
    if latest_attempt is not None and latest_attempt.error_message is not None:
        return sanitize_error_message(latest_attempt.error_message)
    if job.error_message is not None:
        return sanitize_error_message(job.error_message)
    return None


def _artifact_groups_for_job(
    application: LocalDocumentApplication,
    job: _JobSnapshot,
    attempts: tuple[_AttemptSnapshot, ...],
) -> _ArtifactGroups:
    input_artifacts: list[ArtifactReference] = []
    result_artifacts: list[ArtifactReference] = []
    export_artifacts: list[ArtifactReference] = []
    group_error = None

    input_reference, input_error = _input_artifact_reference(application, job)
    if input_reference is not None:
        input_artifacts.append(input_reference)
    if input_error is not None:
        group_error = input_error

    for attempt in attempts:
        if attempt.sanitized_response_artifact_path is None:
            continue
        result_reference = _result_artifact_reference(
            application,
            kind="provider_sanitized_response",
            relative_path=attempt.sanitized_response_artifact_path,
            content_type="application/json",
            known_size_bytes=attempt.sanitized_response_size_bytes,
        )
        if result_reference is not None:
            result_artifacts.append(result_reference)

    if job.extraction_result_payload is not None:
        markdown_reference = _markdown_artifact_reference(application, job.id)
        if markdown_reference is not None:
            export_artifacts.append(markdown_reference)

    return _ArtifactGroups(
        input_artifacts=tuple(input_artifacts),
        result_artifacts=tuple(result_artifacts),
        export_artifacts=tuple(export_artifacts),
        error=group_error,
    )


def _input_artifact_reference(
    application: LocalDocumentApplication,
    job: _JobSnapshot,
) -> tuple[ArtifactReference | None, BackendErrorView | None]:
    if job.source_image_path is None:
        return None, None

    try:
        uploads_root = application.settings.storage.uploads_dir.resolve()
        target_path = Path(job.source_image_path).resolve(strict=False)
        upload_relative_path = target_path.relative_to(uploads_root)
        relative_path = validate_relative_artifact_path(
            f"uploads/{_posix_path(upload_relative_path)}"
        )
    except (ArtifactLayoutError, OSError, ValueError):
        return None, BackendErrorView(
            error_type="artifact_access_denied",
            error_message="One or more artifact references were not safe to expose.",
        )

    return (
        _artifact_reference(
            kind="input_original",
            relative_path=relative_path,
            target_path=target_path,
            content_type=job.source_image_mime_type,
            known_size_bytes=job.source_image_size_bytes,
        ),
        None,
    )


def _result_artifact_reference(
    application: LocalDocumentApplication,
    *,
    kind: str,
    relative_path: str,
    content_type: str | None,
    known_size_bytes: int | None = None,
) -> ArtifactReference | None:
    try:
        safe_relative_path = validate_relative_artifact_path(relative_path)
        results_root = application.settings.storage.results_dir.resolve()
        target_path = results_root.joinpath(*safe_relative_path.split("/")).resolve(
            strict=False
        )
        target_path.relative_to(results_root)
    except (ArtifactLayoutError, OSError, ValueError):
        return None

    return _artifact_reference(
        kind=kind,
        relative_path=safe_relative_path,
        target_path=target_path,
        content_type=content_type,
        known_size_bytes=known_size_bytes,
    )


def _markdown_artifact_reference(
    application: LocalDocumentApplication,
    job_id: str,
) -> ArtifactReference | None:
    try:
        relative_path = MarkdownExportArtifactLayout(
            application.settings.storage.results_dir
        ).relative_path(job_id)
    except ArtifactLayoutError:
        return None
    return _result_artifact_reference(
        application,
        kind="markdown_export",
        relative_path=relative_path,
        content_type="text/markdown; charset=utf-8",
    )


def _artifact_reference(
    *,
    kind: str,
    relative_path: str,
    target_path: Path,
    content_type: str | None,
    known_size_bytes: int | None = None,
) -> ArtifactReference:
    exists = target_path.exists()
    stat_result = target_path.stat() if target_path.is_file() else None
    return ArtifactReference(
        kind=kind,
        relative_path=relative_path,
        exists=exists,
        content_type=content_type,
        size_bytes=(
            stat_result.st_size
            if stat_result is not None
            else known_size_bytes
            if exists
            else None
        ),
        created_at=(
            datetime.fromtimestamp(stat_result.st_ctime, UTC)
            if stat_result is not None
            else None
        ),
    )


def _validate_artifact_job_id(
    application: LocalDocumentApplication,
    job_id: str,
) -> BackendErrorView | None:
    try:
        MarkdownExportArtifactLayout(
            application.settings.storage.results_dir
        ).relative_path(job_id)
    except ArtifactLayoutError:
        return BackendErrorView(
            error_type="invalid_input",
            error_message="Job id is not a safe artifact identifier.",
        )
    return None


def _validate_history_pagination(
    limit: int,
    offset: int,
) -> BackendErrorView | None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        return BackendErrorView(
            error_type="invalid_input",
            error_message="Job history limit must be a positive integer.",
        )
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        return BackendErrorView(
            error_type="invalid_input",
            error_message="Job history offset must be a non-negative integer.",
        )
    return None


def _coerce_status_filter(
    status: JobStatus | str | None,
) -> tuple[JobStatus | None, BackendErrorView | None]:
    if status is None:
        return None, None
    if isinstance(status, JobStatus):
        return status, None
    try:
        return JobStatus(status), None
    except ValueError:
        return None, BackendErrorView(
            error_type="invalid_input",
            error_message="Job status filter is invalid.",
        )


def _document_type(payload: Mapping[str, object] | None) -> str | None:
    if payload is None:
        return None
    document = payload.get("document")
    if not isinstance(document, Mapping):
        return None
    detected_type = document.get("detected_type")
    return detected_type if isinstance(detected_type, str) else None


def _sequence_count(payload: Mapping[str, object] | None, key: str) -> int | None:
    if payload is None:
        return None
    value = payload.get(key)
    if isinstance(value, list | tuple):
        return len(value)
    return None


def _warning_count(payload: Mapping[str, object] | None) -> int | None:
    if payload is None:
        return None
    try:
        result = reconstruct_extraction_result_from_payload(payload)
    except ExtractionResultReconstructionError:
        return _sequence_count(payload, "warnings")
    return count_extraction_result_warnings(result)


def _is_supported_source_file(path: Path) -> bool:
    try:
        return path.is_file() and bool(path.suffix)
    except OSError:
        return False


def _safe_submission_filename(filename: str) -> str:
    value = filename.strip()
    if not value or value in {".", ".."}:
        msg = "filename must be a non-empty safe file name"
        raise ValueError(msg)
    if "/" in value or "\\" in value or ":" in value:
        msg = "filename must not contain path separators or drive markers"
        raise ValueError(msg)
    windows_path = PureWindowsPath(value)
    if windows_path.is_absolute() or windows_path.drive:
        msg = "filename must not be an absolute path"
        raise ValueError(msg)
    path = Path(value)
    if path.name != value or not path.suffix:
        msg = "filename must be a single file name with an extension"
        raise ValueError(msg)
    return value


def _cleanup_staged_submission_file(staged_path: Path, staging_dir: Path) -> None:
    try:
        staged_path.unlink(missing_ok=True)
    except OSError:
        return
    try:
        staging_dir.rmdir()
    except OSError:
        return


def _submit_error_type(error: DocumentExtractionWorkflowError) -> str:
    message = str(error).lower()
    if "valid image" in message or "unsupported" in message:
        return "unsupported_file"
    if "source image path" in message:
        return "invalid_input"
    return "internal_error"


def _safe_processing_error_message(error: DocumentExtractionWorkflowError) -> str:
    message = sanitize_error_message(str(error))
    if not message:
        return "Document could not be processed."
    return message


def _posix_path(path: Path) -> str:
    return "/".join(path.parts)
