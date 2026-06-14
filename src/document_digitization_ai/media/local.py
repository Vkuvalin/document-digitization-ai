from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from document_digitization_ai.core import (
    MediaStagingBackend,
    MediaStagingSettings,
    SettingsError,
)
from document_digitization_ai.media.base import (
    MediaStagingConfigurationError,
    MediaStagingError,
    MediaStagingInput,
    MediaStagingPort,
    MediaStagingResult,
    StagedMediaReference,
    StagedMediaReferenceKind,
    UnsupportedMediaStagingBackendError,
)

if TYPE_CHECKING:
    from document_digitization_ai.media.imgbb import HTTPTransport


@dataclass(frozen=True, slots=True)
class LocalNoopMediaStagingService:
    async def stage(self, media: MediaStagingInput) -> MediaStagingResult:
        path = media.local_path
        if not path.exists():
            msg = f"Media file does not exist: {path}"
            raise MediaStagingError(msg)
        if not path.is_file():
            msg = f"Media path must point to a file: {path}"
            raise MediaStagingError(msg)

        return MediaStagingResult(
            reference=StagedMediaReference(
                kind=StagedMediaReferenceKind.LOCAL_FILE,
                value=str(path),
                mime_type=media.mime_type,
                file_size_bytes=media.file_size_bytes,
                sha256=media.sha256,
                metadata=media.metadata,
            ),
            external_upload_performed=False,
        )


def build_media_staging_service(
    settings: MediaStagingSettings,
    *,
    imgbb_transport: HTTPTransport | None = None,
) -> MediaStagingPort:
    if settings.backend is MediaStagingBackend.NONE:
        return LocalNoopMediaStagingService()
    if settings.backend is MediaStagingBackend.IMGBB:
        from document_digitization_ai.media.imgbb import ImgBBMediaStagingService

        try:
            api_key = settings.require_imgbb_api_key()
        except SettingsError as exc:
            raise MediaStagingConfigurationError(str(exc)) from exc
        if api_key is None:
            msg = "IMGBB_API_KEY must be set when MEDIA_STAGING_BACKEND=imgbb"
            raise MediaStagingConfigurationError(msg)
        if imgbb_transport is not None:
            return ImgBBMediaStagingService(
                api_key=api_key,
                ttl_seconds=settings.ttl_seconds,
                transport=imgbb_transport,
            )
        return ImgBBMediaStagingService(
            api_key=api_key,
            ttl_seconds=settings.ttl_seconds,
        )

    msg = f"Unsupported media staging backend: {settings.backend}"
    raise UnsupportedMediaStagingBackendError(msg)
