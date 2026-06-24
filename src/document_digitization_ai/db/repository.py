from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.contracts import (
    DocumentModeHint,
    ExtractionResult,
    ImageDiagnostics,
    JobStatus,
    can_transition_job_status,
)
from document_digitization_ai.db.models import (
    DocumentJob,
    ExtractionAttempt,
    ExtractionAttemptStatus,
)


class PersistenceError(RuntimeError):
    """Base persistence-layer error."""


class JobNotFoundError(PersistenceError):
    """Raised when a document job does not exist."""


class InvalidJobStatusTransitionError(PersistenceError):
    """Raised when a repository update violates the approved lifecycle."""


class ExtractionAttemptNotFoundError(PersistenceError):
    """Raised when an extraction attempt does not exist."""


class InvalidExtractionAttemptStatusTransitionError(PersistenceError):
    """Raised when an extraction attempt transition violates the lifecycle."""


class DocumentJobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_job(
        self,
        user_mode_hint: DocumentModeHint,
        *,
        job_id: str | None = None,
    ) -> DocumentJob:
        job = DocumentJob(
            id=job_id or generate_job_id(),
            status=JobStatus.CREATED,
            user_mode_hint=user_mode_hint,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def get_job(self, job_id: str) -> DocumentJob | None:
        return await self._session.get(DocumentJob, job_id)

    async def require_job(self, job_id: str) -> DocumentJob:
        job = await self.get_job(job_id)
        if job is None:
            msg = f"Document job not found: {job_id}"
            raise JobNotFoundError(msg)
        return job

    async def list_jobs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: JobStatus | None = None,
    ) -> tuple[DocumentJob, ...]:
        statement = select(DocumentJob)
        if status is not None:
            statement = statement.where(DocumentJob.status == status)
        statement = (
            statement.order_by(DocumentJob.created_at.desc(), DocumentJob.id.desc())
            .offset(offset)
            .limit(limit)
        )
        jobs = await self._session.scalars(statement)
        return tuple(jobs.all())

    async def count_jobs(self, *, status: JobStatus | None = None) -> int:
        statement = select(func.count()).select_from(DocumentJob)
        if status is not None:
            statement = statement.where(DocumentJob.status == status)
        count = await self._session.scalar(statement)
        return int(count or 0)

    async def list_jobs_created_before(
        self,
        cutoff: datetime,
    ) -> tuple[DocumentJob, ...]:
        statement = (
            select(DocumentJob)
            .where(DocumentJob.created_at < cutoff)
            .order_by(DocumentJob.created_at.asc(), DocumentJob.id.asc())
        )
        jobs = await self._session.scalars(statement)
        return tuple(jobs.all())

    async def delete_job(self, job_id: str) -> bool:
        job = await self.get_job(job_id)
        if job is None:
            return False
        await self._session.delete(job)
        await self._session.flush()
        return True

    async def update_status(
        self,
        job_id: str,
        next_status: JobStatus,
    ) -> DocumentJob:
        job = await self.require_job(job_id)
        if not can_transition_job_status(job.status, next_status):
            msg = f"Invalid job status transition: {job.status.value} -> {next_status.value}"
            raise InvalidJobStatusTransitionError(msg)
        job.status = next_status
        await self._session.flush()
        return job

    async def attach_uploaded_image_metadata(
        self,
        job_id: str,
        *,
        source_image_path: str,
        mime_type: str,
        size_bytes: int,
    ) -> DocumentJob:
        job = await self.require_job(job_id)
        job.source_image_path = source_image_path
        job.source_image_mime_type = mime_type
        job.source_image_size_bytes = size_bytes
        await self._session.flush()
        return job

    async def attach_image_diagnostics(
        self,
        job_id: str,
        diagnostics: ImageDiagnostics,
    ) -> DocumentJob:
        job = await self.require_job(job_id)
        job.image_diagnostics_payload = diagnostics.to_dict()
        await self._session.flush()
        return job

    async def attach_extraction_result(
        self,
        job_id: str,
        result: ExtractionResult,
        *,
        validation_status: str | None = None,
        completed_attempt_id: str | None = None,
    ) -> DocumentJob:
        job = await self.require_job(job_id)
        job.extraction_result_payload = result.to_dict()
        job.validation_status = validation_status
        job.completed_attempt_id = completed_attempt_id
        await self._session.flush()
        return job

    async def mark_failed(self, job_id: str, error_message: str) -> DocumentJob:
        job = await self.require_job(job_id)
        if job.status is not JobStatus.FAILED:
            if not can_transition_job_status(job.status, JobStatus.FAILED):
                msg = f"Invalid job status transition: {job.status.value} -> FAILED"
                raise InvalidJobStatusTransitionError(msg)
            job.status = JobStatus.FAILED
        job.error_message = error_message
        await self._session.flush()
        return job


class ExtractionAttemptRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_attempt(
        self,
        *,
        job_id: str,
        attempt_number: int,
        provider_name: str,
        model_name: str,
        schema_version: str,
        schema_mode: str,
        request_metadata_json: Mapping[str, object],
        attempt_id: str | None = None,
    ) -> ExtractionAttempt:
        await self._require_job(job_id)
        attempt = ExtractionAttempt(
            id=attempt_id or generate_attempt_id(),
            job_id=job_id,
            attempt_number=attempt_number,
            status=ExtractionAttemptStatus.PENDING,
            provider_name=provider_name,
            model_name=model_name,
            schema_version=schema_version,
            schema_mode=schema_mode,
            request_metadata_json=dict(request_metadata_json),
        )
        self._session.add(attempt)
        await self._session.flush()
        return attempt

    async def get_attempt(self, attempt_id: str) -> ExtractionAttempt | None:
        return await self._session.get(ExtractionAttempt, attempt_id)

    async def require_attempt(self, attempt_id: str) -> ExtractionAttempt:
        attempt = await self.get_attempt(attempt_id)
        if attempt is None:
            msg = f"Extraction attempt not found: {attempt_id}"
            raise ExtractionAttemptNotFoundError(msg)
        return attempt

    async def list_attempts_for_job(self, job_id: str) -> tuple[ExtractionAttempt, ...]:
        statement = (
            select(ExtractionAttempt)
            .where(ExtractionAttempt.job_id == job_id)
            .order_by(ExtractionAttempt.attempt_number)
        )
        attempts = await self._session.scalars(statement)
        return tuple(attempts.all())

    async def get_latest_attempt_for_job(
        self,
        job_id: str,
    ) -> ExtractionAttempt | None:
        statement = (
            select(ExtractionAttempt)
            .where(ExtractionAttempt.job_id == job_id)
            .order_by(ExtractionAttempt.attempt_number.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def get_active_attempt_for_job(
        self,
        job_id: str,
    ) -> ExtractionAttempt | None:
        statement = (
            select(ExtractionAttempt)
            .where(
                ExtractionAttempt.job_id == job_id,
                ExtractionAttempt.status.in_(
                    (
                        ExtractionAttemptStatus.PENDING,
                        ExtractionAttemptStatus.RUNNING,
                    )
                ),
            )
            .order_by(ExtractionAttempt.attempt_number.desc())
            .limit(1)
        )
        return await self._session.scalar(statement)

    async def get_next_attempt_number(self, job_id: str) -> int:
        await self._require_job(job_id)
        statement = select(func.max(ExtractionAttempt.attempt_number)).where(
            ExtractionAttempt.job_id == job_id
        )
        latest_attempt_number = await self._session.scalar(statement)
        if latest_attempt_number is None:
            return 1
        return int(latest_attempt_number) + 1

    async def save(self, attempt: ExtractionAttempt) -> ExtractionAttempt:
        await self._session.flush()
        return attempt

    async def _require_job(self, job_id: str) -> DocumentJob:
        job = await self._session.get(DocumentJob, job_id)
        if job is None:
            msg = f"Document job not found: {job_id}"
            raise JobNotFoundError(msg)
        return job


def generate_job_id() -> str:
    return uuid4().hex


def generate_attempt_id() -> str:
    return uuid4().hex
