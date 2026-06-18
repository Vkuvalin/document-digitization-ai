from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from document_digitization_ai.contracts import DocumentModeHint
from document_digitization_ai.core import AppSettings
from document_digitization_ai.db import (
    DocumentJobRepository,
    create_async_engine_from_url,
    create_async_session_factory,
    create_database_schema,
)
from document_digitization_ai.extraction import (
    FakeExtractionProvider,
    build_extraction_provider,
)
from document_digitization_ai.media import build_media_staging_service
from document_digitization_ai.services import (
    DocumentExtractionRunSummary,
    DocumentExtractionWorkflowError,
    DocumentExtractionWorkflowResult,
    DocumentExtractionWorkflowService,
    DocumentIntakeResult,
    DocumentIntakeService,
)
from document_digitization_ai.storage import (
    ExtractionAttemptArtifactLayout,
    JobArtifactLayout,
)


class LocalDocumentApplication:
    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings
        self._engine = create_async_engine_from_url(
            settings.database.url,
            echo=settings.database.echo,
        )
        self._session_factory = create_async_session_factory(self._engine)

    @property
    def settings(self) -> AppSettings:
        return self._settings

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def initialize_database(self) -> None:
        await create_database_schema(self._engine)

    async def intake_local_image(
        self,
        source_image_path: str | Path,
        user_mode_hint: DocumentModeHint,
    ) -> DocumentIntakeResult:
        async with self._session_factory() as session:
            service = self._build_intake_service(session)
            try:
                result = await service.intake_local_image(
                    source_image_path,
                    user_mode_hint,
                )
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            return result

    async def run_fake_extraction(
        self,
        job_id: str,
    ) -> DocumentExtractionWorkflowResult:
        async with self._session_factory() as session:
            service = self._build_extraction_workflow_service(session)
            try:
                result = await service.run(job_id)
                await session.commit()
            except DocumentExtractionWorkflowError:
                await session.commit()
                raise
            except Exception:
                await session.rollback()
                raise
            return result

    async def run_real_extraction_from_image(
        self,
        source_image_path: str | Path,
        user_mode_hint: DocumentModeHint = DocumentModeHint.AUTO,
    ) -> DocumentExtractionRunSummary:
        service = self._build_real_extraction_workflow_service()
        return await service.run_from_image(source_image_path, user_mode_hint)

    async def close(self) -> None:
        await self._engine.dispose()

    def _build_intake_service(self, session: AsyncSession) -> DocumentIntakeService:
        return DocumentIntakeService(
            repository=DocumentJobRepository(session),
            artifact_layout=JobArtifactLayout.from_storage_settings(
                self._settings.storage
            ),
            diagnostics_config=(
                self._settings.image_diagnostics.to_diagnostics_config()
            ),
        )

    def _build_extraction_workflow_service(
        self,
        session: AsyncSession,
    ) -> DocumentExtractionWorkflowService:
        return DocumentExtractionWorkflowService(
            repository=DocumentJobRepository(session),
            extraction_settings=self._settings.extraction,
            media_staging_service=build_media_staging_service(
                self._settings.media_staging
            ),
            extraction_provider=FakeExtractionProvider(),
        )

    def _build_real_extraction_workflow_service(
        self,
    ) -> DocumentExtractionWorkflowService:
        return DocumentExtractionWorkflowService(
            repository=None,
            extraction_settings=self._settings.extraction,
            media_staging_service=build_media_staging_service(
                self._settings.media_staging
            ),
            extraction_provider=build_extraction_provider(
                self._settings.extraction,
                openrouter_settings=self._settings.openrouter,
            ),
            session_factory=self._session_factory,
            job_artifact_layout=JobArtifactLayout.from_storage_settings(
                self._settings.storage
            ),
            attempt_artifact_layout=ExtractionAttemptArtifactLayout(
                self._settings.storage.results_dir
            ),
            diagnostics_config=(
                self._settings.image_diagnostics.to_diagnostics_config()
            ),
        )
