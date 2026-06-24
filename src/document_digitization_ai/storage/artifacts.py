from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from pathlib import PurePosixPath, PureWindowsPath
from shutil import rmtree
from typing import Any

from document_digitization_ai.core import StorageSettings


class ArtifactLayoutError(ValueError):
    """Raised when artifact path input is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class JobArtifactPaths:
    upload_dir: Path
    original_upload_path: Path
    result_dir: Path
    result_json_path: Path
    preview_path: Path


@dataclass(frozen=True, slots=True)
class ExtractionAttemptArtifactPaths:
    attempt_dir_relative: str
    raw_response_artifact_path: str
    sanitized_response_artifact_path: str
    error_response_artifact_path: str


@dataclass(frozen=True, slots=True)
class StoredExtractionAttemptArtifact:
    relative_path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class StoredMarkdownExportArtifact:
    relative_path: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class DeletedArtifactTree:
    relative_path: str
    deleted: bool


@dataclass(frozen=True, slots=True)
class JobArtifactLayout:
    uploads_root: Path
    results_root: Path

    @classmethod
    def from_storage_settings(cls, settings: StorageSettings) -> JobArtifactLayout:
        return cls(
            uploads_root=settings.uploads_dir,
            results_root=settings.results_dir,
        )

    def upload_dir(self, job_id: str) -> Path:
        safe_job_id = _validate_path_segment(job_id, "job_id")
        return self.uploads_root / safe_job_id

    def original_upload_path(self, job_id: str, file_extension: str) -> Path:
        return self.upload_dir(job_id) / f"original{_normalize_extension(file_extension)}"

    def result_dir(self, job_id: str) -> Path:
        safe_job_id = _validate_path_segment(job_id, "job_id")
        return self.results_root / safe_job_id

    def result_json_path(self, job_id: str) -> Path:
        return self.result_dir(job_id) / "result.json"

    def preview_path(self, job_id: str) -> Path:
        return self.result_dir(job_id) / "preview.html"

    def paths_for_job(self, job_id: str, file_extension: str) -> JobArtifactPaths:
        return JobArtifactPaths(
            upload_dir=self.upload_dir(job_id),
            original_upload_path=self.original_upload_path(job_id, file_extension),
            result_dir=self.result_dir(job_id),
            result_json_path=self.result_json_path(job_id),
            preview_path=self.preview_path(job_id),
        )

    def ensure_upload_dir(self, job_id: str) -> Path:
        path = self.upload_dir(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_result_dir(self, job_id: str) -> Path:
        path = self.result_dir(job_id)
        path.mkdir(parents=True, exist_ok=True)
        return path

    def ensure_job_dirs(self, job_id: str, file_extension: str) -> JobArtifactPaths:
        self.ensure_upload_dir(job_id)
        self.ensure_result_dir(job_id)
        return self.paths_for_job(job_id, file_extension)


@dataclass(frozen=True, slots=True)
class ExtractionAttemptArtifactLayout:
    artifact_root: Path

    def attempt_dir_relative(self, job_id: str, attempt_number: int) -> str:
        safe_job_id = _validate_path_segment(job_id, "job_id")
        attempt_segment = _format_attempt_number(attempt_number)
        return f"jobs/{safe_job_id}/attempts/{attempt_segment}"

    def relative_path(
        self,
        job_id: str,
        attempt_number: int,
        filename: str,
    ) -> str:
        return build_extraction_attempt_artifact_path(
            job_id=job_id,
            attempt_number=attempt_number,
            filename=filename,
        )

    def paths_for_attempt(
        self,
        job_id: str,
        attempt_number: int,
    ) -> ExtractionAttemptArtifactPaths:
        attempt_dir = self.attempt_dir_relative(job_id, attempt_number)
        return ExtractionAttemptArtifactPaths(
            attempt_dir_relative=attempt_dir,
            raw_response_artifact_path=(
                f"{attempt_dir}/provider_raw_response.json"
            ),
            sanitized_response_artifact_path=(
                f"{attempt_dir}/provider_sanitized_response.json"
            ),
            error_response_artifact_path=(
                f"{attempt_dir}/provider_error_response.json"
            ),
        )

    def write_json_artifact(
        self,
        *,
        job_id: str,
        attempt_number: int,
        filename: str,
        payload: Any,
    ) -> StoredExtractionAttemptArtifact:
        relative_path = self.relative_path(job_id, attempt_number, filename)
        _ensure_json_compatible(payload, "payload")
        target_path = _safe_artifact_target_path(self.artifact_root, relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        data = f"{serialized}\n".encode("utf-8")
        target_path.write_bytes(data)
        return StoredExtractionAttemptArtifact(
            relative_path=relative_path,
            size_bytes=len(data),
        )


@dataclass(frozen=True, slots=True)
class MarkdownExportArtifactLayout:
    artifact_root: Path

    def relative_path(self, job_id: str) -> str:
        safe_job_id = _validate_path_segment(job_id, "job_id")
        return validate_relative_artifact_path(
            f"jobs/{safe_job_id}/exports/result.md"
        )

    def write_markdown_artifact(
        self,
        *,
        job_id: str,
        markdown: str,
    ) -> StoredMarkdownExportArtifact:
        relative_path = self.relative_path(job_id)
        target_path = _safe_artifact_target_path(self.artifact_root, relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        data = markdown.encode("utf-8")
        target_path.write_bytes(data)
        return StoredMarkdownExportArtifact(
            relative_path=relative_path,
            size_bytes=len(data),
        )


def delete_artifact_tree(
    artifact_root: Path,
    relative_path: str,
) -> DeletedArtifactTree:
    safe_relative_path = validate_relative_artifact_path(relative_path)
    target_path = _safe_artifact_target_path(artifact_root, safe_relative_path)
    if not target_path.exists():
        return DeletedArtifactTree(relative_path=safe_relative_path, deleted=False)
    if target_path.is_dir():
        rmtree(target_path)
    else:
        target_path.unlink()
    return DeletedArtifactTree(relative_path=safe_relative_path, deleted=True)


def build_extraction_attempt_artifact_path(
    *,
    job_id: str,
    attempt_number: int,
    filename: str,
) -> str:
    safe_job_id = _validate_path_segment(job_id, "job_id")
    attempt_segment = _format_attempt_number(attempt_number)
    safe_filename = _validate_path_segment(filename, "filename")
    return validate_relative_artifact_path(
        f"jobs/{safe_job_id}/attempts/{attempt_segment}/{safe_filename}"
    )


def validate_relative_artifact_path(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        msg = "artifact path must be a non-empty relative path"
        raise ArtifactLayoutError(msg)

    raw_path = value.strip()
    windows_path = PureWindowsPath(raw_path)
    if windows_path.is_absolute() or windows_path.drive:
        msg = "artifact path must not be an absolute Windows path"
        raise ArtifactLayoutError(msg)

    normalized_path = raw_path.replace("\\", "/")
    posix_path = PurePosixPath(normalized_path)
    if posix_path.is_absolute():
        msg = "artifact path must not be an absolute POSIX path"
        raise ArtifactLayoutError(msg)

    parts = normalized_path.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        msg = "artifact path must not contain empty, current, or parent segments"
        raise ArtifactLayoutError(msg)

    return "/".join(parts)


def _validate_path_segment(value: str, field_name: str) -> str:
    if not value.strip():
        msg = f"{field_name} must not be empty"
        raise ArtifactLayoutError(msg)
    if "/" in value or "\\" in value:
        msg = f"{field_name} must not contain path separators"
        raise ArtifactLayoutError(msg)
    path = Path(value)
    if path.name != value or value in {".", ".."}:
        msg = f"{field_name} must be a single safe path segment"
        raise ArtifactLayoutError(msg)
    return value


def _normalize_extension(file_extension: str) -> str:
    extension = file_extension.strip().lower()
    if not extension:
        msg = "file_extension must not be empty"
        raise ArtifactLayoutError(msg)
    if extension.startswith("."):
        segment = extension[1:]
    else:
        segment = extension
        extension = f".{extension}"
    _validate_path_segment(segment, "file_extension")
    return extension


def _format_attempt_number(attempt_number: int) -> str:
    if isinstance(attempt_number, bool) or not isinstance(attempt_number, int):
        msg = "attempt_number must be a positive integer"
        raise ArtifactLayoutError(msg)
    if attempt_number <= 0:
        msg = "attempt_number must be a positive integer"
        raise ArtifactLayoutError(msg)
    return f"{attempt_number:03d}"


def _safe_artifact_target_path(artifact_root: Path, relative_path: str) -> Path:
    normalized_relative_path = validate_relative_artifact_path(relative_path)
    root = artifact_root.resolve()
    target_path = root.joinpath(*normalized_relative_path.split("/")).resolve()
    try:
        target_path.relative_to(root)
    except ValueError as exc:
        msg = "artifact target path must stay inside artifact root"
        raise ArtifactLayoutError(msg) from exc
    return target_path


def _ensure_json_compatible(value: Any, field_name: str) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not value == value or value in {float("inf"), float("-inf")}:
            msg = f"{field_name} must be finite"
            raise ArtifactLayoutError(msg)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_compatible(item, f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                msg = f"{field_name} keys must be non-empty strings"
                raise ArtifactLayoutError(msg)
            _ensure_json_compatible(item, f"{field_name}.{key}")
        return
    msg = f"{field_name} must be JSON-compatible"
    raise ArtifactLayoutError(msg)
