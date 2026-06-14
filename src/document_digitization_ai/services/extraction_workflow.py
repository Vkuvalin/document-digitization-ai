from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from document_digitization_ai.contracts import ExtractionResult, JobStatus, Warning
from document_digitization_ai.core import ExtractionSettings
from document_digitization_ai.db import DocumentJobRepository
from document_digitization_ai.extraction import (
    ExtractionProviderPort,
    ExtractionProviderRequest,
    ExtractionProviderResponse,
    ProviderOutputValidationOutcome,
    build_extraction_prompt_package,
    build_extraction_schema_package,
    image_diagnostics_from_payload,
    validate_provider_output,
)
from document_digitization_ai.media import (
    MediaStagingInput,
    MediaStagingPort,
    MediaStagingResult,
    StagedMediaReference,
)
from document_digitization_ai.providers import (
    ProviderInputContext,
    attach_staged_media,
    build_provider_input_context,
)


class DocumentExtractionWorkflowError(RuntimeError):
    """Raised when local extraction workflow cannot complete."""


@dataclass(frozen=True, slots=True)
class DocumentExtractionWorkflowResult:
    job_id: str
    final_job_status: JobStatus
    validation_outcome: ProviderOutputValidationOutcome
    extraction_result: ExtractionResult
    raw_provider_response: ExtractionProviderResponse
    staged_media_reference: StagedMediaReference
    media_staging: MediaStagingResult
    warnings: tuple[Warning, ...]


@dataclass(frozen=True, slots=True)
class DocumentExtractionWorkflowService:
    repository: DocumentJobRepository
    extraction_settings: ExtractionSettings
    media_staging_service: MediaStagingPort
    extraction_provider: ExtractionProviderPort

    async def run(self, job_id: str) -> DocumentExtractionWorkflowResult:
        job = await self.repository.require_job(job_id)
        if job.status is not JobStatus.IMAGE_DIAGNOSTICS_READY:
            msg = (
                "Document extraction workflow requires job status "
                f"{JobStatus.IMAGE_DIAGNOSTICS_READY.value}; got {job.status.value}"
            )
            raise DocumentExtractionWorkflowError(msg)

        try:
            context = build_provider_input_context(job, self.extraction_settings)
            media_staging = await self._stage_media(context)
            await self.repository.update_status(job.id, JobStatus.MEDIA_STAGED)

            staged_context = attach_staged_media(context, media_staging.reference)
            prompt_package = build_extraction_prompt_package(staged_context)
            schema_package = build_extraction_schema_package(staged_context)
            request = ExtractionProviderRequest(
                correlation_id=job.id,
                context=staged_context,
                staged_media=media_staging.reference,
                prompt_package=prompt_package,
                schema_package=schema_package,
            )

            await self.repository.update_status(job.id, JobStatus.EXTRACTION_RUNNING)
            provider_response = await self.extraction_provider.extract(request)
            await self.repository.update_status(job.id, JobStatus.EXTRACTION_SUCCEEDED)

            image_diagnostics = image_diagnostics_from_payload(
                _require_image_diagnostics_payload(job.image_diagnostics_payload)
            )
            validation = validate_provider_output(
                provider_response,
                context=staged_context,
                image_diagnostics=image_diagnostics,
            )
            validation_job_status = _validation_job_status(validation.outcome)
            await self.repository.attach_extraction_result(
                job.id,
                validation.extraction_result,
                validation_status=validation_job_status.value,
            )
            await self.repository.update_status(job.id, validation_job_status)
            updated_job = await self.repository.update_status(job.id, JobStatus.RESULT_READY)
        except Exception as exc:
            await self._mark_job_failed(job.id, exc)
            msg = f"Document extraction workflow failed for job {job.id}: {exc}"
            raise DocumentExtractionWorkflowError(msg) from exc

        return DocumentExtractionWorkflowResult(
            job_id=job.id,
            final_job_status=updated_job.status,
            validation_outcome=validation.outcome,
            extraction_result=validation.extraction_result,
            raw_provider_response=provider_response,
            staged_media_reference=media_staging.reference,
            media_staging=media_staging,
            warnings=validation.extraction_result.warnings,
        )

    async def _stage_media(self, context: ProviderInputContext) -> MediaStagingResult:
        return await self.media_staging_service.stage(
            MediaStagingInput(
                local_path=context.image.local_path,
                mime_type=context.image.mime_type,
                file_size_bytes=context.image.file_size_bytes,
                sha256=context.image.sha256,
                metadata={
                    "job_id": context.job_id,
                    "source": "local_extraction_workflow",
                },
            )
        )

    async def _mark_job_failed(self, job_id: str, error: Exception) -> None:
        try:
            await self.repository.mark_failed(job_id, str(error))
        except Exception as mark_failed_error:
            msg = (
                f"Document extraction workflow failed for job {job_id}; additionally "
                f"failed to mark job as FAILED: {mark_failed_error}"
            )
            raise DocumentExtractionWorkflowError(msg) from error


def _validation_job_status(outcome: ProviderOutputValidationOutcome) -> JobStatus:
    if outcome is ProviderOutputValidationOutcome.SUCCEEDED:
        return JobStatus.VALIDATION_SUCCEEDED
    if outcome is ProviderOutputValidationOutcome.PARTIAL:
        return JobStatus.VALIDATION_PARTIAL
    msg = f"Unsupported validation outcome for persistence: {outcome.value}"
    raise DocumentExtractionWorkflowError(msg)


def _require_image_diagnostics_payload(
    value: object,
) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = "image_diagnostics_payload must be present before extraction workflow"
        raise DocumentExtractionWorkflowError(msg)
    return value
