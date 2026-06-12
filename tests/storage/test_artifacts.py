from inspect import Parameter, signature
from pathlib import Path

import pytest

from document_digitization_ai.core import StorageSettings
from document_digitization_ai.storage import ArtifactLayoutError, JobArtifactLayout


def test_job_artifact_layout_builds_deterministic_paths(tmp_path: Path) -> None:
    layout = JobArtifactLayout.from_storage_settings(
        StorageSettings(
            database_url="sqlite+aiosqlite:///./data/app.db",
            data_dir=tmp_path / "data",
            uploads_dir=tmp_path / "data" / "uploads",
            results_dir=tmp_path / "data" / "results",
        )
    )

    paths = layout.paths_for_job("job-001", "JPG")

    assert paths.upload_dir == tmp_path / "data" / "uploads" / "job-001"
    assert paths.original_upload_path == paths.upload_dir / "original.jpg"
    assert paths.result_dir == tmp_path / "data" / "results" / "job-001"
    assert paths.result_json_path == paths.result_dir / "result.json"
    assert paths.preview_path == paths.result_dir / "preview.html"
    assert not paths.upload_dir.exists()
    assert not paths.result_dir.exists()


def test_job_artifact_layout_creates_directories_only_when_explicit(
    tmp_path: Path,
) -> None:
    layout = JobArtifactLayout(
        uploads_root=tmp_path / "uploads",
        results_root=tmp_path / "results",
    )

    layout.ensure_upload_dir("job-002")

    assert (tmp_path / "uploads" / "job-002").is_dir()
    assert not (tmp_path / "results" / "job-002").exists()

    layout.ensure_result_dir("job-002")

    assert (tmp_path / "results" / "job-002").is_dir()


def test_job_artifact_layout_ensures_job_dirs_with_explicit_extension(
    tmp_path: Path,
) -> None:
    layout = JobArtifactLayout(
        uploads_root=tmp_path / "uploads",
        results_root=tmp_path / "results",
    )

    paths = layout.ensure_job_dirs("job-003", ".jpg")

    assert paths.original_upload_path == tmp_path / "uploads" / "job-003" / "original.jpg"
    assert paths.upload_dir.is_dir()
    assert paths.result_dir.is_dir()
    assert (
        signature(layout.ensure_job_dirs).parameters["file_extension"].default
        is Parameter.empty
    )


def test_job_artifact_layout_rejects_unsafe_path_segments(tmp_path: Path) -> None:
    layout = JobArtifactLayout(
        uploads_root=tmp_path / "uploads",
        results_root=tmp_path / "results",
    )

    with pytest.raises(ArtifactLayoutError):
        layout.upload_dir("../job")

    with pytest.raises(ArtifactLayoutError):
        layout.upload_dir("parent/job")

    with pytest.raises(ArtifactLayoutError):
        layout.upload_dir("parent\\job")

    with pytest.raises(ArtifactLayoutError):
        layout.original_upload_path("job-004", "../jpg")

    with pytest.raises(ArtifactLayoutError):
        layout.original_upload_path("job-004", "bad\\jpg")
