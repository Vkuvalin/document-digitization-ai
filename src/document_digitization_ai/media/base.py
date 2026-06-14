from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from math import isfinite
from pathlib import Path
from typing import Protocol


class MediaStagingError(RuntimeError):
    """Base error for media staging failures."""


class UnsupportedMediaStagingBackendError(MediaStagingError):
    """Raised when selected staging backend has no approved implementation."""


class StagedMediaReferenceKind(StrEnum):
    LOCAL_FILE = "local_file"
    NONE = "none"
    PUBLIC_URL = "public_url"
    PROVIDER_FILE_ID = "provider_file_id"


@dataclass(frozen=True, slots=True)
class MediaStagingInput:
    local_path: Path
    mime_type: str
    file_size_bytes: int
    sha256: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _ensure_non_empty_text(str(self.local_path), "local_path")
        _ensure_non_empty_text(self.mime_type, "mime_type")
        _ensure_positive_int(self.file_size_bytes, "file_size_bytes")
        _ensure_optional_non_empty_text(self.sha256, "sha256")
        _ensure_json_object(self.metadata, "metadata")

    def to_dict(self) -> dict[str, object]:
        return {
            "local_path": str(self.local_path),
            "mime_type": self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "sha256": self.sha256,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class StagedMediaReference:
    kind: StagedMediaReferenceKind
    value: str
    mime_type: str
    file_size_bytes: int
    sha256: str | None = None
    expires_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, StagedMediaReferenceKind):
            msg = "kind must be a StagedMediaReferenceKind value"
            raise ValueError(msg)
        _ensure_non_empty_text(self.value, "value")
        _ensure_non_empty_text(self.mime_type, "mime_type")
        _ensure_positive_int(self.file_size_bytes, "file_size_bytes")
        _ensure_optional_non_empty_text(self.sha256, "sha256")
        _ensure_json_object(self.metadata, "metadata")

    def to_dict(self) -> dict[str, object]:
        expires_at = self.expires_at.isoformat() if self.expires_at is not None else None
        return {
            "kind": self.kind.value,
            "value": self.value,
            "mime_type": self.mime_type,
            "file_size_bytes": self.file_size_bytes,
            "sha256": self.sha256,
            "expires_at": expires_at,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class MediaStagingResult:
    reference: StagedMediaReference
    external_upload_performed: bool
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.reference, StagedMediaReference):
            msg = "reference must be a StagedMediaReference value"
            raise ValueError(msg)
        if not isinstance(self.external_upload_performed, bool):
            msg = "external_upload_performed must be a boolean"
            raise ValueError(msg)
        for warning in self.warnings:
            _ensure_non_empty_text(warning, "warnings")

    def to_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference.to_dict(),
            "external_upload_performed": self.external_upload_performed,
            "warnings": list(self.warnings),
        }


class MediaStagingPort(Protocol):
    async def stage(self, media: MediaStagingInput) -> MediaStagingResult: ...


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_optional_non_empty_text(value: str | None, field_name: str) -> None:
    if value is not None:
        _ensure_non_empty_text(value, field_name)


def _ensure_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        msg = f"{field_name} must be a positive integer"
        raise ValueError(msg)


def _ensure_json_object(value: Mapping[str, object], field_name: str) -> None:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be a JSON object"
        raise ValueError(msg)
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            msg = f"{field_name} keys must be non-empty strings"
            raise ValueError(msg)
        _ensure_json_compatible(item, f"{field_name}.{key}")


def _ensure_json_compatible(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not isfinite(value):
            msg = f"{field_name} must be finite"
            raise ValueError(msg)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_compatible(item, f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        _ensure_json_object(value, field_name)
        return
    msg = f"{field_name} must be JSON-compatible"
    raise ValueError(msg)
