from __future__ import annotations

from dataclasses import dataclass

from document_digitization_ai.db import (
    DocumentJob,
    DocumentJobRepository,
    ExtractionAttempt,
    ExtractionAttemptRepository,
    JobNotFoundError,
)
from document_digitization_ai.export import (
    ExportDocument,
    ExtractionResultReconstructionError,
    build_extraction_result_export_document,
    reconstruct_extraction_result_from_payload,
    render_extraction_result_markdown,
    render_extraction_result_pdf,
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
class PdfExportResult:
    job_id: str
    result_available: bool
    pdf: bytes | None = None
    filename: str | None = None
    error_type: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class _ExportDocumentResult:
    job_id: str
    result_available: bool
    export_document: ExportDocument | None = None
    job: DocumentJob | None = None
    attempt: ExtractionAttempt | None = None
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
        document_result = await self._build_job_export_document(job_id)
        if not document_result.result_available:
            return _markdown_unavailable(
                job_id=document_result.job_id,
                error_type=document_result.error_type or "result_unavailable",
                error_message=(
                    document_result.error_message
                    or "Document job does not have an extraction result."
                ),
            )
        if document_result.export_document is None:
            return _markdown_unavailable(
                job_id=document_result.job_id,
                error_type="malformed_result_payload",
                error_message="Persisted extraction result payload is malformed.",
            )

        markdown = render_extraction_result_markdown(document_result.export_document)
        return MarkdownExportResult(
            job_id=document_result.job_id,
            result_available=True,
            markdown=markdown,
        )

    async def export_job_result_pdf(
        self,
        job_id: str,
    ) -> PdfExportResult:
        document_result = await self._build_job_export_document(job_id)
        if not document_result.result_available:
            return _pdf_unavailable(
                job_id=document_result.job_id,
                error_type=document_result.error_type or "result_unavailable",
                error_message=(
                    document_result.error_message
                    or "Document job does not have an extraction result."
                ),
            )
        if document_result.export_document is None:
            return _pdf_unavailable(
                job_id=document_result.job_id,
                error_type="malformed_result_payload",
                error_message="Persisted extraction result payload is malformed.",
            )

        pdf = render_extraction_result_pdf(
            document_result.export_document,
            job_reference=_short_job_reference(document_result.job_id),
            created_at=(
                None if document_result.job is None else document_result.job.created_at
            ),
        )
        return PdfExportResult(
            job_id=document_result.job_id,
            result_available=True,
            pdf=pdf,
            filename=_safe_pdf_filename(document_result.job_id),
        )

    async def _build_job_export_document(
        self,
        job_id: str,
    ) -> _ExportDocumentResult:
        try:
            job = await self.repository.require_job(job_id)
        except JobNotFoundError:
            return _export_document_unavailable(
                job_id=job_id,
                error_type="job_not_found",
                error_message="Document job was not found.",
            )

        if job.extraction_result_payload is None:
            return _export_document_unavailable(
                job_id=job.id,
                error_type="result_unavailable",
                error_message="Document job does not have an extraction result.",
            )

        try:
            result = reconstruct_extraction_result_from_payload(
                job.extraction_result_payload
            )
        except ExtractionResultReconstructionError:
            return _export_document_unavailable(
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

        return _ExportDocumentResult(
            job_id=job.id,
            result_available=True,
            export_document=export_document,
            job=job,
            attempt=attempt,
        )


def _export_document_unavailable(
    *,
    job_id: str,
    error_type: str,
    error_message: str,
) -> _ExportDocumentResult:
    return _ExportDocumentResult(
        job_id=job_id,
        result_available=False,
        error_type=error_type,
        error_message=error_message,
    )


def _markdown_unavailable(
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


def _pdf_unavailable(
    *,
    job_id: str,
    error_type: str,
    error_message: str,
) -> PdfExportResult:
    return PdfExportResult(
        job_id=job_id,
        result_available=False,
        error_type=error_type,
        error_message=error_message,
    )


def _short_job_reference(job_id: str) -> str:
    safe = _safe_reference_fragment(job_id)
    return safe[:12] or "unknown"


def _safe_pdf_filename(job_id: str) -> str:
    safe = _safe_reference_fragment(job_id)[:12] or "result"
    return f"analysis_{safe}.pdf"


def _safe_reference_fragment(value: str) -> str:
    normalized = value.strip()
    chars = [
        char if char.isascii() and (char.isalnum() or char in {"-", "_"}) else "_"
        for char in normalized
    ]
    return "".join(chars).strip("_-.")
