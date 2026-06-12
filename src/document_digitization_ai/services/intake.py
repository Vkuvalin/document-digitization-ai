from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from shutil import copy2

from document_digitization_ai.contracts import (
    DocumentModeHint,
    ImageDiagnostics,
    JobStatus,
    Warning,
)
from document_digitization_ai.db import DocumentJobRepository
from document_digitization_ai.diagnostics import (
    ImageDiagnosticsConfig,
    collect_image_diagnostics,
)
from document_digitization_ai.storage import JobArtifactLayout


class DocumentIntakeError(RuntimeError):
    """Raised when local document intake cannot complete."""


@dataclass(frozen=True, slots=True)
class DocumentIntakeResult:
    job_id: str
    final_job_status: JobStatus
    stored_original_image_path: Path
    image_diagnostics: ImageDiagnostics
    warnings: tuple[Warning, ...]


@dataclass(frozen=True, slots=True)
class DocumentIntakeService:
    repository: DocumentJobRepository
    artifact_layout: JobArtifactLayout
    diagnostics_config: ImageDiagnosticsConfig

    async def intake_local_image(
        self,
        source_image_path: str | Path,
        user_mode_hint: DocumentModeHint,
    ) -> DocumentIntakeResult:
        source_path = Path(source_image_path)
        _validate_source_image_path(source_path)
        job = await self.repository.create_job(user_mode_hint)

        try:
            artifact_paths = self.artifact_layout.ensure_job_dirs(
                job.id,
                source_path.suffix,
            )
            copy2(source_path, artifact_paths.original_upload_path)
            diagnostics = collect_image_diagnostics(
                artifact_paths.original_upload_path,
                config=self.diagnostics_config,
            )

            await self.repository.attach_uploaded_image_metadata(
                job.id,
                source_image_path=str(artifact_paths.original_upload_path),
                mime_type=diagnostics.file.mime_type,
                size_bytes=diagnostics.file.file_size_bytes,
            )
            await self.repository.update_status(job.id, JobStatus.IMAGE_UPLOADED)
            await self.repository.attach_image_diagnostics(job.id, diagnostics)
            updated_job = await self.repository.update_status(
                job.id,
                JobStatus.IMAGE_DIAGNOSTICS_READY,
            )
        except Exception as exc:
            await self._mark_job_failed(job.id, exc)
            msg = f"Document intake failed for job {job.id}: {exc}"
            raise DocumentIntakeError(msg) from exc

        return DocumentIntakeResult(
            job_id=job.id,
            final_job_status=updated_job.status,
            stored_original_image_path=artifact_paths.original_upload_path,
            image_diagnostics=diagnostics,
            warnings=diagnostics.warnings,
        )

    async def _mark_job_failed(self, job_id: str, error: Exception) -> None:
        try:
            await self.repository.mark_failed(job_id, str(error))
        except Exception as mark_failed_error:
            msg = (
                f"Document intake failed for job {job_id}; additionally failed "
                f"to mark job as FAILED: {mark_failed_error}"
            )
            raise DocumentIntakeError(msg) from error


def _validate_source_image_path(source_path: Path) -> None:
    if not source_path.is_file():
        msg = f"Source image path must exist and be a file: {source_path}"
        raise DocumentIntakeError(msg)
    if not source_path.suffix:
        msg = f"Source image path must include a file extension: {source_path}"
        raise DocumentIntakeError(msg)
