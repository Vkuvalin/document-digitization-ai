from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.contracts import (
    DetectedDocumentType,
    DocumentInfo,
    DocumentModeHint,
    ExtractionMetadata,
    ExtractionResult,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageShape,
    JobStatus,
    RawText,
    Warning,
    WarningCode,
)
from document_digitization_ai.db import (
    DocumentJob,
    DocumentJobRepository,
    ExtractionAttemptRepository,
    ExtractionAttemptStatus,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from document_digitization_ai.services import DocumentResultExportService


@pytest.mark.asyncio
async def test_export_job_result_markdown_renders_without_artifact_or_status_mutation(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "export-success.db")
    job_id = "job-export-success"
    try:
        await _persist_job_with_result(session_factory, job_id)

        async with session_factory() as session:
            service = _export_service(session)
            assert not hasattr(service, "extraction_provider")
            assert not hasattr(service, "media_staging_service")

            result = await service.export_job_result_markdown(job_id)

        async with session_factory() as session:
            persisted_job = await session.get(DocumentJob, job_id)

        assert result.result_available is True
        assert result.markdown is not None
        assert result.artifact_path is None
        assert "Persisted text" in result.markdown
        assert "Проверка пройдена" in result.markdown
        assert "Extraction Metadata" not in result.markdown
        assert "Provider" not in result.markdown
        assert "openai/test-vision" not in result.markdown
        assert job_id not in result.markdown
        assert persisted_job is not None
        assert persisted_job.status is JobStatus.RESULT_READY
        assert not (
            tmp_path
            / "data"
            / "results"
            / "jobs"
            / job_id
            / "exports"
            / "result.md"
        ).exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_export_job_result_markdown_handles_job_not_found(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path, "not-found.db")
    try:
        async with session_factory() as session:
            result = await _export_service(session).export_job_result_markdown(
                "missing-job"
            )

        assert result.result_available is False
        assert result.error_type == "job_not_found"
        assert result.markdown is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_export_job_result_markdown_handles_job_without_result(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "without-result.db")
    job_id = "job-without-result"
    try:
        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(DocumentModeHint.AUTO, job_id=job_id)
            job.status = JobStatus.FAILED
            await session.commit()

        async with session_factory() as session:
            result = await _export_service(session).export_job_result_markdown(job_id)

        assert result.result_available is False
        assert result.error_type == "result_unavailable"
        assert result.markdown is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_export_job_result_markdown_handles_malformed_payload(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "malformed.db")
    job_id = "job-malformed"
    try:
        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(DocumentModeHint.AUTO, job_id=job_id)
            job.status = JobStatus.RESULT_READY
            job.extraction_result_payload = {"document": {}}
            await session.commit()

        async with session_factory() as session:
            result = await _export_service(session).export_job_result_markdown(job_id)

        assert result.result_available is False
        assert result.error_type == "malformed_result_payload"
        assert result.markdown is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_export_summary_uses_attempt_validation_when_job_status_missing(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "attempt-outcome.db")
    job_id = "job-attempt-outcome"
    try:
        await _persist_job_with_result(
            session_factory,
            job_id,
            validation_status=None,
            attempt_validation_outcome="partial",
        )

        async with session_factory() as session:
            result = await _export_service(session).export_job_result_markdown(job_id)

        assert result.result_available is True
        assert result.markdown is not None
        assert "Частичная проверка" in result.markdown
        assert "partial |" not in result.markdown
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_export_summary_uses_unknown_without_explicit_validation_metadata(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "unknown-outcome.db")
    job_id = "job-unknown-outcome"
    try:
        await _persist_job_with_result(
            session_factory,
            job_id,
            validation_status=None,
            result=_result(with_warning=True),
        )

        async with session_factory() as session:
            result = await _export_service(session).export_job_result_markdown(job_id)

        assert result.result_available is True
        assert result.markdown is not None
        assert "Неизвестно" in result.markdown
        assert "unknown |" not in result.markdown
        assert "partial |" not in result.markdown
    finally:
        await engine.dispose()


async def _session_factory(
    tmp_path: Path,
    database_name: str,
):
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / database_name}"
    )
    await create_database_schema(engine)
    return engine, create_async_session_factory(engine)


def _export_service(
    session: AsyncSession,
) -> DocumentResultExportService:
    return DocumentResultExportService(
        repository=DocumentJobRepository(session),
        attempt_repository=ExtractionAttemptRepository(session),
    )


async def _persist_job_with_result(
    session_factory,
    job_id: str,
    *,
    validation_status: str | None = JobStatus.VALIDATION_SUCCEEDED.value,
    attempt_validation_outcome: str | None = None,
    result: ExtractionResult | None = None,
) -> None:
    async with session_factory() as session:
        repository = DocumentJobRepository(session)
        job = await repository.create_job(DocumentModeHint.FORM, job_id=job_id)
        job.status = JobStatus.RESULT_READY
        job.validation_status = validation_status
        job.extraction_result_payload = (result or _result()).to_dict()
        if attempt_validation_outcome is not None:
            attempt = await ExtractionAttemptRepository(session).create_attempt(
                job_id=job_id,
                attempt_number=1,
                provider_name="fake",
                model_name="openai/test-vision",
                schema_version="extraction_result_v0",
                schema_mode="json_schema",
                request_metadata_json={},
            )
            attempt.status = ExtractionAttemptStatus.SUCCEEDED
            attempt.validation_outcome = attempt_validation_outcome
            job.completed_attempt_id = attempt.id
        await session.commit()


def _result(*, with_warning: bool = False) -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
            language="ru",
        ),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/jpeg",
                file_size_bytes=123,
                file_extension=".jpg",
            ),
            image=ImageShape.from_dimensions(width=120, height=120),
        ),
        raw_text=RawText(text="Persisted text", confidence=0.9),
        warnings=(
            Warning(
                code=WarningCode.PARTIAL_EXTRACTION,
                message="Warning must not imply validation outcome.",
            ),
        )
        if with_warning
        else (),
        metadata=ExtractionMetadata(provider="fake", model="openai/test-vision"),
    )
