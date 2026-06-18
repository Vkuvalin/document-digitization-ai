from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from mimetypes import guess_type
from pathlib import Path
from shutil import copy2

from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.contracts import (
    EXTRACTION_RESULT_SCHEMA_VERSION,
    DocumentModeHint,
    ExtractionResult,
    ImageDiagnostics,
    JobStatus,
    Warning,
)
from document_digitization_ai.core import ExtractionProviderName, ExtractionSettings
from document_digitization_ai.db import (
    DocumentJobRepository,
    ExtractionAttemptLifecycleService,
    ExtractionAttemptRepository,
    ExtractionAttemptStatus,
    build_safe_request_metadata,
    build_safe_response_metadata,
    normalize_failure_metadata,
    sanitize_error_message,
)
from document_digitization_ai.db.models import utc_now
from document_digitization_ai.diagnostics import (
    ImageDiagnosticsConfig,
    ImageDiagnosticsError,
    collect_image_diagnostics,
)
from document_digitization_ai.extraction import (
    ExtractionProviderPort,
    ExtractionProviderRequest,
    ExtractionProviderResponse,
    ExtractionValidationError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderOutputValidationOutcome,
    ProviderRateLimitError,
    ProviderRejectedRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    build_extraction_prompt_package,
    build_extraction_schema_package,
    image_diagnostics_from_payload,
    sanitize_provider_payload,
    validate_provider_output,
)
from document_digitization_ai.media import (
    MediaStagingConfigurationError,
    MediaStagingError,
    MediaStagingInput,
    MediaStagingPort,
    MediaStagingResult,
    StagedMediaReference,
    StagedMediaReferenceKind,
)
from document_digitization_ai.providers import (
    ProviderInputContext,
    attach_staged_media,
    build_provider_input_context,
)
from document_digitization_ai.storage import (
    ArtifactLayoutError,
    ExtractionAttemptArtifactLayout,
    JobArtifactLayout,
    StoredExtractionAttemptArtifact,
)
from document_digitization_ai.storage.artifacts import validate_relative_artifact_path


class DocumentExtractionWorkflowError(RuntimeError):
    """Raised when local extraction workflow cannot complete."""


@dataclass(frozen=True, slots=True)
class DocumentExtractionRunSummary:
    job_id: str
    status: JobStatus
    attempt_id: str | None
    attempt_number: int | None
    provider_name: str
    model_name: str
    validation_outcome: str | None
    validation_issue_count: int | None
    result_available: bool
    error_type: str | None = None
    error_message: str | None = None
    raw_response_artifact_path: str | None = None
    sanitized_response_artifact_path: str | None = None


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
class _AttemptRunContext:
    attempt_id: str
    attempt_number: int
    provider_context: ProviderInputContext


@dataclass(frozen=True, slots=True)
class _WorkflowDependencies:
    session_factory: Callable[[], AsyncSession]
    job_artifact_layout: JobArtifactLayout
    attempt_artifact_layout: ExtractionAttemptArtifactLayout
    diagnostics_config: ImageDiagnosticsConfig


@dataclass(frozen=True, slots=True)
class _StoredImageArtifact:
    path: Path
    mime_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DocumentExtractionWorkflowService:
    repository: DocumentJobRepository | None
    extraction_settings: ExtractionSettings
    media_staging_service: MediaStagingPort
    extraction_provider: ExtractionProviderPort
    session_factory: Callable[[], AsyncSession] | None = None
    job_artifact_layout: JobArtifactLayout | None = None
    attempt_artifact_layout: ExtractionAttemptArtifactLayout | None = None
    diagnostics_config: ImageDiagnosticsConfig | None = None

    async def run_from_image(
        self,
        image_path: str | Path,
        user_mode_hint: DocumentModeHint = DocumentModeHint.AUTO,
    ) -> DocumentExtractionRunSummary:
        deps = self._require_end_to_end_dependencies()
        source_path = Path(image_path)
        job_id: str | None = None
        attempt_id: str | None = None
        attempt_number: int | None = None
        raw_artifact: StoredExtractionAttemptArtifact | None = None
        sanitized_artifact: StoredExtractionAttemptArtifact | None = None

        try:
            _validate_source_image_path(source_path)
            job_id = await self._create_job(
                user_mode_hint,
                deps,
            )
            stored_image = self._store_original_image_artifact(
                source_path,
                job_id,
                deps,
            )
            await self._attach_uploaded_image_metadata(job_id, stored_image, deps)
            diagnostics = collect_image_diagnostics(
                stored_image.path,
                config=deps.diagnostics_config,
            )
            await self._persist_diagnostics(job_id, stored_image.path, diagnostics, deps)

            attempt_context = await self._create_and_start_attempt(job_id, deps)
            attempt_id = attempt_context.attempt_id
            attempt_number = attempt_context.attempt_number

            media_staging = await self._stage_media(attempt_context.provider_context)
            await ExtractionAttemptLifecycleService(
                deps.session_factory
            ).record_media_staging_metadata(
                attempt_id,
                metadata=_safe_media_staging_metadata(media_staging),
            )
            _ensure_provider_usable_media(
                attempt_context.provider_context,
                media_staging,
            )
            staged_context = attach_staged_media(
                attempt_context.provider_context,
                media_staging.reference,
            )
            prompt_package = build_extraction_prompt_package(staged_context)
            schema_package = build_extraction_schema_package(staged_context)
            request = ExtractionProviderRequest(
                correlation_id=job_id,
                context=staged_context,
                staged_media=media_staging.reference,
                prompt_package=prompt_package,
                schema_package=schema_package,
            )

            provider_response = await self.extraction_provider.extract(request)
            raw_artifact = deps.attempt_artifact_layout.write_json_artifact(
                job_id=job_id,
                attempt_number=attempt_number,
                filename="provider_raw_response.json",
                payload=_raw_provider_response_artifact_payload(provider_response),
            )
            sanitized_payload = sanitize_provider_payload(provider_response)
            sanitized_artifact = deps.attempt_artifact_layout.write_json_artifact(
                job_id=job_id,
                attempt_number=attempt_number,
                filename="provider_sanitized_response.json",
                payload=sanitized_payload,
            )
            validation = validate_provider_output(
                provider_response,
                context=staged_context,
                image_diagnostics=diagnostics,
            )

            final_status = await self._finalize_success(
                job_id=job_id,
                attempt_id=attempt_id,
                provider_response=provider_response,
                validation=validation,
                raw_artifact=raw_artifact,
                sanitized_artifact=sanitized_artifact,
                deps=deps,
            )
        except Exception as exc:
            await self._persist_failure_state(
                error=exc,
                job_id=job_id,
                attempt_id=attempt_id,
                raw_artifact=raw_artifact,
                sanitized_artifact=sanitized_artifact,
                deps=deps,
            )
            failure = normalize_failure_metadata(
                exc,
                retryable=_is_retryable_error(exc),
            )
            msg = f"Document extraction workflow failed: {failure.error_message}"
            raise DocumentExtractionWorkflowError(msg) from exc

        return DocumentExtractionRunSummary(
            job_id=job_id,
            status=final_status,
            attempt_id=attempt_id,
            attempt_number=attempt_number,
            provider_name=provider_response.provider_name,
            model_name=provider_response.model_name,
            validation_outcome=validation.outcome.value,
            validation_issue_count=len(validation.validation_warnings),
            result_available=True,
            raw_response_artifact_path=raw_artifact.relative_path,
            sanitized_response_artifact_path=sanitized_artifact.relative_path,
        )

    async def run(self, job_id: str) -> DocumentExtractionWorkflowResult:
        repository = self._require_repository()
        job = await repository.require_job(job_id)
        if job.status is not JobStatus.IMAGE_DIAGNOSTICS_READY:
            msg = (
                "Document extraction workflow requires job status "
                f"{JobStatus.IMAGE_DIAGNOSTICS_READY.value}; got {job.status.value}"
            )
            raise DocumentExtractionWorkflowError(msg)

        try:
            context = build_provider_input_context(job, self.extraction_settings)
            media_staging = await self._stage_media(context)
            await repository.update_status(job.id, JobStatus.MEDIA_STAGED)

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

            await repository.update_status(job.id, JobStatus.EXTRACTION_RUNNING)
            provider_response = await self.extraction_provider.extract(request)
            await repository.update_status(job.id, JobStatus.EXTRACTION_SUCCEEDED)

            image_diagnostics = image_diagnostics_from_payload(
                _require_image_diagnostics_payload(job.image_diagnostics_payload)
            )
            validation = validate_provider_output(
                provider_response,
                context=staged_context,
                image_diagnostics=image_diagnostics,
            )
            validation_job_status = _validation_job_status(validation.outcome)
            await repository.attach_extraction_result(
                job.id,
                validation.extraction_result,
                validation_status=validation_job_status.value,
            )
            await repository.update_status(job.id, validation_job_status)
            updated_job = await repository.update_status(job.id, JobStatus.RESULT_READY)
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

    async def _create_job(
        self,
        user_mode_hint: DocumentModeHint,
        deps: _WorkflowDependencies,
    ) -> str:
        async with deps.session_factory() as session:
            try:
                repository = DocumentJobRepository(session)
                job = await repository.create_job(user_mode_hint)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return job.id

    def _store_original_image_artifact(
        self,
        source_path: Path,
        job_id: str,
        deps: _WorkflowDependencies,
    ) -> _StoredImageArtifact:
        artifact_paths = deps.job_artifact_layout.ensure_job_dirs(
            job_id,
            source_path.suffix,
        )
        copy2(source_path, artifact_paths.original_upload_path)
        return _StoredImageArtifact(
            path=artifact_paths.original_upload_path,
            mime_type=_guess_mime_type(artifact_paths.original_upload_path),
            size_bytes=artifact_paths.original_upload_path.stat().st_size,
        )

    async def _attach_uploaded_image_metadata(
        self,
        job_id: str,
        stored_image: _StoredImageArtifact,
        deps: _WorkflowDependencies,
    ) -> None:
        async with deps.session_factory() as session:
            try:
                repository = DocumentJobRepository(session)
                await repository.attach_uploaded_image_metadata(
                    job_id,
                    source_image_path=str(stored_image.path),
                    mime_type=stored_image.mime_type,
                    size_bytes=stored_image.size_bytes,
                )
                await repository.update_status(job_id, JobStatus.IMAGE_UPLOADED)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _persist_diagnostics(
        self,
        job_id: str,
        stored_image_path: Path,
        diagnostics: ImageDiagnostics,
        deps: _WorkflowDependencies,
    ) -> None:
        async with deps.session_factory() as session:
            try:
                repository = DocumentJobRepository(session)
                await repository.attach_uploaded_image_metadata(
                    job_id,
                    source_image_path=str(stored_image_path),
                    mime_type=diagnostics.file.mime_type,
                    size_bytes=diagnostics.file.file_size_bytes,
                )
                await repository.attach_image_diagnostics(job_id, diagnostics)
                await repository.update_status(
                    job_id,
                    JobStatus.IMAGE_DIAGNOSTICS_READY,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _create_and_start_attempt(
        self,
        job_id: str,
        deps: _WorkflowDependencies,
    ) -> _AttemptRunContext:
        async with deps.session_factory() as session:
            try:
                job_repository = DocumentJobRepository(session)
                attempt_repository = ExtractionAttemptRepository(session)
                job = await job_repository.require_job(job_id)
                await job_repository.update_status(job_id, JobStatus.EXTRACTION_RUNNING)
                provider_context = build_provider_input_context(
                    job,
                    self.extraction_settings,
                )
                request_metadata = build_safe_request_metadata(
                    provider_name=provider_context.extraction.provider_name.value,
                    model_name=provider_context.extraction.model,
                    schema_version=EXTRACTION_RESULT_SCHEMA_VERSION,
                    schema_mode=provider_context.extraction.provider_schema_mode.value,
                    metadata={
                        "structured_outputs_enabled": (
                            provider_context.extraction.structured_outputs_enabled
                        ),
                        "provider_require_parameters": (
                            provider_context.extraction.structured_outputs_require_parameters
                        ),
                    },
                )
                attempt = await attempt_repository.create_attempt(
                    job_id=job_id,
                    attempt_number=await attempt_repository.get_next_attempt_number(
                        job_id
                    ),
                    provider_name=provider_context.extraction.provider_name.value,
                    model_name=provider_context.extraction.model,
                    schema_version=EXTRACTION_RESULT_SCHEMA_VERSION,
                    schema_mode=provider_context.extraction.provider_schema_mode.value,
                    request_metadata_json=request_metadata,
                )
                attempt.status = ExtractionAttemptStatus.RUNNING
                attempt.started_at = utc_now()
                await attempt_repository.save(attempt)
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return _AttemptRunContext(
            attempt_id=attempt.id,
            attempt_number=attempt.attempt_number,
            provider_context=provider_context,
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

    async def _finalize_success(
        self,
        *,
        job_id: str,
        attempt_id: str,
        provider_response: ExtractionProviderResponse,
        validation,
        raw_artifact: StoredExtractionAttemptArtifact,
        sanitized_artifact: StoredExtractionAttemptArtifact,
        deps: _WorkflowDependencies,
    ) -> JobStatus:
        async with deps.session_factory() as session:
            try:
                job_repository = DocumentJobRepository(session)
                attempt_repository = ExtractionAttemptRepository(session)
                attempt = await attempt_repository.require_attempt(attempt_id)
                if attempt.status is not ExtractionAttemptStatus.RUNNING:
                    msg = (
                        "Cannot finalize extraction attempt success unless attempt "
                        f"is RUNNING; got {attempt.status.value}"
                    )
                    raise DocumentExtractionWorkflowError(msg)

                finished_at = utc_now()
                attempt.status = ExtractionAttemptStatus.SUCCEEDED
                attempt.finished_at = finished_at
                attempt.duration_ms = _duration_ms(attempt.started_at, finished_at)
                attempt.validation_outcome = validation.outcome.value
                attempt.validation_issue_count = len(validation.validation_warnings)
                attempt.response_metadata_json = build_safe_response_metadata(
                    _response_metadata(provider_response, validation)
                )
                attempt.raw_response_artifact_path = validate_relative_artifact_path(
                    raw_artifact.relative_path
                )
                attempt.raw_response_size_bytes = raw_artifact.size_bytes
                attempt.sanitized_response_artifact_path = (
                    validate_relative_artifact_path(sanitized_artifact.relative_path)
                )
                attempt.sanitized_response_size_bytes = sanitized_artifact.size_bytes
                await attempt_repository.save(attempt)

                validation_job_status = _validation_job_status(validation.outcome)
                await job_repository.attach_extraction_result(
                    job_id,
                    validation.extraction_result,
                    validation_status=validation_job_status.value,
                    completed_attempt_id=attempt_id,
                )
                await job_repository.update_status(job_id, JobStatus.EXTRACTION_SUCCEEDED)
                await job_repository.update_status(job_id, validation_job_status)
                updated_job = await job_repository.update_status(
                    job_id,
                    JobStatus.RESULT_READY,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
        return updated_job.status

    async def _persist_failure_state(
        self,
        *,
        error: Exception,
        job_id: str | None,
        attempt_id: str | None,
        raw_artifact: StoredExtractionAttemptArtifact | None,
        sanitized_artifact: StoredExtractionAttemptArtifact | None,
        deps: _WorkflowDependencies,
    ) -> None:
        if job_id is None:
            return
        try:
            if attempt_id is None:
                await self._mark_job_failed_safe(job_id, error, deps)
            else:
                await self._finalize_failure(
                    job_id=job_id,
                    attempt_id=attempt_id,
                    error=error,
                    raw_artifact=raw_artifact,
                    sanitized_artifact=sanitized_artifact,
                    deps=deps,
                )
        except Exception as failure_error:
            safe_message = sanitize_error_message(str(failure_error))
            msg = (
                "Document extraction workflow failed; additionally failed to persist "
                f"failure state: {safe_message}"
            )
            raise DocumentExtractionWorkflowError(msg) from error

    async def _mark_job_failed_safe(
        self,
        job_id: str,
        error: Exception,
        deps: _WorkflowDependencies,
    ) -> None:
        failure = normalize_failure_metadata(
            error,
            retryable=_is_retryable_error(error),
        )
        async with deps.session_factory() as session:
            try:
                repository = DocumentJobRepository(session)
                await repository.mark_failed(job_id, failure.error_message)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _finalize_failure(
        self,
        *,
        job_id: str,
        attempt_id: str,
        error: Exception,
        raw_artifact: StoredExtractionAttemptArtifact | None,
        sanitized_artifact: StoredExtractionAttemptArtifact | None,
        deps: _WorkflowDependencies,
    ) -> None:
        failure = normalize_failure_metadata(
            error,
            retryable=_is_retryable_error(error),
        )
        async with deps.session_factory() as session:
            try:
                job_repository = DocumentJobRepository(session)
                attempt_repository = ExtractionAttemptRepository(session)
                attempt = await attempt_repository.require_attempt(attempt_id)
                if attempt.status is not ExtractionAttemptStatus.RUNNING:
                    msg = (
                        "Cannot finalize extraction attempt failure unless attempt "
                        f"is RUNNING; got {attempt.status.value}"
                    )
                    raise DocumentExtractionWorkflowError(msg)

                finished_at = utc_now()
                attempt.status = ExtractionAttemptStatus.FAILED
                attempt.finished_at = finished_at
                attempt.duration_ms = _duration_ms(attempt.started_at, finished_at)
                attempt.error_type = failure.error_type
                attempt.error_message = failure.error_message
                attempt.retryable = failure.retryable
                if raw_artifact is not None:
                    attempt.raw_response_artifact_path = validate_relative_artifact_path(
                        raw_artifact.relative_path
                    )
                    attempt.raw_response_size_bytes = raw_artifact.size_bytes
                if sanitized_artifact is not None:
                    attempt.sanitized_response_artifact_path = (
                        validate_relative_artifact_path(sanitized_artifact.relative_path)
                    )
                    attempt.sanitized_response_size_bytes = sanitized_artifact.size_bytes
                await attempt_repository.save(attempt)
                await job_repository.mark_failed(job_id, failure.error_message)
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def _mark_job_failed(self, job_id: str, error: Exception) -> None:
        repository = self._require_repository()
        try:
            await repository.mark_failed(job_id, str(error))
        except Exception as mark_failed_error:
            msg = (
                f"Document extraction workflow failed for job {job_id}; additionally "
                f"failed to mark job as FAILED: {mark_failed_error}"
            )
            raise DocumentExtractionWorkflowError(msg) from error

    def _require_repository(self) -> DocumentJobRepository:
        if self.repository is None:
            msg = "repository is required for run(job_id)"
            raise DocumentExtractionWorkflowError(msg)
        return self.repository

    def _require_end_to_end_dependencies(self) -> _WorkflowDependencies:
        if self.session_factory is None:
            msg = "session_factory is required for run_from_image"
            raise DocumentExtractionWorkflowError(msg)
        if self.job_artifact_layout is None:
            msg = "job_artifact_layout is required for run_from_image"
            raise DocumentExtractionWorkflowError(msg)
        if self.attempt_artifact_layout is None:
            msg = "attempt_artifact_layout is required for run_from_image"
            raise DocumentExtractionWorkflowError(msg)
        return _WorkflowDependencies(
            session_factory=self.session_factory,
            job_artifact_layout=self.job_artifact_layout,
            attempt_artifact_layout=self.attempt_artifact_layout,
            diagnostics_config=self.diagnostics_config or ImageDiagnosticsConfig(),
        )


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


def _validate_source_image_path(source_path: Path) -> None:
    if not source_path.is_file():
        msg = f"Source image path must exist and be a file: {source_path}"
        raise DocumentExtractionWorkflowError(msg)
    if not source_path.suffix:
        msg = f"Source image path must include a file extension: {source_path}"
        raise DocumentExtractionWorkflowError(msg)


def _guess_mime_type(path: Path) -> str:
    mime_type, _ = guess_type(path.name)
    return mime_type or "application/octet-stream"


def _raw_provider_response_artifact_payload(
    response: ExtractionProviderResponse,
) -> object:
    if response.raw_response_json is not None:
        return response.raw_response_json
    return response.to_dict()


def _safe_media_staging_metadata(
    media_staging: MediaStagingResult,
) -> dict[str, object]:
    reference = media_staging.reference
    metadata: dict[str, object] = {
        "media_backend": _media_backend(reference),
        "staged_media_kind": reference.kind.value,
        "media_url_present": reference.kind is StagedMediaReferenceKind.PUBLIC_URL,
        "external_upload_performed": media_staging.external_upload_performed,
        "media_count": 1,
    }
    if reference.kind is StagedMediaReferenceKind.PUBLIC_URL:
        host = _public_url_host(reference.value)
        if host:
            metadata["media_url_host"] = host
    return metadata


def _ensure_provider_usable_media(
    context: ProviderInputContext,
    media_staging: MediaStagingResult,
) -> None:
    if (
        context.extraction.provider_name is ExtractionProviderName.OPENROUTER
        and media_staging.reference.kind is not StagedMediaReferenceKind.PUBLIC_URL
    ):
        msg = "Configured OpenRouter extraction requires PUBLIC_URL staged media"
        raise ProviderRejectedRequestError(msg)


def _media_backend(reference: StagedMediaReference) -> str:
    metadata_backend = reference.metadata.get("staging_backend")
    if isinstance(metadata_backend, str) and metadata_backend.strip():
        return metadata_backend.strip()
    if reference.kind is StagedMediaReferenceKind.LOCAL_FILE:
        return "none"
    return "unknown"


def _public_url_host(value: str) -> str | None:
    if not (value.startswith("http://") or value.startswith("https://")):
        return None
    remainder = value.split("://", 1)[1]
    host = remainder.split("/", 1)[0].split(":", 1)[0].strip()
    return host or None


def _response_metadata(
    provider_response: ExtractionProviderResponse,
    validation,
) -> dict[str, object]:
    extraction_result = validation.extraction_result
    metadata = dict(provider_response.metadata)
    metadata.update(
        {
            "finish_reason": provider_response.finish_reason,
            "model_name": provider_response.model_name,
            "raw_text_length": len(provider_response.raw_text or ""),
            "usable_content": True,
            "warning_count": len(extraction_result.warnings),
            "field_count": len(extraction_result.fields),
            "table_count": len(extraction_result.tables),
            "block_count": len(extraction_result.blocks),
        }
    )
    return metadata


def _is_retryable_error(error: Exception) -> bool:
    if isinstance(
        error,
        (ProviderRateLimitError, ProviderTimeoutError, ProviderUnavailableError),
    ):
        return True
    if isinstance(
        error,
        (
            ProviderAuthenticationError,
            ProviderConfigurationError,
            ProviderMalformedResponseError,
            ProviderRejectedRequestError,
            ExtractionValidationError,
            ImageDiagnosticsError,
            ArtifactLayoutError,
            ValueError,
        ),
    ):
        return False
    if isinstance(error, MediaStagingConfigurationError):
        return False
    if isinstance(error, MediaStagingError):
        message = str(error).lower()
        if "does not exist" in message or "must point to a file" in message:
            return False
        return True
    return False


def _duration_ms(started_at: datetime | None, finished_at: datetime) -> int:
    if started_at is None:
        return 0
    if started_at.tzinfo is None and finished_at.tzinfo is not None:
        finished_at = finished_at.replace(tzinfo=None)
    elif started_at.tzinfo is not None and finished_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=None)
    return max(0, int((finished_at - started_at).total_seconds() * 1000))
