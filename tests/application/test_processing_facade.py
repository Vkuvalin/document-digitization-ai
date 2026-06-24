from __future__ import annotations

from datetime import UTC, datetime
from io import BytesIO
import inspect
import json
from pathlib import Path
from typing import Any, cast

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from document_digitization_ai.application import (
    DocumentProcessingFacade,
    LocalDocumentApplication,
)
from document_digitization_ai.application import dtos as facade_dtos
from document_digitization_ai.application import facade as facade_module
from document_digitization_ai.contracts import (
    BlockType,
    DetectedDocumentType,
    DocumentInfo,
    DocumentModeHint,
    ExtractedTable,
    ExtractionResult,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageShape,
    JobStatus,
    RawText,
    TableRow,
    TextBlock,
    Warning,
    WarningCode,
)
from document_digitization_ai.core import AppSettings
from document_digitization_ai.db import (
    DocumentJob,
    DocumentJobRepository,
    create_async_session_factory,
)
from document_digitization_ai.services import (
    DocumentExtractionRunSummary,
    MarkdownExportResult,
)
from document_digitization_ai.storage import (
    MarkdownExportArtifactLayout,
    StoredMarkdownExportArtifact,
)


@pytest.mark.asyncio
async def test_facade_submit_from_path_and_queries_return_safe_views(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    application = ObservingApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()

        submit = await facade.submit_document_from_path(
            source_image_path,
            user_mode_hint=DocumentModeHint.PLAIN_TEXT,
        )
        assert submit.accepted is True
        assert submit.job_id is not None
        assert submit.status == JobStatus.RESULT_READY.value
        assert submit.result_available is True
        assert _json_safe_dumps(submit.to_dict())
        assert not _contains_absolute_path(submit.to_dict(), tmp_path)

        history = await facade.list_jobs()
        status = await facade.get_job_status(submit.job_id)
        detail = await facade.get_job_detail(submit.job_id)
        result = await facade.get_extraction_result(submit.job_id)
        artifacts = await facade.get_job_artifacts(submit.job_id)

        assert application.workflow_calls == 1
        assert application.export_calls == 0
        assert history.total == 1
        assert history.jobs[0].job_id == submit.job_id
        assert status.status == JobStatus.RESULT_READY.value
        assert status.result_available is True
        assert detail.summary is not None
        assert detail.status is not None
        assert len(detail.attempts) == 1
        assert result.result_available is True
        assert result.result is not None
        raw_text = result.result["raw_text"]
        assert isinstance(raw_text, dict)
        assert raw_text["text"] == "Deterministic fake extracted text."
        assert artifacts.error is None
        assert {artifact.kind for artifact in artifacts.artifacts} == {
            "input_original",
            "provider_sanitized_response",
            "markdown_export",
        }
        assert all(not Path(item.relative_path).is_absolute() for item in artifacts.artifacts)
        assert not _contains_absolute_path(detail.to_dict(), tmp_path)
        assert not _contains_absolute_path(result.to_dict(), tmp_path)
        assert "provider_raw_response" not in json.dumps(artifacts.to_dict())
        assert "delete_url" not in json.dumps(artifacts.to_dict())
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_markdown_export_writes_only_when_explicit(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    application = ObservingApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        submit = await facade.submit_document_from_path(source_image_path)
        assert submit.job_id is not None
        result_md_path = (
            tmp_path
            / "data"
            / "results"
            / "jobs"
            / submit.job_id
            / "exports"
            / "result.md"
        )

        markdown = await facade.get_result_markdown(submit.job_id)
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            persisted_job = await session.get(DocumentJob, submit.job_id)
            assert persisted_job is not None
            status_after_read = persisted_job.status

        assert application.workflow_calls == 1
        assert application.export_calls == 1
        assert markdown.result_available is True
        assert markdown.markdown is not None
        assert markdown.artifact is None
        assert not result_md_path.exists()
        assert status_after_read is JobStatus.RESULT_READY

        markdown_with_artifact = await facade.get_result_markdown(
            submit.job_id,
            write_artifact=True,
        )
        assert application.export_calls == 2
        assert markdown_with_artifact.result_available is True
        assert markdown_with_artifact.artifact is not None
        assert markdown_with_artifact.artifact.relative_path == (
            f"jobs/{submit.job_id}/exports/result.md"
        )
        assert markdown_with_artifact.artifact.exists is True
        assert result_md_path.is_file()
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_submit_document_file_stages_bytes_safely(
    tmp_path: Path,
) -> None:
    image_bytes = _rgb_image_bytes()
    application = ObservingApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()

        submit = await facade.submit_document_file(
            filename="upload.jpg",
            content_type="image/jpeg",
            data=image_bytes,
            user_mode_hint=DocumentModeHint.FORM,
        )
        empty = await facade.submit_document_file(
            filename="empty.jpg",
            content_type="image/jpeg",
            data=b"",
        )
        unsafe = await facade.submit_document_file(
            filename="../unsafe.jpg",
            content_type="image/jpeg",
            data=image_bytes,
        )
        history = await facade.list_jobs()

        assert submit.accepted is True
        assert submit.job_id is not None
        assert submit.status == JobStatus.RESULT_READY.value
        assert empty.error is not None
        assert empty.error.error_type == "invalid_input"
        assert unsafe.error is not None
        assert unsafe.error.error_type == "invalid_input"
        assert history.total == 1
        assert application.workflow_calls == 1
        assert not _contains_absolute_path(submit.to_dict(), tmp_path)
        assert not any(
            (tmp_path / "data" / "uploads" / "_facade_file_submissions").glob("*")
        )
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_history_is_limited_and_newest_first(tmp_path: Path) -> None:
    application = LocalDocumentApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            await _persist_created_job(
                session,
                job_id="job-old",
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
            await _persist_created_job(
                session,
                job_id="job-new",
                created_at=datetime(2026, 1, 2, tzinfo=UTC),
            )
            await session.commit()

        history = await facade.list_jobs(limit=1)
        invalid_limit = await facade.list_jobs(limit=0)
        filtered = await facade.list_jobs(status=JobStatus.CREATED)

        assert history.total == 2
        assert history.limit == 1
        assert [job.job_id for job in history.jobs] == ["job-new"]
        assert invalid_limit.error is not None
        assert invalid_limit.error.error_type == "invalid_input"
        assert filtered.total == 2
        assert filtered.status_filter == JobStatus.CREATED.value
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_errors_and_malformed_payloads_are_safe(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jpg"
    application = LocalDocumentApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            malformed = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-malformed",
            )
            malformed.status = JobStatus.RESULT_READY
            malformed.extraction_result_payload = {"document": {}}
            await session.commit()

        invalid_submit = await facade.submit_document_from_path(missing_path)
        unknown_status = await facade.get_job_status("missing-job")
        unknown_detail = await facade.get_job_detail("missing-job")
        unknown_result = await facade.get_extraction_result("missing-job")
        unknown_markdown = await facade.get_result_markdown("missing-job")
        malformed_result = await facade.get_extraction_result("job-malformed")

        assert invalid_submit.error is not None
        assert invalid_submit.error.error_type == "invalid_input"
        assert not _contains_absolute_path(invalid_submit.to_dict(), tmp_path)
        assert unknown_status.error is not None
        assert unknown_status.error.error_type == "job_not_found"
        assert unknown_detail.error is not None
        assert unknown_detail.error.error_type == "job_not_found"
        assert unknown_result.error is not None
        assert unknown_result.error.error_type == "job_not_found"
        assert unknown_markdown.error is not None
        assert unknown_markdown.error.error_type == "job_not_found"
        assert malformed_result.error is not None
        assert malformed_result.error.error_type == "malformed_result_payload"
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_result_view_adds_review_facts_without_persisting_them(
    tmp_path: Path,
) -> None:
    application = LocalDocumentApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        session_factory = create_async_session_factory(application.engine)
        result = ExtractionResult(
            document=DocumentInfo(
                user_mode_hint=DocumentModeHint.FORM,
                detected_type=DetectedDocumentType.FORM,
            ),
            image_diagnostics=ImageDiagnostics(
                file=ImageFileMetadata(
                    mime_type="image/jpeg",
                    file_size_bytes=123,
                    file_extension=".jpg",
                ),
                image=ImageShape.from_dimensions(width=120, height=120),
            ),
            raw_text=RawText(
                text=(
                    "Prenatal labs\n"
                    "\n"
                    "Test Result\n"
                    "Blood type and Rh A+ / absc"
                )
            ),
            tables=(
                ExtractedTable(
                    title="Prenatal labs",
                    columns=("Test", "Result"),
                    rows=(TableRow(cells=("Blood type and Rh", "A+ / absc")),),
                ),
            ),
        )
        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            job = await repository.create_job(DocumentModeHint.FORM, job_id="job-review")
            job.status = JobStatus.RESULT_READY
            job.extraction_result_payload = result.to_dict()
            await session.commit()

        view = await facade.get_extraction_result("job-review")

        assert view.result_available is True
        assert view.result is not None
        review = view.result["review"]
        assert isinstance(review, dict)
        assert review["derived_table_facts"] == [
            {
                "label": "Blood type and Rh",
                "value": "A+ / absc",
                "source": "table",
                "source_table": "Prenatal labs",
                "source_row_index": 1,
                "note": None,
                "confidence": None,
            }
        ]
        assert view.result["tables"] == result.to_dict()["tables"]
        presentation = view.result["presentation"]
        assert isinstance(presentation, dict)
        assert "Prenatal labs" in presentation["text_markdown"]
        assert "### Поля" not in presentation["text_markdown"]
        assert "Blood type and Rh" in presentation["text_markdown"]
        assert "| Test              | Result" in presentation["text_markdown"]
        assert "Test Result\nBlood type and Rh A+ / absc" not in (
            presentation["text_markdown"]
        )

        async with session_factory() as session:
            persisted = await DocumentJobRepository(session).require_job("job-review")
            assert persisted.extraction_result_payload is not None
            assert "review" not in persisted.extraction_result_payload
            assert "presentation" not in persisted.extraction_result_payload
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_artifact_refs_are_relative_and_handle_missing_files(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    application = LocalDocumentApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        submit = await facade.submit_document_from_path(source_image_path)
        assert submit.job_id is not None

        unsafe = await facade.get_job_artifacts("../job")
        assert unsafe.error is not None
        assert unsafe.error.error_type == "invalid_input"

        original_upload = (
            tmp_path / "data" / "uploads" / submit.job_id / "original.jpg"
        )
        original_upload.unlink()

        artifacts = await facade.get_job_artifacts(submit.job_id)
        by_kind = {artifact.kind: artifact for artifact in artifacts.artifacts}

        assert artifacts.error is None
        assert by_kind["input_original"].exists is False
        assert by_kind["input_original"].relative_path == (
            f"uploads/{submit.job_id}/original.jpg"
        )
        assert all(not Path(item.relative_path).is_absolute() for item in artifacts.artifacts)
        assert not _contains_absolute_path(artifacts.to_dict(), tmp_path)
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_preview_file_serves_only_safe_original_upload(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    application = LocalDocumentApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        submit = await facade.submit_document_from_path(source_image_path)
        assert submit.job_id is not None

        preview = await facade.get_job_preview_file(submit.job_id)
        missing_job = await facade.get_job_preview_file("missing-job")

        assert preview.error is None
        assert preview.path is not None
        assert preview.path.name == "original.jpg"
        assert preview.path.is_file()
        assert preview.filename == "original.jpg"
        assert preview.content_type == "image/jpeg"
        assert preview.supports_inline_preview is True
        assert missing_job.error is not None
        assert missing_job.error.error_type == "job_not_found"

        original_upload = (
            tmp_path / "data" / "uploads" / submit.job_id / "original.jpg"
        )
        original_upload.unlink()
        missing_file = await facade.get_job_preview_file(submit.job_id)

        assert missing_file.error is not None
        assert missing_file.error.error_type == "artifact_not_found"
        assert not _contains_absolute_path(missing_file.error.to_dict(), tmp_path)

        outside_path = tmp_path / "outside.jpg"
        _save_rgb_image(outside_path)
        raw_artifact_path = (
            tmp_path
            / "data"
            / "results"
            / "jobs"
            / "job-raw"
            / "attempts"
            / "001"
            / "provider_sanitized_response.json"
        )
        raw_artifact_path.parent.mkdir(parents=True)
        raw_artifact_path.write_text("{}", encoding="utf-8")
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            outside_job = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-outside",
            )
            await repository.attach_uploaded_image_metadata(
                outside_job.id,
                source_image_path=str(outside_path),
                mime_type="image/jpeg",
                size_bytes=outside_path.stat().st_size,
            )
            raw_job = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-raw",
            )
            await repository.attach_uploaded_image_metadata(
                raw_job.id,
                source_image_path=str(raw_artifact_path),
                mime_type="application/json",
                size_bytes=raw_artifact_path.stat().st_size,
            )
            await session.commit()

        outside_preview = await facade.get_job_preview_file("job-outside")
        raw_preview = await facade.get_job_preview_file("job-raw")

        assert outside_preview.error is not None
        assert outside_preview.error.error_type == "artifact_access_denied"
        assert raw_preview.error is not None
        assert raw_preview.error.error_type == "artifact_access_denied"
        assert not _contains_absolute_path(raw_preview.error.to_dict(), tmp_path)
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_delete_job_removes_row_and_safe_artifact_dirs(
    tmp_path: Path,
) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    application = LocalDocumentApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        submit = await facade.submit_document_from_path(source_image_path)
        assert submit.job_id is not None
        job_id = submit.job_id
        upload_dir = tmp_path / "data" / "uploads" / job_id
        result_dir = tmp_path / "data" / "results" / job_id
        attempt_dir = tmp_path / "data" / "results" / "jobs" / job_id
        outside_file = tmp_path / "outside-keep.txt"
        result_dir.mkdir(parents=True, exist_ok=True)
        attempt_dir.mkdir(parents=True, exist_ok=True)
        (result_dir / "result.json").write_text("{}", encoding="utf-8")
        (attempt_dir / "provider_sanitized_response.json").write_text(
            "{}",
            encoding="utf-8",
        )
        outside_file.write_text("keep", encoding="utf-8")

        deleted = await facade.delete_job(job_id)
        repeated = await facade.delete_job(job_id)
        invalid = await facade.delete_job("../job")
        history = await facade.list_jobs()
        detail = await facade.get_job_detail(job_id)

        assert deleted.error is None
        assert deleted.deleted is True
        assert deleted.artifacts_deleted >= 2
        assert repeated.error is None
        assert repeated.deleted is False
        assert invalid.error is not None
        assert invalid.error.error_type == "invalid_input"
        assert history.total == 0
        assert detail.error is not None
        assert detail.error.error_type == "job_not_found"
        assert not upload_dir.exists()
        assert not result_dir.exists()
        assert not attempt_dir.exists()
        assert outside_file.read_text(encoding="utf-8") == "keep"
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_retention_cleanup_deletes_only_expired_safe_jobs(
    tmp_path: Path,
) -> None:
    application = LocalDocumentApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    now = datetime(2026, 6, 23, tzinfo=UTC)
    old_created_at = datetime(2026, 6, 10, tzinfo=UTC)
    recent_created_at = datetime(2026, 6, 20, tzinfo=UTC)
    outside_file = tmp_path / "outside-retention.txt"
    outside_file.write_text("keep", encoding="utf-8")
    try:
        await facade.initialize_database()
        session_factory = create_async_session_factory(application.engine)
        async with session_factory() as session:
            repository = DocumentJobRepository(session)
            old_job = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-old",
            )
            old_job.created_at = old_created_at
            old_job.updated_at = old_created_at
            recent_job = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-recent",
            )
            recent_job.created_at = recent_created_at
            recent_job.updated_at = recent_created_at
            outside_job = await repository.create_job(
                DocumentModeHint.AUTO,
                job_id="job-outside",
            )
            outside_job.created_at = old_created_at
            outside_job.updated_at = old_created_at
            outside_job.source_image_path = str(outside_file)
            await session.commit()

        for job_id in ("job-old", "job-recent"):
            (tmp_path / "data" / "uploads" / job_id).mkdir(parents=True)
            (tmp_path / "data" / "results" / "jobs" / job_id).mkdir(parents=True)

        cleanup = await facade.cleanup_expired_jobs(now=now)
        history = await facade.list_jobs()
        remaining_ids = {job.job_id for job in history.jobs}

        assert cleanup.error is None
        assert cleanup.retention_days == 7
        assert cleanup.jobs_deleted == 2
        assert cleanup.cutoff_at == datetime(2026, 6, 16, tzinfo=UTC)
        assert remaining_ids == {"job-recent"}
        assert not (tmp_path / "data" / "uploads" / "job-old").exists()
        assert not (tmp_path / "data" / "results" / "jobs" / "job-old").exists()
        assert (tmp_path / "data" / "uploads" / "job-recent").is_dir()
        assert (tmp_path / "data" / "results" / "jobs" / "job-recent").is_dir()
        assert outside_file.read_text(encoding="utf-8") == "keep"
    finally:
        await facade.close()


@pytest.mark.asyncio
async def test_facade_markdown_write_failure_is_safe(tmp_path: Path) -> None:
    source_image_path = tmp_path / "source.jpg"
    _save_rgb_image(source_image_path)
    application = FailingArtifactExportApplication(_app_settings(tmp_path))
    facade = DocumentProcessingFacade(application)
    try:
        await facade.initialize_database()
        submit = await facade.submit_document_from_path(source_image_path)
        assert submit.job_id is not None

        markdown = await facade.get_result_markdown(
            submit.job_id,
            write_artifact=True,
        )

        assert markdown.result_available is False
        assert markdown.error is not None
        assert markdown.error.error_type == "artifact_write_failed"
        assert not _contains_absolute_path(markdown.to_dict(), tmp_path)
        assert r"C:\Users" not in json.dumps(markdown.to_dict())
    finally:
        await facade.close()


def test_facade_dtos_are_serializable_and_http_independent() -> None:
    source = inspect.getsource(facade_module) + inspect.getsource(facade_dtos)
    lowered_source = source.lower()

    assert "fastapi" not in lowered_source
    assert "uploadfile" not in lowered_source
    assert "from starlette" not in lowered_source
    assert "import starlette" not in lowered_source

    error = facade_dtos.BackendErrorView(
        error_type="invalid_input",
        error_message="Input is invalid.",
    )
    dto = facade_dtos.JobStatusView(
        job_id="job-001",
        status=None,
        result_available=False,
        error=error,
    )
    serialized = dto.to_dict()

    assert json.loads(json.dumps(serialized))["error"]["error_type"] == "invalid_input"
    assert "DocumentJob" not in json.dumps(serialized)


def test_facade_summary_warning_count_uses_nested_result_warnings() -> None:
    result = ExtractionResult(
        document=DocumentInfo(
            user_mode_hint=DocumentModeHint.FORM,
            detected_type=DetectedDocumentType.FORM,
        ),
        image_diagnostics=ImageDiagnostics(
            file=ImageFileMetadata(
                mime_type="image/jpeg",
                file_size_bytes=123,
                file_extension=".jpg",
            ),
            image=ImageShape.from_dimensions(width=120, height=120),
            warnings=(
                Warning(
                    code=WarningCode.LOW_CONTRAST,
                    message="Контраст ниже ожидаемого.",
                ),
            ),
        ),
        raw_text=RawText(
            text="Text",
            warnings=(
                Warning(
                    code=WarningCode.UNREADABLE_TEXT,
                    message="Фрагмент текста не читается.",
                ),
            ),
        ),
        tables=(
            ExtractedTable(
                title="Line items",
                columns=("Item",),
                rows=(
                    TableRow(
                        cells=("Unreadable row",),
                        warnings=(
                            Warning(
                                code=WarningCode.AMBIGUOUS_TABLE,
                                message="Строка таблицы неоднозначна.",
                            ),
                        ),
                    ),
                ),
            ),
        ),
        blocks=(
            TextBlock(
                type=BlockType.PARAGRAPH,
                text="Block text",
                order=1,
                warnings=(
                    Warning(
                        code=WarningCode.PARTIAL_EXTRACTION,
                        message="Текстовый блок извлечён частично.",
                    ),
                ),
            ),
        ),
        warnings=(
            Warning(
                code=WarningCode.PARTIAL_EXTRACTION,
                message="Часть данных не извлечена.",
            ),
        ),
    )
    job = facade_module._JobSnapshot(
        id="job-with-warnings",
        status=JobStatus.RESULT_READY,
        user_mode_hint=DocumentModeHint.FORM,
        source_image_path=None,
        source_image_mime_type=None,
        source_image_size_bytes=None,
        extraction_result_payload=result.to_dict(),
        validation_status=None,
        completed_attempt_id=None,
        error_message=None,
        created_at=None,
        updated_at=None,
    )

    summary = facade_module._summary_from_snapshots(job, latest_attempt=None)

    assert summary.warning_count == 5


class ObservingApplication(LocalDocumentApplication):
    def __init__(self, settings: AppSettings) -> None:
        super().__init__(settings)
        self.workflow_calls = 0
        self.export_calls = 0

    async def run_real_extraction_from_image(
        self,
        source_image_path: str | Path,
        user_mode_hint: DocumentModeHint = DocumentModeHint.AUTO,
    ) -> DocumentExtractionRunSummary:
        self.workflow_calls += 1
        return await super().run_real_extraction_from_image(
            source_image_path,
            user_mode_hint,
        )

    async def export_result_markdown(
        self,
        job_id: str,
        *,
        write_artifact: bool = True,
    ) -> MarkdownExportResult:
        self.export_calls += 1
        return await super().export_result_markdown(
            job_id,
            write_artifact=write_artifact,
        )


class FailingArtifactExportApplication(LocalDocumentApplication):
    def _build_markdown_export_artifact_layout(self) -> MarkdownExportArtifactLayout:
        return FailingMarkdownExportArtifactLayout(self.settings.storage.results_dir)


class FailingMarkdownExportArtifactLayout(MarkdownExportArtifactLayout):
    def write_markdown_artifact(
        self,
        *,
        job_id: str,
        markdown: str,
    ) -> StoredMarkdownExportArtifact:
        raise OSError(r"C:\Users\User\secret\result.md")


async def _persist_created_job(
    session: AsyncSession,
    *,
    job_id: str,
    created_at: datetime,
) -> None:
    repository = DocumentJobRepository(session)
    job = await repository.create_job(DocumentModeHint.AUTO, job_id=job_id)
    job.created_at = created_at
    job.updated_at = created_at


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


def _save_rgb_image(
    path: Path,
    *,
    size: tuple[int, int] = (120, 120),
    color: tuple[int, int, int] = (128, 128, 128),
) -> None:
    image = Image.new("RGB", size, color=color)
    image.save(path)


def _rgb_image_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (120, 120), color=(128, 128, 128)).save(output, format="JPEG")
    return output.getvalue()


def _contains_absolute_path(payload: object, tmp_path: Path) -> bool:
    serialized = json.dumps(payload, default=str)
    return str(tmp_path) in serialized or r"C:\Users" in serialized


def _json_safe_dumps(payload: object) -> str:
    return json.dumps(payload, sort_keys=True)
