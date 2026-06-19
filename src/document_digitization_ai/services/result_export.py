from __future__ import annotations

from dataclasses import dataclass

from document_digitization_ai.db import (
    DocumentJobRepository,
    ExtractionAttemptRepository,
    JobNotFoundError,
)
from document_digitization_ai.export import (
    ExtractionResultReconstructionError,
    build_extraction_result_export_document,
    reconstruct_extraction_result_from_payload,
    render_extraction_result_markdown,
)


class DocumentResultExportError(RuntimeError):
    """Raised when result export is configured incorrectly."""


@dataclass(frozen=True, slots=True)
class MarkdownExportResult:
    job_id: str
    result_available: bool
    markdown: str | None = None
    artifact_path: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class DocumentResultExportService:
    repository: DocumentJobRepository
    attempt_repository: ExtractionAttemptRepository | None = None

    async def export_job_result_markdown(
        self,
        job_id: str,
    ) -> MarkdownExportResult:
        try:
            job = await self.repository.require_job(job_id)
        except JobNotFoundError:
            return _unavailable(
                job_id=job_id,
                error_type="job_not_found",
                error_message="Document job was not found.",
            )

        if job.extraction_result_payload is None:
            return _unavailable(
                job_id=job.id,
                error_type="result_unavailable",
                error_message="Document job does not have an extraction result.",
            )

        try:
            result = reconstruct_extraction_result_from_payload(
                job.extraction_result_payload
            )
        except ExtractionResultReconstructionError:
            return _unavailable(
                job_id=job.id,
                error_type="malformed_result_payload",
                error_message="Persisted extraction result payload is malformed.",
            )

        attempt = None
        if self.attempt_repository is not None and job.completed_attempt_id is not None:
            attempt = await self.attempt_repository.get_attempt(job.completed_attempt_id)
        export_document = build_extraction_result_export_document(
            result,
            job=job,
            attempt=attempt,
        )
        markdown = render_extraction_result_markdown(export_document)

        return MarkdownExportResult(
            job_id=job.id,
            result_available=True,
            markdown=markdown,
        )


def _unavailable(
    *,
    job_id: str,
    error_type: str,
    error_message: str,
) -> MarkdownExportResult:
    return MarkdownExportResult(
        job_id=job_id,
        result_available=False,
        error_type=error_type,
        error_message=error_message,
    )
