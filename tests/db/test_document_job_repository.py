from pathlib import Path

import pytest

from document_digitization_ai.contracts import (
    DetectedDocumentType,
    DocumentInfo,
    DocumentModeHint,
    ExtractionResult,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageShape,
    JobStatus,
    RawText,
)
from document_digitization_ai.db.bootstrap import create_database_schema
from document_digitization_ai.db.repository import (
    DocumentJobRepository,
    InvalidJobStatusTransitionError,
    JobNotFoundError,
)
from document_digitization_ai.db.session import (
    create_async_engine_from_url,
    create_async_session_factory,
)


@pytest.mark.asyncio
async def test_document_job_repository_persists_job_metadata(tmp_path: Path) -> None:
    engine = create_async_engine_from_url(f"sqlite+aiosqlite:///{tmp_path / 'jobs.db'}")
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(
                DocumentModeHint.FORM,
                job_id="job-001",
            )
            await repository.attach_uploaded_image_metadata(
                job.id,
                source_image_path="data/uploads/job-001/original.jpg",
                mime_type="image/jpeg",
                size_bytes=1234,
            )
            await repository.attach_image_diagnostics(job.id, _image_diagnostics())
            await repository.update_status(job.id, JobStatus.IMAGE_UPLOADED)
            await session.commit()

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            persisted = await repository.require_job("job-001")

            assert persisted.status is JobStatus.IMAGE_UPLOADED
            assert persisted.user_mode_hint is DocumentModeHint.FORM
            assert persisted.source_image_path == "data/uploads/job-001/original.jpg"
            assert persisted.source_image_mime_type == "image/jpeg"
            assert persisted.source_image_size_bytes == 1234
            assert persisted.image_diagnostics_payload is not None
            assert persisted.image_diagnostics_payload["file"]["mime_type"] == "image/jpeg"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_document_job_repository_rejects_invalid_status_transition(
    tmp_path: Path,
) -> None:
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'invalid-transition.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-invalid-transition",
            )

            with pytest.raises(InvalidJobStatusTransitionError):
                await repository.update_status(job.id, JobStatus.RESULT_READY)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_document_job_repository_attaches_extraction_result(
    tmp_path: Path,
) -> None:
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'result.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(
                DocumentModeHint.PLAIN_TEXT,
                job_id="job-result",
            )
            await repository.attach_extraction_result(
                job.id,
                _extraction_result(),
                validation_status="VALIDATION_SUCCEEDED",
            )
            await session.commit()

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            persisted = await repository.require_job("job-result")

            assert persisted.validation_status == "VALIDATION_SUCCEEDED"
            assert persisted.extraction_result_payload is not None
            assert persisted.extraction_result_payload["raw_text"]["text"] == "hello"
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_document_job_repository_marks_failed_and_requires_existing_job(
    tmp_path: Path,
) -> None:
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'failed.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-failed",
            )
            await repository.mark_failed(job.id, "invalid image")
            await session.commit()

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            persisted = await repository.require_job("job-failed")

            assert persisted.status is JobStatus.FAILED
            assert persisted.error_message == "invalid image"
            with pytest.raises(JobNotFoundError):
                await repository.require_job("missing")
    finally:
        await engine.dispose()


def _image_diagnostics() -> ImageDiagnostics:
    return ImageDiagnostics(
        file=ImageFileMetadata(
            mime_type="image/jpeg",
            file_size_bytes=1234,
            file_extension=".jpg",
            sha256="a" * 64,
        ),
        image=ImageShape.from_dimensions(width=1200, height=1600, format="JPEG"),
    )


def _extraction_result() -> ExtractionResult:
    return ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.PLAIN_TEXT,
            detected_type=DetectedDocumentType.PLAIN_TEXT,
        ),
        image_diagnostics=_image_diagnostics(),
        raw_text=RawText(text="hello"),
    )
