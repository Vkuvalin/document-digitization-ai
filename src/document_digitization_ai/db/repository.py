from __future__ import annotations

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.contracts import (
    DocumentModeHint,
    ExtractionResult,
    ImageDiagnostics,
    JobStatus,
    can_transition_job_status,
)
from document_digitization_ai.db.models import DocumentJob


class PersistenceError(RuntimeError):
    """Base persistence-layer error."""


class JobNotFoundError(PersistenceError):
    """Raised when a document job does not exist."""


class InvalidJobStatusTransitionError(PersistenceError):
    """Raised when a repository update violates the approved lifecycle."""


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
    ) -> DocumentJob:
        job = await self.require_job(job_id)
        job.extraction_result_payload = result.to_dict()
        job.validation_status = validation_status
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


def generate_job_id() -> str:
    return uuid4().hex
