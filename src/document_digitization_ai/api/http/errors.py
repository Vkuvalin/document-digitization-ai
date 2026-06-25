from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from fastapi import Request
from fastapi.responses import JSONResponse

from document_digitization_ai.api.http.schemas import ApiErrorResponse
from document_digitization_ai.application import BackendErrorView


_T = TypeVar("_T")


_ERROR_STATUS_CODES = {
    "job_not_found": 404,
    "invalid_input": 400,
    "unsupported_file": 415,
    "too_large_upload": 413,
    "artifact_access_denied": 403,
    "artifact_delete_failed": 500,
    "artifact_not_found": 404,
    "artifact_write_failed": 500,
    "malformed_result_payload": 500,
    "result_unavailable": 409,
    "internal_error": 500,
}

_GENERIC_INTERNAL_MESSAGES = {
    "artifact_access_denied": "Artifact access denied.",
    "artifact_delete_failed": "Artifact could not be deleted.",
    "artifact_not_found": "Artifact was not found.",
    "artifact_write_failed": "Artifact could not be written.",
    "malformed_result_payload": "Result payload could not be returned.",
    "internal_error": "Internal server error.",
}


class ApiHTTPError(Exception):
    def __init__(
        self,
        error_type: str,
        error_message: str,
        *,
        status_code: int | None = None,
    ) -> None:
        super().__init__(error_type)
        self.error_type = error_type
        self.error_message = error_message
        self.status_code = status_code or _ERROR_STATUS_CODES.get(error_type, 500)


async def api_http_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    if not isinstance(exc, ApiHTTPError):
        exc = ApiHTTPError(
            "internal_error",
            _GENERIC_INTERNAL_MESSAGES["internal_error"],
        )
    response = ApiErrorResponse(
        error_type=exc.error_type,
        error_message=exc.error_message,
    )
    return JSONResponse(status_code=exc.status_code, content=response.model_dump())


async def call_facade(operation: Callable[[], Awaitable[_T]]) -> _T:
    try:
        return await operation()
    except ApiHTTPError:
        raise
    except Exception as exc:
        raise ApiHTTPError(
            "internal_error",
            _GENERIC_INTERNAL_MESSAGES["internal_error"],
        ) from exc


def raise_for_backend_error(
    error: BackendErrorView | None,
    *,
    allow_result_unavailable: bool = False,
) -> None:
    if error is None:
        return
    if allow_result_unavailable and error.error_type == "result_unavailable":
        return
    raise ApiHTTPError(
        error.error_type,
        _safe_error_message(error.error_type, error.error_message),
    )


def raise_api_error(error_type: str, error_message: str) -> None:
    raise ApiHTTPError(error_type, _safe_error_message(error_type, error_message))


def _safe_error_message(error_type: str, error_message: str) -> str:
    generic_message = _GENERIC_INTERNAL_MESSAGES.get(error_type)
    if generic_message is not None:
        return generic_message
    message = error_message.strip()
    if not message:
        return "Request could not be processed."
    return message
