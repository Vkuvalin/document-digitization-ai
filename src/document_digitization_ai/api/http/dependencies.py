from __future__ import annotations

from fastapi import Request

from document_digitization_ai.application import DocumentProcessingFacade


def get_document_facade(request: Request) -> DocumentProcessingFacade:
    return request.app.state.document_facade

