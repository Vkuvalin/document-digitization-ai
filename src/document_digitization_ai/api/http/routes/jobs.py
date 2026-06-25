from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, Response

from document_digitization_ai.api.http.dependencies import get_document_facade
from document_digitization_ai.api.http.errors import (
    ApiHTTPError,
    call_facade,
    raise_for_backend_error,
)
from document_digitization_ai.api.http.schemas import (
    ArtifactListResponse,
    DeleteJobResponse,
    ExtractionResultResponse,
    JobDetailResponse,
    JobHistoryResponse,
    JobStatusResponse,
    MarkdownExportResponse,
)
from document_digitization_ai.application import DocumentProcessingFacade


router = APIRouter(tags=["jobs"])

DocumentFacade = Annotated[DocumentProcessingFacade, Depends(get_document_facade)]


@router.get("/jobs", response_model=JobHistoryResponse)
async def list_jobs(
    facade: DocumentFacade,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> JobHistoryResponse:
    result = await call_facade(
        lambda: facade.list_jobs(limit=limit, offset=offset, status=status)
    )
    raise_for_backend_error(result.error)
    return JobHistoryResponse.from_view(result)


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
async def get_job_detail(
    job_id: str,
    facade: DocumentFacade,
) -> JobDetailResponse:
    result = await call_facade(lambda: facade.get_job_detail(job_id))
    raise_for_backend_error(result.error)
    return JobDetailResponse.from_view(result)


@router.get("/jobs/{job_id}/preview")
async def get_job_preview(
    job_id: str,
    facade: DocumentFacade,
    download: bool = False,
) -> FileResponse:
    result = await call_facade(lambda: facade.get_job_preview_file(job_id))
    raise_for_backend_error(result.error)
    if result.path is None or result.filename is None:
        raise ApiHTTPError("internal_error", "Internal server error.")
    content_disposition_type = (
        "attachment" if download or not result.supports_inline_preview else "inline"
    )
    return FileResponse(
        result.path,
        media_type=result.content_type or "application/octet-stream",
        filename=result.filename,
        content_disposition_type=content_disposition_type,
    )


@router.delete("/jobs/{job_id}", response_model=DeleteJobResponse)
async def delete_job(
    job_id: str,
    facade: DocumentFacade,
) -> DeleteJobResponse:
    result = await call_facade(lambda: facade.delete_job(job_id))
    raise_for_backend_error(result.error)
    return DeleteJobResponse.from_view(result)


@router.get("/jobs/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    facade: DocumentFacade,
) -> JobStatusResponse:
    result = await call_facade(lambda: facade.get_job_status(job_id))
    raise_for_backend_error(result.error)
    return JobStatusResponse.from_view(result)


@router.get("/jobs/{job_id}/result", response_model=ExtractionResultResponse)
async def get_job_result(
    job_id: str,
    facade: DocumentFacade,
) -> ExtractionResultResponse:
    result = await call_facade(lambda: facade.get_extraction_result(job_id))
    raise_for_backend_error(result.error, allow_result_unavailable=True)
    return ExtractionResultResponse.from_view(result)


@router.get("/jobs/{job_id}/markdown", response_model=MarkdownExportResponse)
async def get_job_markdown(
    job_id: str,
    facade: DocumentFacade,
) -> MarkdownExportResponse:
    result = await call_facade(
        lambda: facade.get_result_markdown(job_id, write_artifact=False)
    )
    raise_for_backend_error(result.error, allow_result_unavailable=True)
    return MarkdownExportResponse.from_view(result)


@router.post("/jobs/{job_id}/markdown/export", response_model=MarkdownExportResponse)
async def export_job_markdown(
    job_id: str,
    facade: DocumentFacade,
) -> MarkdownExportResponse:
    result = await call_facade(
        lambda: facade.get_result_markdown(job_id, write_artifact=True)
    )
    raise_for_backend_error(result.error, allow_result_unavailable=True)
    return MarkdownExportResponse.from_view(result)


@router.get("/jobs/{job_id}/pdf")
async def get_job_pdf(
    job_id: str,
    facade: DocumentFacade,
) -> Response:
    result = await call_facade(lambda: facade.get_result_pdf(job_id))
    raise_for_backend_error(result.error)
    if result.pdf is None or result.filename is None:
        raise ApiHTTPError("internal_error", "Internal server error.")
    return Response(
        content=result.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{result.filename}"',
        },
    )


@router.get("/jobs/{job_id}/artifacts", response_model=ArtifactListResponse)
async def get_job_artifacts(
    job_id: str,
    facade: DocumentFacade,
) -> ArtifactListResponse:
    result = await call_facade(lambda: facade.get_job_artifacts(job_id))
    raise_for_backend_error(result.error)
    return ArtifactListResponse.from_view(result)
