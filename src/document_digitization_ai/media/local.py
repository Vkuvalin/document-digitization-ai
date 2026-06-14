from __future__ import annotations

from dataclasses import dataclass

from document_digitization_ai.core import MediaStagingBackend, MediaStagingSettings
from document_digitization_ai.media.base import (
    MediaStagingError,
    MediaStagingInput,
    MediaStagingPort,
    MediaStagingResult,
    StagedMediaReference,
    StagedMediaReferenceKind,
    UnsupportedMediaStagingBackendError,
)


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


def build_media_staging_service(settings: MediaStagingSettings) -> MediaStagingPort:
    if settings.backend is MediaStagingBackend.NONE:
        return LocalNoopMediaStagingService()
    if settings.backend is MediaStagingBackend.IMGBB:
        msg = "MEDIA_STAGING_BACKEND=imgbb is not implemented in Stage 8"
        raise UnsupportedMediaStagingBackendError(msg)

    msg = f"Unsupported media staging backend: {settings.backend}"
    raise UnsupportedMediaStagingBackendError(msg)
