from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

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


_WEB_STATIC_DIR = Path(__file__).resolve().parents[2] / "web" / "static"


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

    _mount_web_ui(app)

    @app.get("/health", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _mount_web_ui(app: FastAPI) -> None:
    if not _WEB_STATIC_DIR.is_dir():
        msg = f"Web UI static directory is missing: {_WEB_STATIC_DIR}"
        raise RuntimeError(msg)

    index_path = _WEB_STATIC_DIR / "index.html"
    if not index_path.is_file():
        msg = f"Web UI index file is missing: {index_path}"
        raise RuntimeError(msg)

    @app.get("/app", include_in_schema=False)
    async def web_ui_index() -> RedirectResponse:
        return RedirectResponse(url="/app/", status_code=307)

    app.mount(
        "/app",
        StaticFiles(directory=_WEB_STATIC_DIR, html=True),
        name="web_ui",
    )
