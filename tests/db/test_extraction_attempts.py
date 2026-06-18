from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import selectinload

from document_digitization_ai.contracts import DocumentModeHint
from document_digitization_ai.db import (
    DocumentJob,
    DocumentJobRepository,
    ExtractionAttemptLifecycleService,
    ExtractionAttemptRepository,
    ExtractionAttemptStatus,
    InvalidExtractionAttemptStatusTransitionError,
    build_safe_request_metadata,
    build_safe_response_metadata,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
    normalize_failure_metadata,
    sanitize_error_message,
)
from document_digitization_ai.storage.artifacts import (
    ArtifactLayoutError,
    ExtractionAttemptArtifactLayout,
    validate_relative_artifact_path,
)


@pytest.mark.asyncio
async def test_attempts_are_numbered_per_job_and_linked_to_document_job(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "numbering.db")
    try:
        await _create_job(session_factory, "job-a")
        await _create_job(session_factory, "job-b")
        service = ExtractionAttemptLifecycleService(session_factory)

        first = await _create_attempt(service, "job-a")
        second = await _create_attempt(service, "job-a")
        other_job_first = await _create_attempt(service, "job-b")

        assert first.attempt_number == 1
        assert second.attempt_number == 2
        assert other_job_first.attempt_number == 1
        assert first.status is ExtractionAttemptStatus.PENDING
        assert first.created_at is not None
        assert first.updated_at is not None
        assert first.started_at is None

        async with session_factory() as session:
            statement = (
                select(DocumentJob)
                .options(selectinload(DocumentJob.extraction_attempts))
                .where(DocumentJob.id == "job-a")
            )
            job = await session.scalar(statement)
            assert job is not None
            assert [attempt.attempt_number for attempt in job.extraction_attempts] == [
                1,
                2,
            ]
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_number_unique_constraint_is_enforced(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path, "unique.db")
    try:
        await _create_job(session_factory, "job-unique")

        async with session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            await repository.create_attempt(
                job_id="job-unique",
                attempt_number=1,
                provider_name="openrouter",
                model_name="openai/test-vision",
                schema_version="v1",
                schema_mode="compact",
                request_metadata_json={},
            )
            await session.commit()

        async with session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            with pytest.raises(IntegrityError):
                await repository.create_attempt(
                    job_id="job-unique",
                    attempt_number=1,
                    provider_name="openrouter",
                    model_name="openai/test-vision",
                    schema_version="v1",
                    schema_mode="compact",
                    request_metadata_json={},
                )
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_lifecycle_success_and_active_query(tmp_path: Path) -> None:
    engine, session_factory = await _session_factory(tmp_path, "lifecycle-success.db")
    try:
        await _create_job(session_factory, "job-success")
        service = ExtractionAttemptLifecycleService(session_factory)
        attempt = await _create_attempt(service, "job-success")

        running = await service.start_attempt(attempt.id)

        assert running.status is ExtractionAttemptStatus.RUNNING
        assert running.started_at is not None

        async with session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            active = await repository.get_active_attempt_for_job("job-success")
            assert active is not None
            assert active.id == attempt.id

        succeeded = await service.complete_attempt_success(
            attempt.id,
            validation_outcome="partial",
            validation_issue_count=0,
            response_metadata={
                "provider_response_id": "resp-123",
                "finish_reason": "stop",
                "model_name": "openai/test-vision",
                "usable_content": True,
                "raw_text_length": 883,
                "provider_seconds": 15.482,
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": None,
                    "total_tokens": 20,
                    "unexpected": 99,
                },
                "raw_text": "full provider content must not be stored",
            },
            raw_response_artifact_path=(
                "jobs/job-success/attempts/001/provider_raw_response.json"
            ),
            raw_response_size_bytes=100,
            sanitized_response_artifact_path=(
                "jobs/job-success/attempts/001/provider_sanitized_response.json"
            ),
            sanitized_response_size_bytes=80,
        )

        assert succeeded.status is ExtractionAttemptStatus.SUCCEEDED
        assert succeeded.finished_at is not None
        assert succeeded.duration_ms is not None
        assert succeeded.duration_ms >= 0
        assert succeeded.validation_outcome == "partial"
        assert succeeded.validation_issue_count == 0
        assert succeeded.raw_response_artifact_path == (
            "jobs/job-success/attempts/001/provider_raw_response.json"
        )
        assert succeeded.sanitized_response_artifact_path == (
            "jobs/job-success/attempts/001/provider_sanitized_response.json"
        )
        assert succeeded.response_metadata_json == {
            "finish_reason": "stop",
            "model_name": "openai/test-vision",
            "provider_response_id": "resp-123",
            "provider_seconds": 15.482,
            "raw_text_length": 883,
            "usable_content": True,
            "usage": {
                "completion_tokens": None,
                "prompt_tokens": 10,
                "total_tokens": 20,
            },
        }

        async with session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            assert await repository.get_active_attempt_for_job("job-success") is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_attempt_lifecycle_failure_paths_and_invalid_transitions(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "lifecycle-failure.db")
    try:
        await _create_job(session_factory, "job-failure")
        service = ExtractionAttemptLifecycleService(session_factory)

        pending_attempt = await _create_attempt(service, "job-failure")
        failed_from_pending = await service.complete_attempt_failure(
            pending_attempt.id,
            expected_status=ExtractionAttemptStatus.PENDING,
            error="provider failed before response",
            retryable=True,
        )
        assert failed_from_pending.status is ExtractionAttemptStatus.FAILED
        assert failed_from_pending.finished_at is not None
        assert failed_from_pending.duration_ms == 0
        assert failed_from_pending.retryable is True
        assert failed_from_pending.raw_response_artifact_path is None
        assert failed_from_pending.sanitized_response_artifact_path is None

        with pytest.raises(InvalidExtractionAttemptStatusTransitionError):
            await service.complete_attempt_success(
                pending_attempt.id,
                validation_outcome="succeeded",
                validation_issue_count=0,
            )

        running_attempt = await _create_attempt(service, "job-failure")
        await service.start_attempt(running_attempt.id)
        with pytest.raises(InvalidExtractionAttemptStatusTransitionError):
            await service.start_attempt(running_attempt.id)

        succeeded = await service.complete_attempt_success(
            running_attempt.id,
            validation_outcome="succeeded",
            validation_issue_count=0,
        )
        assert succeeded.status is ExtractionAttemptStatus.SUCCEEDED
        with pytest.raises(InvalidExtractionAttemptStatusTransitionError):
            await service.complete_attempt_failure(
                running_attempt.id,
                error="cannot fail terminal attempt",
            )

        stale_attempt = await _create_attempt(service, "job-failure")
        with pytest.raises(InvalidExtractionAttemptStatusTransitionError):
            await service.complete_attempt_failure(
                stale_attempt.id,
                error="stale expected state",
            )
    finally:
        await engine.dispose()


def test_metadata_allowlists_drop_sensitive_and_unknown_values() -> None:
    request_metadata = build_safe_request_metadata(
        provider_name="openrouter",
        model_name="openai/test-vision",
        schema_version="v1",
        schema_mode="compact",
        metadata={
            "Authorization": "Bearer secret",
            "api_key": "secret",
            "delete_url": "https://delete.example",
            "local_path": r"C:\Users\User\image.jpg",
            "prompt_text": "full prompt",
            "base64_image": "AAAA",
            "media_url": "https://i.ibb.co/full-url-not-allowed",
            "media_url_host": "i.ibb.co",
            "media_url_present": True,
            "media_count": 1,
            "structured_outputs_enabled": True,
            "provider_require_parameters": True,
            "unknown": "drop",
        },
    )

    assert request_metadata == {
        "media_count": 1,
        "media_url_host": "i.ibb.co",
        "media_url_present": True,
        "model_name": "openai/test-vision",
        "provider_name": "openrouter",
        "provider_require_parameters": True,
        "schema_mode": "compact",
        "schema_version": "v1",
        "structured_outputs_enabled": True,
    }

    response_metadata = build_safe_response_metadata(
        {
            "provider_response_id": "resp-123",
            "finish_reason": "stop",
            "raw_text": "full extracted text",
            "content": "full provider content",
            "raw_payload": {"document": {"sensitive": "payload"}},
            "headers": {"authorization": "Bearer secret"},
            "field_count": 10,
            "usage": {
                "prompt_tokens": 1,
                "completion_tokens": 2,
                "total_tokens": 3,
                "api_key": "secret",
            },
        }
    )

    assert response_metadata == {
        "field_count": 10,
        "finish_reason": "stop",
        "provider_response_id": "resp-123",
        "usage": {
            "completion_tokens": 2,
            "prompt_tokens": 1,
            "total_tokens": 3,
        },
    }


def test_error_metadata_is_redacted_truncated_and_retryable_aware() -> None:
    message = (
        "Authorization: Bearer sk-secret api_key=hidden "
        r"C:\Users\User\document.jpg "
        "/home/user/document.jpg "
        + ("x" * 1100)
    )

    safe_message = sanitize_error_message(message)
    failure = normalize_failure_metadata(
        RuntimeError(message),
        error_type="ProviderTimeoutError",
    )

    assert len(safe_message) <= 1000
    assert "sk-secret" not in safe_message
    assert "hidden" not in safe_message
    assert r"C:\Users\User" not in safe_message
    assert "/home/user" not in safe_message
    assert failure.error_type == "ProviderTimeoutError"
    assert failure.retryable is True
    assert len(failure.error_message) <= 1000


@pytest.mark.asyncio
async def test_artifact_paths_are_validated_and_nullable_on_provider_failure(
    tmp_path: Path,
) -> None:
    assert validate_relative_artifact_path(
        r"jobs\job-artifacts\attempts\001\provider_raw_response.json"
    ) == "jobs/job-artifacts/attempts/001/provider_raw_response.json"

    for invalid_path in (
        r"C:\Users\User\provider_raw_response.json",
        "/tmp/provider_raw_response.json",
        "jobs/job-artifacts/../provider_raw_response.json",
    ):
        with pytest.raises(ArtifactLayoutError):
            validate_relative_artifact_path(invalid_path)

    engine, session_factory = await _session_factory(tmp_path, "artifact-paths.db")
    try:
        await _create_job(session_factory, "job-artifacts")
        service = ExtractionAttemptLifecycleService(session_factory)
        attempt = await _create_attempt(service, "job-artifacts")
        await service.start_attempt(attempt.id)

        with pytest.raises(ValueError, match="raw_response_artifact_path"):
            await service.record_provider_response_artifacts(
                attempt.id,
                raw_response_artifact_path="/tmp/provider_raw_response.json",
            )

        failed = await service.complete_attempt_failure(
            attempt.id,
            error="provider failed before response",
        )

        assert failed.raw_response_artifact_path is None
        assert failed.sanitized_response_artifact_path is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_provider_response_artifacts_requires_running_and_preserves_refs(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "artifact-guard.db")
    try:
        await _create_job(session_factory, "job-artifact-guard")
        service = ExtractionAttemptLifecycleService(session_factory)

        pending_attempt = await _create_attempt(service, "job-artifact-guard")
        with pytest.raises(
            InvalidExtractionAttemptStatusTransitionError,
            match="expected RUNNING",
        ):
            await service.record_provider_response_artifacts(
                pending_attempt.id,
                raw_response_artifact_path=(
                    "jobs/job-artifact-guard/attempts/001/provider_raw_response.json"
                ),
            )

        async with session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            persisted = await repository.require_attempt(pending_attempt.id)
            assert persisted.raw_response_artifact_path is None
            assert persisted.sanitized_response_artifact_path is None

        running_attempt = await _create_attempt(service, "job-artifact-guard")
        await service.start_attempt(running_attempt.id)
        recorded = await service.record_provider_response_artifacts(
            running_attempt.id,
            raw_response_artifact_path=(
                "jobs/job-artifact-guard/attempts/002/provider_raw_response.json"
            ),
            raw_response_size_bytes=10,
            sanitized_response_artifact_path=(
                "jobs/job-artifact-guard/attempts/002/provider_sanitized_response.json"
            ),
            sanitized_response_size_bytes=8,
        )

        assert recorded.raw_response_artifact_path == (
            "jobs/job-artifact-guard/attempts/002/provider_raw_response.json"
        )
        assert recorded.sanitized_response_artifact_path == (
            "jobs/job-artifact-guard/attempts/002/provider_sanitized_response.json"
        )

        await service.complete_attempt_success(
            running_attempt.id,
            validation_outcome="succeeded",
            validation_issue_count=0,
            raw_response_artifact_path=recorded.raw_response_artifact_path,
            raw_response_size_bytes=recorded.raw_response_size_bytes,
            sanitized_response_artifact_path=recorded.sanitized_response_artifact_path,
            sanitized_response_size_bytes=recorded.sanitized_response_size_bytes,
        )
        with pytest.raises(
            InvalidExtractionAttemptStatusTransitionError,
            match="expected RUNNING",
        ):
            await service.record_provider_response_artifacts(
                running_attempt.id,
                raw_response_artifact_path=(
                    "jobs/job-artifact-guard/attempts/002/overwritten.json"
                ),
                raw_response_size_bytes=999,
            )

        async with session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            persisted = await repository.require_attempt(running_attempt.id)
            assert persisted.raw_response_artifact_path == recorded.raw_response_artifact_path
            assert persisted.raw_response_size_bytes == recorded.raw_response_size_bytes
            assert (
                persisted.sanitized_response_artifact_path
                == recorded.sanitized_response_artifact_path
            )
            assert (
                persisted.sanitized_response_size_bytes
                == recorded.sanitized_response_size_bytes
            )

        failed_attempt = await _create_attempt(service, "job-artifact-guard")
        await service.start_attempt(failed_attempt.id)
        failed = await service.complete_attempt_failure(
            failed_attempt.id,
            error="provider failed after raw response",
            raw_response_artifact_path=(
                "jobs/job-artifact-guard/attempts/003/provider_raw_response.json"
            ),
            raw_response_size_bytes=12,
        )
        with pytest.raises(
            InvalidExtractionAttemptStatusTransitionError,
            match="expected RUNNING",
        ):
            await service.record_provider_response_artifacts(
                failed_attempt.id,
                raw_response_artifact_path=(
                    "jobs/job-artifact-guard/attempts/003/overwritten.json"
                ),
                raw_response_size_bytes=999,
            )

        async with session_factory() as session:
            repository = ExtractionAttemptRepository(session)
            persisted = await repository.require_attempt(failed_attempt.id)
            assert persisted.raw_response_artifact_path == failed.raw_response_artifact_path
            assert persisted.raw_response_size_bytes == failed.raw_response_size_bytes
            assert persisted.sanitized_response_artifact_path is None
            assert persisted.sanitized_response_size_bytes is None
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_media_staging_metadata_requires_running_and_filters_values(
    tmp_path: Path,
) -> None:
    engine, session_factory = await _session_factory(tmp_path, "media-metadata.db")
    try:
        await _create_job(session_factory, "job-media-metadata")
        service = ExtractionAttemptLifecycleService(session_factory)

        pending_attempt = await _create_attempt(service, "job-media-metadata")
        with pytest.raises(
            InvalidExtractionAttemptStatusTransitionError,
            match="expected RUNNING",
        ):
            await service.record_media_staging_metadata(
                pending_attempt.id,
                metadata={"staged_media_kind": "public_url"},
            )

        running_attempt = await _create_attempt(service, "job-media-metadata")
        await service.start_attempt(running_attempt.id)
        recorded = await service.record_media_staging_metadata(
            running_attempt.id,
            metadata={
                "media_backend": "imgbb",
                "staged_media_kind": "public_url",
                "media_url_present": True,
                "media_url_host": "i.ibb.co",
                "external_upload_performed": True,
                "media_count": 1,
                "media_url": "https://i.ibb.co/full-url-not-allowed",
                "delete_url": "https://ibb.co/delete/private",
                "local_path": r"C:\Users\User\document.jpg",
            },
        )

        assert recorded.request_metadata_json == {
            "external_upload_performed": True,
            "media_backend": "imgbb",
            "media_count": 1,
            "media_url_host": "i.ibb.co",
            "media_url_present": True,
            "model_name": "openai/test-vision",
            "provider_name": "openrouter",
            "schema_mode": "compact",
            "schema_version": "v1",
            "staged_media_kind": "public_url",
        }
    finally:
        await engine.dispose()


def test_attempt_artifact_writer_uses_relative_paths_and_deterministic_json(
    tmp_path: Path,
) -> None:
    layout = ExtractionAttemptArtifactLayout(tmp_path)

    raw = layout.write_json_artifact(
        job_id="job-writer",
        attempt_number=1,
        filename="provider_raw_response.json",
        payload={"b": 2, "a": 1},
    )
    sanitized = layout.write_json_artifact(
        job_id="job-writer",
        attempt_number=1,
        filename="provider_sanitized_response.json",
        payload={"raw_text": {"text": "hello"}},
    )

    raw_path = tmp_path / Path(*raw.relative_path.split("/"))
    sanitized_path = tmp_path / Path(*sanitized.relative_path.split("/"))

    assert raw.relative_path == "jobs/job-writer/attempts/001/provider_raw_response.json"
    assert sanitized.relative_path == (
        "jobs/job-writer/attempts/001/provider_sanitized_response.json"
    )
    assert raw_path.read_text(encoding="utf-8") == '{"a":1,"b":2}\n'
    assert sanitized_path.exists()
    assert raw.size_bytes == raw_path.stat().st_size
    assert sanitized.size_bytes == sanitized_path.stat().st_size


async def _session_factory(
    tmp_path: Path,
    database_name: str,
) -> tuple[AsyncEngine, Callable[[], AsyncSession]]:
    engine = create_async_engine_from_url(f"sqlite+aiosqlite:///{tmp_path / database_name}")
    await create_database_schema(engine)
    return engine, create_async_session_factory(engine)


async def _create_job(
    session_factory: Callable[[], AsyncSession],
    job_id: str,
) -> None:
    async with session_factory() as session:
        repository = DocumentJobRepository(session)
        await repository.create_job(DocumentModeHint.AUTO, job_id=job_id)
        await session.commit()


async def _create_attempt(
    service: ExtractionAttemptLifecycleService,
    job_id: str,
):
    return await service.create_attempt_for_job(
        job_id=job_id,
        provider_name="openrouter",
        model_name="openai/test-vision",
        schema_version="v1",
        schema_mode="compact",
    )
