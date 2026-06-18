from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.core import ExtractionProviderName, ExtractionSettings
from document_digitization_ai.db import (
    DocumentJob,
    ExtractionAttempt,
    ExtractionAttemptRepository,
    ExtractionAttemptStatus,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from document_digitization_ai.diagnostics import ImageDiagnosticsConfig
from document_digitization_ai.extraction import (
    ExtractionProviderRequest,
    ExtractionProviderResponse,
    FakeExtractionProvider,
    ProviderAuthenticationError,
    ProviderTimeoutError,
)
from document_digitization_ai.media import (
    LocalNoopMediaStagingService,
    MediaStagingError,
    MediaStagingInput,
    MediaStagingResult,
    StagedMediaReference,
    StagedMediaReferenceKind,
)
from document_digitization_ai.services import (
    DocumentExtractionWorkflowError,
    DocumentExtractionWorkflowService,
)
from document_digitization_ai.storage import (
    ExtractionAttemptArtifactLayout,
    JobArtifactLayout,
)


@pytest.mark.asyncio
async def test_run_from_image_persists_end_to_end_result_attempt_and_artifacts(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, "e2e-success.db")
    provider = ObservingFakeProvider(session_factory)
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        provider=provider,
    )

    try:
        summary = await service.run_from_image(source_image_path, DocumentModeHint.FORM)

        async with session_factory() as session:
            job = await session.get(DocumentJob, summary.job_id)
            attempts = await _attempts_for_job(session, summary.job_id)

        assert provider.calls == 1
        assert provider.observed_committed_running is True
        assert summary.status is JobStatus.RESULT_READY
        assert summary.attempt_id is not None
        assert summary.validation_outcome == "succeeded"
        assert summary.validation_issue_count == 0
        assert summary.result_available is True
        assert job is not None
        assert job.status is JobStatus.RESULT_READY
        assert job.image_diagnostics_payload is not None
        assert job.extraction_result_payload is not None
        assert job.extraction_result_payload["raw_text"]["text"] == (
            "Deterministic fake extracted text."
        )
        assert job.completed_attempt_id == summary.attempt_id
        assert len(attempts) == 1

        attempt = attempts[0]
        assert attempt.status is ExtractionAttemptStatus.SUCCEEDED
        assert attempt.attempt_number == 1
        assert attempt.raw_response_artifact_path == summary.raw_response_artifact_path
        assert attempt.sanitized_response_artifact_path == (
            summary.sanitized_response_artifact_path
        )
        assert attempt.validation_outcome == "succeeded"
        assert attempt.validation_issue_count == 0
        assert attempt.retryable is None
        assert "delete_url" not in json.dumps(attempt.request_metadata_json)
        assert str(source_image_path) not in json.dumps(attempt.request_metadata_json)
        assert attempt.request_metadata_json["staged_media_kind"] == "local_file"
        assert attempt.request_metadata_json["media_backend"] == "none"

        raw_path = _artifact_path(tmp_path, attempt.raw_response_artifact_path)
        sanitized_path = _artifact_path(tmp_path, attempt.sanitized_response_artifact_path)
        assert raw_path.is_file()
        assert sanitized_path.is_file()
        raw_payload = json.loads(raw_path.read_text(encoding="utf-8"))
        sanitized_payload = json.loads(sanitized_path.read_text(encoding="utf-8"))
        assert raw_payload["provider"] == "fake"
        assert "raw_text" in sanitized_payload
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_partial_validation_still_reaches_result_ready(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, "partial.db")
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        provider=FakeExtractionProvider(
            raw_payload={"raw_text": {"text": "Only raw text."}},
            raw_text="Only raw text.",
        ),
    )

    try:
        summary = await service.run_from_image(source_image_path, DocumentModeHint.TABLE)

        async with session_factory() as session:
            job = await session.get(DocumentJob, summary.job_id)
            attempts = await _attempts_for_job(session, summary.job_id)

        assert summary.status is JobStatus.RESULT_READY
        assert summary.validation_outcome == "partial"
        assert job is not None
        assert job.status is JobStatus.RESULT_READY
        assert attempts[0].status is ExtractionAttemptStatus.SUCCEEDED
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_invalid_path_creates_no_job(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path, "missing.db")
    service = _workflow_service(tmp_path, session_factory=session_factory)

    try:
        with pytest.raises(DocumentExtractionWorkflowError):
            await service.run_from_image(tmp_path / "missing.jpg", DocumentModeHint.AUTO)

        async with session_factory() as session:
            count = await session.scalar(select(func.count()).select_from(DocumentJob))
        assert count == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_diagnostics_failure_marks_job_failed_without_attempt(
    tmp_path: Path,
) -> None:
    invalid_image_path = tmp_path / "invalid.jpg"
    invalid_image_path.write_text("not an image", encoding="utf-8")
    engine, session_factory = await _session_factory(tmp_path, "diagnostics-failure.db")
    service = _workflow_service(tmp_path, session_factory=session_factory)

    try:
        with pytest.raises(DocumentExtractionWorkflowError, match="valid image"):
            await service.run_from_image(invalid_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            jobs = (await session.scalars(select(DocumentJob))).all()
            attempts = (await session.scalars(select(ExtractionAttempt))).all()

        assert len(jobs) == 1
        assert jobs[0].status is JobStatus.FAILED
        assert jobs[0].error_message is not None
        assert attempts == []
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_artifact_setup_failure_after_job_creation_marks_failed(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    uploads_root_file = tmp_path / "uploads-root-file"
    uploads_root_file.write_text("not a directory", encoding="utf-8")
    engine, session_factory = await _session_factory(tmp_path, "upload-copy-failure.db")
    media_staging = CountingMediaStagingService()
    provider = CountingProvider()
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        job_artifact_layout=JobArtifactLayout(
            uploads_root=uploads_root_file,
            results_root=tmp_path / "data" / "results",
        ),
        media_staging_service=media_staging,
        provider=provider,
    )

    try:
        with pytest.raises(DocumentExtractionWorkflowError):
            await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            jobs = (await session.scalars(select(DocumentJob))).all()
            attempts = (await session.scalars(select(ExtractionAttempt))).all()

        assert len(jobs) == 1
        assert jobs[0].status is JobStatus.FAILED
        assert jobs[0].source_image_path is None
        assert jobs[0].error_message is not None
        assert str(tmp_path) not in jobs[0].error_message
        assert attempts == []
        assert media_staging.calls == 0
        assert provider.calls == 0
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_media_failure_marks_attempt_failed_and_skips_provider(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, "media-failure.db")
    provider = CountingProvider()
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        media_staging_service=FailingMediaStagingService(
            MediaStagingError(
                r"temporary media unavailable api_key=secret C:\Users\User\image.jpg"
            )
        ),
        provider=provider,
    )

    try:
        with pytest.raises(DocumentExtractionWorkflowError):
            await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            job = await _single_job(session)
            attempts = await _attempts_for_job(session, job.id)

        assert provider.calls == 0
        assert job.status is JobStatus.FAILED
        assert "secret" not in (job.error_message or "")
        assert r"C:\Users\User" not in (job.error_message or "")
        assert attempts[0].status is ExtractionAttemptStatus.FAILED
        assert attempts[0].retryable is True
        assert attempts[0].raw_response_artifact_path is None
        assert attempts[0].sanitized_response_artifact_path is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_openrouter_requires_public_media_before_provider_call(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, "openrouter-media.db")
    provider = CountingProvider()
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        extraction_settings=ExtractionSettings(
            provider_name=ExtractionProviderName.OPENROUTER,
            model="openai/test-vision",
        ),
        provider=provider,
    )

    try:
        with pytest.raises(DocumentExtractionWorkflowError, match="PUBLIC_URL"):
            await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            job = await _single_job(session)
            attempts = await _attempts_for_job(session, job.id)

        assert provider.calls == 0
        assert job.status is JobStatus.FAILED
        assert attempts[0].status is ExtractionAttemptStatus.FAILED
        assert attempts[0].error_type == "ProviderRejectedRequestError"
        assert attempts[0].retryable is False
        assert attempts[0].request_metadata_json["staged_media_kind"] == "local_file"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_provider_retryable_and_non_retryable_failures(
    tmp_path: Path,
) -> None:
    timeout_attempt = await _failed_provider_attempt(
        tmp_path,
        database_name="provider-timeout.db",
        error=ProviderTimeoutError("provider timed out"),
    )
    auth_attempt = await _failed_provider_attempt(
        tmp_path,
        database_name="provider-auth.db",
        error=ProviderAuthenticationError("OPENROUTER_API_KEY=secret is invalid"),
    )

    assert timeout_attempt.error_type == "ProviderTimeoutError"
    assert timeout_attempt.retryable is True
    assert auth_attempt.error_type == "ProviderAuthenticationError"
    assert auth_attempt.retryable is False
    assert "secret" not in (auth_attempt.error_message or "")


@pytest.mark.asyncio
async def test_run_from_image_malformed_provider_payload_preserves_raw_only(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, "malformed-payload.db")
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        provider=FakeExtractionProvider(raw_payload=[]),
    )

    try:
        with pytest.raises(DocumentExtractionWorkflowError, match="raw_payload"):
            await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            job = await _single_job(session)
            attempts = await _attempts_for_job(session, job.id)

        assert job.status is JobStatus.FAILED
        assert attempts[0].status is ExtractionAttemptStatus.FAILED
        assert attempts[0].retryable is False
        assert attempts[0].raw_response_artifact_path is not None
        assert attempts[0].sanitized_response_artifact_path is None
        assert _artifact_path(tmp_path, attempts[0].raw_response_artifact_path).is_file()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_validation_failure_preserves_raw_and_sanitized_artifacts(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, "validation-failure.db")
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        provider=FakeExtractionProvider(raw_payload={}),
    )

    try:
        with pytest.raises(DocumentExtractionWorkflowError, match="usable extraction"):
            await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            job = await _single_job(session)
            attempts = await _attempts_for_job(session, job.id)

        assert job.status is JobStatus.FAILED
        assert attempts[0].status is ExtractionAttemptStatus.FAILED
        assert attempts[0].retryable is False
        assert attempts[0].raw_response_artifact_path is not None
        assert attempts[0].sanitized_response_artifact_path is not None
        assert _artifact_path(tmp_path, attempts[0].raw_response_artifact_path).is_file()
        assert _artifact_path(
            tmp_path,
            attempts[0].sanitized_response_artifact_path,
        ).is_file()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_artifact_write_failure_fails_safely(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    artifact_root_file = tmp_path / "artifact-root-file"
    artifact_root_file.write_text("not a directory", encoding="utf-8")
    engine, session_factory = await _session_factory(tmp_path, "artifact-failure.db")
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        attempt_artifact_root=artifact_root_file,
    )

    try:
        with pytest.raises(DocumentExtractionWorkflowError):
            await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            job = await _single_job(session)
            attempts = await _attempts_for_job(session, job.id)

        assert job.status is JobStatus.FAILED
        assert attempts[0].status is ExtractionAttemptStatus.FAILED
        assert attempts[0].retryable is False
        assert attempts[0].raw_response_artifact_path is None
        assert attempts[0].sanitized_response_artifact_path is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_run_from_image_records_safe_public_url_staging_metadata(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, "public-url-media.db")
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        media_staging_service=PublicUrlMediaStagingService(),
    )

    try:
        summary = await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            attempts = await _attempts_for_job(session, summary.job_id)

        metadata = attempts[0].request_metadata_json
        serialized = json.dumps(metadata, sort_keys=True)
        assert metadata["media_backend"] == "imgbb"
        assert metadata["staged_media_kind"] == "public_url"
        assert metadata["media_url_present"] is True
        assert metadata["media_url_host"] == "i.ibb.co"
        assert metadata["external_upload_performed"] is True
        assert "delete_url" not in serialized
        assert "delete/private" not in serialized
        assert "staged.jpg" not in serialized
        assert str(source_image_path) not in serialized
    finally:
        await engine.dispose()


@dataclass(slots=True)
class ObservingFakeProvider:
    session_factory: Callable[[], AsyncSession]
    calls: int = 0
    observed_committed_running: bool = False

    async def extract(
        self,
        request: ExtractionProviderRequest,
    ) -> ExtractionProviderResponse:
        self.calls += 1
        async with self.session_factory() as session:
            job = await session.get(DocumentJob, request.context.job_id)
            active_attempt = await ExtractionAttemptRepository(
                session
            ).get_active_attempt_for_job(request.context.job_id)
        assert job is not None
        assert job.status is JobStatus.EXTRACTION_RUNNING
        assert active_attempt is not None
        assert active_attempt.status is ExtractionAttemptStatus.RUNNING
        self.observed_committed_running = True
        return await FakeExtractionProvider().extract(request)


@dataclass(slots=True)
class CountingProvider:
    calls: int = 0

    async def extract(
        self,
        request: ExtractionProviderRequest,
    ) -> ExtractionProviderResponse:
        self.calls += 1
        return await FakeExtractionProvider().extract(request)


@dataclass(slots=True)
class CountingMediaStagingService:
    calls: int = 0

    async def stage(self, media: MediaStagingInput) -> MediaStagingResult:
        self.calls += 1
        return await LocalNoopMediaStagingService().stage(media)


@dataclass(frozen=True, slots=True)
class RaisingProvider:
    error: Exception

    async def extract(
        self,
        request: ExtractionProviderRequest,
    ) -> ExtractionProviderResponse:
        raise self.error


@dataclass(frozen=True, slots=True)
class FailingMediaStagingService:
    error: Exception

    async def stage(self, media: MediaStagingInput) -> MediaStagingResult:
        raise self.error


@dataclass(frozen=True, slots=True)
class PublicUrlMediaStagingService:
    async def stage(self, media: MediaStagingInput) -> MediaStagingResult:
        return MediaStagingResult(
            reference=StagedMediaReference(
                kind=StagedMediaReferenceKind.PUBLIC_URL,
                value="https://i.ibb.co/example/staged.jpg",
                mime_type=media.mime_type,
                file_size_bytes=media.file_size_bytes,
                sha256=media.sha256,
                metadata={
                    "staging_backend": "imgbb",
                    "delete_url": "https://ibb.co/delete/private",
                },
            ),
            external_upload_performed=True,
        )


async def _failed_provider_attempt(
    tmp_path: Path,
    *,
    database_name: str,
    error: Exception,
) -> ExtractionAttempt:
    source_image_path = tmp_path / f"{database_name}.jpg"
    _save_rgb_image(source_image_path)
    engine, session_factory = await _session_factory(tmp_path, database_name)
    service = _workflow_service(
        tmp_path,
        session_factory=session_factory,
        provider=RaisingProvider(error),
    )
    try:
        with pytest.raises(DocumentExtractionWorkflowError):
            await service.run_from_image(source_image_path, DocumentModeHint.AUTO)

        async with session_factory() as session:
            job = await _single_job(session)
            attempts = await _attempts_for_job(session, job.id)
            return attempts[0]
    finally:
        await engine.dispose()


async def _session_factory(
    tmp_path: Path,
    database_name: str,
):
    engine = create_async_engine_from_url(f"sqlite+aiosqlite:///{tmp_path / database_name}")
    await create_database_schema(engine)
    return engine, create_async_session_factory(engine)


def _workflow_service(
    tmp_path: Path,
    *,
    session_factory: Callable[[], AsyncSession],
    extraction_settings: ExtractionSettings | None = None,
    job_artifact_layout: JobArtifactLayout | None = None,
    provider: Any | None = None,
    media_staging_service: Any | None = None,
    attempt_artifact_root: Path | None = None,
) -> DocumentExtractionWorkflowService:
    return DocumentExtractionWorkflowService(
        repository=None,
        extraction_settings=extraction_settings
        or ExtractionSettings(
            provider_name=ExtractionProviderName.FAKE,
            model="openai/test-vision",
        ),
        media_staging_service=media_staging_service or LocalNoopMediaStagingService(),
        extraction_provider=provider or FakeExtractionProvider(),
        session_factory=session_factory,
        job_artifact_layout=job_artifact_layout
        or JobArtifactLayout(
            uploads_root=tmp_path / "data" / "uploads",
            results_root=tmp_path / "data" / "results",
        ),
        attempt_artifact_layout=ExtractionAttemptArtifactLayout(
            attempt_artifact_root or tmp_path / "data" / "results"
        ),
        diagnostics_config=ImageDiagnosticsConfig(
            hard_min_width_px=32,
            hard_min_height_px=32,
        ),
    )


async def _attempts_for_job(
    session: AsyncSession,
    job_id: str,
) -> tuple[ExtractionAttempt, ...]:
    return await ExtractionAttemptRepository(session).list_attempts_for_job(job_id)


async def _single_job(session: AsyncSession) -> DocumentJob:
    jobs = (await session.scalars(select(DocumentJob))).all()
    assert len(jobs) == 1
    return jobs[0]


def _artifact_path(tmp_path: Path, relative_path: str | None) -> Path:
    assert relative_path is not None
    return tmp_path / "data" / "results" / Path(*relative_path.split("/"))


def _save_rgb_image(
    path: Path,
    *,
    size: tuple[int, int] = (120, 120),
    color: tuple[int, int, int] = (128, 128, 128),
) -> None:
    image = Image.new("RGB", size, color=color)
    image.save(path)
