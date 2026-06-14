from pathlib import Path

import pytest
from PIL import Image

from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.core import ExtractionSettings
from document_digitization_ai.db import (
    DocumentJobRepository,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from document_digitization_ai.diagnostics import ImageDiagnosticsConfig
from document_digitization_ai.extraction import FakeExtractionProvider
from document_digitization_ai.media import LocalNoopMediaStagingService
from document_digitization_ai.services import (
    DocumentExtractionWorkflowError,
    DocumentExtractionWorkflowService,
    DocumentIntakeService,
)
from document_digitization_ai.storage import JobArtifactLayout


@pytest.mark.asyncio
async def test_extraction_workflow_persists_validated_result_and_reaches_result_ready(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'workflow-success.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            intake_result = await _intake_service(repository, tmp_path).intake_local_image(
                source_image_path,
                DocumentModeHint.FORM,
            )
            workflow = _workflow_service(repository)

            result = await workflow.run(intake_result.job_id)
            persisted = await repository.require_job(result.job_id)

            assert result.final_job_status is JobStatus.RESULT_READY
            assert result.validation_outcome.value == "succeeded"
            assert result.media_staging.external_upload_performed is False
            assert result.staged_media_reference.value == str(
                intake_result.stored_original_image_path
            )
            assert result.raw_provider_response.raw_payload is not None
            assert result.extraction_result.raw_text.text == (
                "Deterministic fake extracted text."
            )
            assert persisted.status is JobStatus.RESULT_READY
            assert persisted.validation_status == JobStatus.VALIDATION_SUCCEEDED.value
            assert persisted.extraction_result_payload is not None
            assert persisted.extraction_result_payload["raw_text"]["text"] == (
                "Deterministic fake extracted text."
            )
            assert "raw_payload" not in persisted.extraction_result_payload
            await session.commit()
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_extraction_workflow_persists_partial_validation_result(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'workflow-partial.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            intake_result = await _intake_service(repository, tmp_path).intake_local_image(
                source_image_path,
                DocumentModeHint.TABLE,
            )
            workflow = _workflow_service(
                repository,
                provider=FakeExtractionProvider(
                    raw_payload={"raw_text": {"text": "Only raw text."}},
                    raw_text="Only raw text.",
                ),
            )

            result = await workflow.run(intake_result.job_id)
            persisted = await repository.require_job(result.job_id)

            assert result.final_job_status is JobStatus.RESULT_READY
            assert result.validation_outcome.value == "partial"
            assert persisted.status is JobStatus.RESULT_READY
            assert persisted.validation_status == JobStatus.VALIDATION_PARTIAL.value
            assert persisted.extraction_result_payload is not None
            assert persisted.extraction_result_payload["warnings"]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_extraction_workflow_rejects_invalid_initial_status_without_mutation(
    tmp_path: Path,
) -> None:
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'workflow-invalid-status.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(DocumentModeHint.AUTO)

            with pytest.raises(DocumentExtractionWorkflowError, match="requires job status"):
                await _workflow_service(repository).run(job.id)

            persisted = await repository.require_job(job.id)
            assert persisted.status is JobStatus.CREATED
            assert persisted.error_message is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_extraction_workflow_marks_job_failed_on_provider_failure(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'workflow-provider-failure.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            intake_result = await _intake_service(repository, tmp_path).intake_local_image(
                source_image_path,
                DocumentModeHint.AUTO,
            )
            workflow = _workflow_service(
                repository,
                provider=FakeExtractionProvider(fail_with_message="configured failure"),
            )

            with pytest.raises(DocumentExtractionWorkflowError, match="configured failure"):
                await workflow.run(intake_result.job_id)

            failed = await repository.require_job(intake_result.job_id)
            assert failed.status is JobStatus.FAILED
            assert "configured failure" in (failed.error_message or "")
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_extraction_workflow_marks_job_failed_on_validation_failure(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'workflow-validation-failure.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            intake_result = await _intake_service(repository, tmp_path).intake_local_image(
                source_image_path,
                DocumentModeHint.AUTO,
            )
            workflow = _workflow_service(
                repository,
                provider=FakeExtractionProvider(raw_payload={}),
            )

            with pytest.raises(DocumentExtractionWorkflowError, match="usable extraction"):
                await workflow.run(intake_result.job_id)

            failed = await repository.require_job(intake_result.job_id)
            assert failed.status is JobStatus.FAILED
            assert failed.extraction_result_payload is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_extraction_workflow_marks_job_failed_on_missing_local_media(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path, size=(120, 120), color=(128, 128, 128))
    engine = create_async_engine_from_url(
        f"sqlite+aiosqlite:///{tmp_path / 'workflow-media-failure.db'}"
    )
    try:
        await create_database_schema(engine)
        session_factory = create_async_session_factory(engine)

        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            intake_result = await _intake_service(repository, tmp_path).intake_local_image(
                source_image_path,
                DocumentModeHint.AUTO,
            )
            intake_result.stored_original_image_path.unlink()

            with pytest.raises(DocumentExtractionWorkflowError, match="does not exist"):
                await _workflow_service(repository).run(intake_result.job_id)

            failed = await repository.require_job(intake_result.job_id)
            assert failed.status is JobStatus.FAILED
            assert failed.extraction_result_payload is None
    finally:
        await engine.dispose()


def _intake_service(
    repository: DocumentJobRepository,
    tmp_path: Path,
) -> DocumentIntakeService:
    return DocumentIntakeService(
        repository=repository,
        artifact_layout=JobArtifactLayout(
            uploads_root=tmp_path / "data" / "uploads",
            results_root=tmp_path / "data" / "results",
        ),
        diagnostics_config=ImageDiagnosticsConfig(
            hard_min_width_px=32,
            hard_min_height_px=32,
        ),
    )


def _workflow_service(
    repository: DocumentJobRepository,
    *,
    provider: FakeExtractionProvider | None = None,
) -> DocumentExtractionWorkflowService:
    return DocumentExtractionWorkflowService(
        repository=repository,
        extraction_settings=ExtractionSettings(model="openai/test-vision"),
        media_staging_service=LocalNoopMediaStagingService(),
        extraction_provider=provider or FakeExtractionProvider(),
    )


def _save_rgb_image(
    path: Path,
    *,
    size: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    image = Image.new("RGB", size, color=color)
    image.save(path)
