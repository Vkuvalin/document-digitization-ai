from __future__ import annotations

import asyncio
import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from document_digitization_ai.media.base import (
    MediaStagingConfigurationError,
    MediaStagingError,
    MediaStagingInput,
    MediaStagingResult,
    StagedMediaReference,
    StagedMediaReferenceKind,
)


IMGBB_UPLOAD_URL = "https://api.imgbb.com/1/upload"
IMGBB_MIN_EXPIRATION_SECONDS = 60
IMGBB_MAX_EXPIRATION_SECONDS = 15_552_000
DEFAULT_IMGBB_TIMEOUT_SECONDS = 180


@dataclass(frozen=True, slots=True)
class HTTPResponseData:
    status_code: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class HTTPTransport(Protocol):
    def post_form(
        self,
        url: str,
        fields: Mapping[str, str],
        *,
        timeout_seconds: int,
    ) -> HTTPResponseData: ...


@dataclass(frozen=True, slots=True)
class DefaultImgBBHTTPTransport:
    def post_form(
        self,
        url: str,
        fields: Mapping[str, str],
        *,
        timeout_seconds: int,
    ) -> HTTPResponseData:
        payload = urlencode(fields).encode("utf-8")
        request = Request(
            url=url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        with urlopen(request, timeout=timeout_seconds) as response:
            response_obj = cast(Any, response)
            status_code = int(response_obj.status)
            headers = {
                str(key): str(value)
                for key, value in response_obj.headers.items()
            }
            body = cast(bytes, response_obj.read())
        return HTTPResponseData(
            status_code=status_code,
            body=body,
            headers=headers,
        )


@dataclass(frozen=True, slots=True)
class ImgBBMediaStagingService:
    api_key: str = field(repr=False)
    ttl_seconds: int = 3600
    transport: HTTPTransport = field(
        default_factory=DefaultImgBBHTTPTransport,
        repr=False,
    )
    upload_url: str = IMGBB_UPLOAD_URL
    timeout_seconds: int = DEFAULT_IMGBB_TIMEOUT_SECONDS

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.api_key, "api_key")
        _ensure_non_empty_text(self.upload_url, "upload_url")
        _ensure_positive_int(self.timeout_seconds, "timeout_seconds")
        _ensure_imgbb_expiration(self.ttl_seconds)

    async def stage(self, media: MediaStagingInput) -> MediaStagingResult:
        image_path = _validate_local_media_file(media.local_path)
        image_bytes = image_path.read_bytes()
        encoded_image = base64.b64encode(image_bytes).decode("ascii")
        response = await asyncio.to_thread(
            self._post_upload,
            encoded_image,
        )
        payload = _parse_imgbb_response(response)
        direct_url, metadata = _extract_public_url_and_metadata(payload)

        return MediaStagingResult(
            reference=StagedMediaReference(
                kind=StagedMediaReferenceKind.PUBLIC_URL,
                value=direct_url,
                mime_type=media.mime_type,
                file_size_bytes=media.file_size_bytes,
                sha256=media.sha256,
                expires_at=datetime.now(UTC) + timedelta(seconds=self.ttl_seconds),
                metadata=metadata,
            ),
            external_upload_performed=True,
        )

    def _post_upload(self, encoded_image: str) -> HTTPResponseData:
        fields = {
            "key": self.api_key,
            "image": encoded_image,
            "expiration": str(self.ttl_seconds),
        }
        try:
            return self.transport.post_form(
                self.upload_url,
                fields,
                timeout_seconds=self.timeout_seconds,
            )
        except Exception as exc:
            msg = "ImgBB upload failed"
            raise MediaStagingError(msg) from exc


def _parse_imgbb_response(response: HTTPResponseData) -> Mapping[str, object]:
    if response.status_code < 200 or response.status_code >= 300:
        msg = f"ImgBB upload failed with HTTP status {response.status_code}"
        raise MediaStagingError(msg)
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = "ImgBB response was not valid JSON"
        raise MediaStagingError(msg) from exc
    if not isinstance(payload, Mapping):
        msg = "ImgBB response must be a JSON object"
        raise MediaStagingError(msg)
    if payload.get("success") is not True:
        msg = "ImgBB upload response reported success=false"
        raise MediaStagingError(msg)
    return payload


def _extract_public_url_and_metadata(
    payload: Mapping[str, object],
) -> tuple[str, Mapping[str, object]]:
    data = _require_mapping(payload.get("data"), "data")
    direct_url, url_source = _extract_direct_url(data)
    if not _is_public_http_url(direct_url):
        msg = "ImgBB response public image URL must be HTTP(S)"
        raise MediaStagingError(msg)

    metadata: dict[str, object] = {
        "staging_backend": "imgbb",
        "provider_facing_url_source": url_source,
        "private_cleanup_url_available": isinstance(data.get("delete_url"), str),
    }
    image_id = data.get("id")
    if isinstance(image_id, str) and image_id.strip():
        metadata["imgbb_id"] = image_id
    return direct_url, metadata


def _extract_direct_url(data: Mapping[str, object]) -> tuple[str, str]:
    image = data.get("image")
    if isinstance(image, Mapping):
        image_url = image.get("url")
        if isinstance(image_url, str) and image_url.strip():
            return image_url.strip(), "data.image.url"

    for key in ("url", "display_url"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip(), f"data.{key}"

    msg = "ImgBB response is missing public image URL"
    raise MediaStagingError(msg)


def _require_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"ImgBB response {field_name} must be an object"
        raise MediaStagingError(msg)
    return value


def _validate_local_media_file(path: Path) -> Path:
    if not path.exists():
        msg = f"Media file does not exist: {path}"
        raise MediaStagingError(msg)
    if not path.is_file():
        msg = f"Media path must point to a file: {path}"
        raise MediaStagingError(msg)
    return path


def _is_public_http_url(value: str) -> bool:
    return value.startswith("https://") or value.startswith("http://")


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise MediaStagingConfigurationError(msg)


def _ensure_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{field_name} must be a positive integer"
        raise MediaStagingConfigurationError(msg)


def _ensure_imgbb_expiration(value: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < IMGBB_MIN_EXPIRATION_SECONDS
        or value > IMGBB_MAX_EXPIRATION_SECONDS
    ):
        msg = (
            "MEDIA_STAGING_TTL_SECONDS must be between "
            f"{IMGBB_MIN_EXPIRATION_SECONDS} and "
            f"{IMGBB_MAX_EXPIRATION_SECONDS} for ImgBB"
        )
        raise MediaStagingConfigurationError(msg)
