from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
