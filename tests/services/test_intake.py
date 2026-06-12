from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.contracts import DocumentModeHint, JobStatus, WarningCode
from document_digitization_ai.db import (
    DocumentJob,
    DocumentJobRepository,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from document_digitization_ai.diagnostics import ImageDiagnosticsConfig
from document_digitization_ai.services import DocumentIntakeError, DocumentIntakeService
from document_digitization_ai.storage import JobArtifactLayout


@pytest.mark.asyncio
async def test_document_intake_service_stores_image_and_updates_job(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(10, 10, 10))
    engine = create_async_engine_from_url(f"sqlite+aiosqlite:///{tmp_path / 'intake.db'}")
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            service = DocumentIntakeService(
                repository=repository,
                artifact_layout=JobArtifactLayout(
                    uploads_root=tmp_path / "data" / "uploads",
                    results_root=tmp_path / "data" / "results",
                ),
                diagnostics_config=ImageDiagnosticsConfig(
                    hard_min_width_px=32,
                    hard_min_height_px=32,
                    low_resolution_min_width_px=800,
                    low_resolution_min_height_px=800,
                    too_dark_brightness_threshold=35.0,
                ),
            )

            result = await service.intake_local_image(
                source_image_path,
                DocumentModeHint.FORM,
            )
            job = await repository.require_job(result.job_id)

            assert result.final_job_status is JobStatus.IMAGE_DIAGNOSTICS_READY
            assert result.stored_original_image_path.is_file()
            assert result.stored_original_image_path.name == "original.jpg"
            assert result.image_diagnostics.file.mime_type == "image/jpeg"
            assert [warning.code for warning in result.warnings] == [
                WarningCode.LOW_RESOLUTION,
                WarningCode.LOW_CONTRAST,
                WarningCode.TOO_DARK,
            ]
            assert job.status is JobStatus.IMAGE_DIAGNOSTICS_READY
            assert job.user_mode_hint is DocumentModeHint.FORM
            assert job.source_image_path == str(result.stored_original_image_path)
            assert job.source_image_mime_type == "image/jpeg"
            assert job.source_image_size_bytes == result.stored_original_image_path.stat().st_size
            assert job.image_diagnostics_payload is not None
            assert job.image_diagnostics_payload["file"]["mime_type"] == "image/jpeg"
            await session.commit()

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            persisted = await repository.require_job(result.job_id)

            assert persisted.status is JobStatus.IMAGE_DIAGNOSTICS_READY
            assert persisted.image_diagnostics_payload is not None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("source_name", "create_source_directory", "create_extensionless_file"),
    [
        ("missing.jpg", False, False),
        ("source_directory.jpg", True, False),
        ("extensionless", False, True),
    ],
)
async def test_document_intake_service_pre_job_validation_does_not_create_job(
    tmp_path: Path,
    source_name: str,
    create_source_directory: bool,
    create_extensionless_file: bool,
) -> None:
    source_path = tmp_path / source_name
    if create_source_directory:
        source_path.mkdir()
    if create_extensionless_file:
        source_path.write_text("not an image", encoding="utf-8")

    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'pre-job-validation.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            service = DocumentIntakeService(
                repository=repository,
                artifact_layout=JobArtifactLayout(
                    uploads_root=tmp_path / "data" / "uploads",
                    results_root=tmp_path / "data" / "results",
                ),
                diagnostics_config=ImageDiagnosticsConfig(),
            )

            with pytest.raises(DocumentIntakeError):
                await service.intake_local_image(
                    source_path,
                    DocumentModeHint.AUTO,
                )

            assert await _count_document_jobs(session) == 0
            assert not (tmp_path / "data" / "uploads").exists()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_document_intake_service_marks_job_failed_after_created(
    tmp_path: Path,
) -> None:
    invalid_image_path = tmp_path / "invalid.jpg"
    invalid_image_path.write_text("not an image", encoding="utf-8")
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'failed-intake.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            service = DocumentIntakeService(
                repository=repository,
                artifact_layout=JobArtifactLayout(
                    uploads_root=tmp_path / "data" / "uploads",
                    results_root=tmp_path / "data" / "results",
                ),
                diagnostics_config=ImageDiagnosticsConfig(),
            )

            with pytest.raises(DocumentIntakeError):
                await service.intake_local_image(
                    invalid_image_path,
                    DocumentModeHint.AUTO,
                )

            failed_job = await repository.require_job(_only_created_job_id(tmp_path))
            assert failed_job.status is JobStatus.FAILED
            assert failed_job.error_message
            await session.commit()
    finally:
        await engine.dispose()


async def _count_document_jobs(session: AsyncSession) -> int:
    count = await session.scalar(select(func.count()).select_from(DocumentJob))
    assert count is not None
    return count


def _only_created_job_id(tmp_path: Path) -> str:
    upload_root = tmp_path / "data" / "uploads"
    job_dirs = [path.name for path in upload_root.iterdir()]
    assert len(job_dirs) == 1
    return job_dirs[0]


def _save_rgb_image(
    path: Path,
    *,
    size: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    image = Image.new("RGB", size, color=color)
    image.save(path)
