from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from document_digitization_ai.api.http.errors import (
    ApiHTTPError,
    api_http_error_handler,
)
from document_digitization_ai.api.http.routes import documents, jobs
from document_digitization_ai.application import (
    DocumentProcessingFacade,
    LocalDocumentApplication,
)
from document_digitization_ai.core import AppSettings, get_settings


def create_app(
    settings: AppSettings | None = None,
    facade: DocumentProcessingFacade | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    owns_facade = facade is None
    document_facade = facade or DocumentProcessingFacade(
        LocalDocumentApplication(resolved_settings)
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if app.state.owns_document_facade:
            await app.state.document_facade.initialize_database()
        try:
            yield
        finally:
            if app.state.owns_document_facade:
                await app.state.document_facade.close()

    app = FastAPI(
        title="document-digitization-ai API",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.state.document_facade = document_facade
    app.state.owns_document_facade = owns_facade
    app.add_exception_handler(ApiHTTPError, api_http_error_handler)

    app.include_router(documents.router)
    app.include_router(jobs.router)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app

