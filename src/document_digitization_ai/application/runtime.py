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
from document_digitization_ai.services import DocumentIntakeResult, DocumentIntakeService
from document_digitization_ai.storage import JobArtifactLayout


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
