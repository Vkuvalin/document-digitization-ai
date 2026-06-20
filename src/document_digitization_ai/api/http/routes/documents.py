from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Request, UploadFile

from document_digitization_ai.api.http.dependencies import get_document_facade
from document_digitization_ai.api.http.errors import (
    call_facade,
    raise_api_error,
    raise_for_backend_error,
)
from document_digitization_ai.api.http.schemas import SubmitDocumentResponse
from document_digitization_ai.application import DocumentProcessingFacade


router = APIRouter(tags=["documents"])

DocumentFacade = Annotated[DocumentProcessingFacade, Depends(get_document_facade)]


@router.post("/documents", response_model=SubmitDocumentResponse)
async def submit_document(
    request: Request,
    facade: DocumentFacade,
    file: Annotated[UploadFile, File()],
) -> SubmitDocumentResponse:
    max_upload_size_bytes = (
        request.app.state.settings.image_diagnostics.max_file_size_bytes
    )
    data = await file.read(max_upload_size_bytes + 1)
    if len(data) > max_upload_size_bytes:
        raise_api_error(
            "too_large_upload",
            "Uploaded file exceeds the configured size limit.",
        )
    if not data:
        raise_api_error("invalid_input", "Uploaded file is empty.")

    result = await call_facade(
        lambda: facade.submit_document_file(
            filename=file.filename or "",
            content_type=file.content_type or "",
            data=data,
        )
    )
    raise_for_backend_error(result.error)
    return SubmitDocumentResponse.from_view(result)

