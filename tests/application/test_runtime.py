from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image
from sqlalchemy import func, inspect, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from document_digitization_ai.application import LocalDocumentApplication
from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.core import AppSettings
from document_digitization_ai.db import DocumentJob, create_async_session_factory
from document_digitization_ai.db.models import ExtractionAttempt
from document_digitization_ai.services import (
    DocumentExtractionWorkflowError,
    DocumentIntakeError,
)


@pytest.mark.asyncio
async def test_application_initializes_database_schema(tmp_path: Path) -> None:
    application = LocalDocumentApplication(_app_settings(tmp_path))
    try:
        await application.initialize_database()

        table_names = await _table_names(application.engine)
    finally:
        await application.close()

    assert "document_jobs" in table_names


@pytest.mark.asyncio
async def test_application_intake_local_image_commits_persisted_job(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    application = LocalDocumentApplication(_app_settings(tmp_path))
    try:
        await application.initialize_database()

        result = await application.intake_local_image(
            source_image_path,
            DocumentModeHint.MIXED_DOCUMENT,
        )
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            persisted_job = await session.get(DocumentJob, result.job_id)

        assert result.final_job_status is JobStatus.IMAGE_DIAGNOSTICS_READY
        assert result.stored_original_image_path.is_file()
        assert persisted_job is not None
        assert persisted_job.status is JobStatus.IMAGE_DIAGNOSTICS_READY
        assert persisted_job.user_mode_hint is DocumentModeHint.MIXED_DOCUMENT
        assert persisted_job.source_image_path == str(result.stored_original_image_path)
        assert persisted_job.image_diagnostics_payload is not None
    finally:
        await application.close()


@pytest.mark.asyncio
async def test_application_intake_failure_rolls_back_job_transaction(
    tmp_path: Path,
) -> None:
    invalid_image_path = tmp_path / "invalid.jpg"
    invalid_image_path.write_text("not an image", encoding="utf-8")
    application = LocalDocumentApplication(_app_settings(tmp_path))
    try:
        await application.initialize_database()

        with pytest.raises(DocumentIntakeError):
            await application.intake_local_image(
                invalid_image_path,
                DocumentModeHint.AUTO,
            )
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            persisted_count = await _count_document_jobs(session)
    finally:
        await application.close()

    assert persisted_count == 0


@pytest.mark.asyncio
async def test_application_fake_extraction_commits_result_ready_job(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    application = LocalDocumentApplication(_app_settings(tmp_path))
    try:
        await application.initialize_database()
        intake_result = await application.intake_local_image(
            source_image_path,
            DocumentModeHint.PLAIN_TEXT,
        )

        extraction_result = await application.run_fake_extraction(intake_result.job_id)
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            persisted_job = await session.get(DocumentJob, intake_result.job_id)
    finally:
        await application.close()

    assert extraction_result.final_job_status is JobStatus.RESULT_READY
    assert extraction_result.validation_outcome.value == "succeeded"
    assert persisted_job is not None
    assert persisted_job.status is JobStatus.RESULT_READY
    assert persisted_job.validation_status == JobStatus.VALIDATION_SUCCEEDED.value
    assert persisted_job.extraction_result_payload is not None


@pytest.mark.asyncio
async def test_application_fake_extraction_failure_persists_failed_job_state(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    application = LocalDocumentApplication(_app_settings(tmp_path))
    try:
        await application.initialize_database()
        intake_result = await application.intake_local_image(
            source_image_path,
            DocumentModeHint.AUTO,
        )
        intake_result.stored_original_image_path.unlink()

        with pytest.raises(DocumentExtractionWorkflowError):
            await application.run_fake_extraction(intake_result.job_id)
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            persisted_job = await session.get(DocumentJob, intake_result.job_id)
    finally:
        await application.close()

    assert persisted_job is not None
    assert persisted_job.status is JobStatus.FAILED
    assert persisted_job.error_message is not None
    assert persisted_job.extraction_result_payload is None


@pytest.mark.asyncio
async def test_application_real_extraction_from_image_runs_configured_backend_workflow(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    application = LocalDocumentApplication(_app_settings(tmp_path))
    try:
        await application.initialize_database()

        summary = await application.run_real_extraction_from_image(
            source_image_path,
            DocumentModeHint.PLAIN_TEXT,
        )
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            persisted_job = await session.get(DocumentJob, summary.job_id)
            attempts = (await session.scalars(select(ExtractionAttempt))).all()
    finally:
        await application.close()

    assert summary.status is JobStatus.RESULT_READY
    assert summary.attempt_id is not None
    assert persisted_job is not None
    assert persisted_job.status is JobStatus.RESULT_READY
    assert persisted_job.completed_attempt_id == summary.attempt_id
    assert len(attempts) == 1
    assert attempts[0].raw_response_artifact_path == summary.raw_response_artifact_path


def _app_settings(tmp_path: Path) -> AppSettings:
    kwargs = cast(
        dict[str, Any],
        {
            "_env_file": None,
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
            "llm_model": "openai/test-vision",
            "storage_data_dir": tmp_path / "data",
            "storage_uploads_dir": tmp_path / "data" / "uploads",
            "storage_results_dir": tmp_path / "data" / "results",
            "image_diagnostics_hard_min_width_px": 32,
            "image_diagnostics_hard_min_height_px": 32,
        },
    )
    return AppSettings(**kwargs)


async def _table_names(engine: AsyncEngine) -> set[str]:
    async with engine.connect() as connection:
        return await connection.run_sync(
            lambda sync_connection: set(inspect(sync_connection).get_table_names())
        )


async def _count_document_jobs(session: AsyncSession) -> int:
    count = await session.scalar(select(func.count()).select_from(DocumentJob))
    assert count is not None
    return count


def _save_rgb_image(
    path: Path,
    *,
    size: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    image = Image.new("RGB", size, color=color)
    image.save(path)
