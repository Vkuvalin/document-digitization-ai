from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, cast

from fastapi import FastAPI
from fastapi.testclient import TestClient

from document_digitization_ai.api.http import create_app
from document_digitization_ai.application import (
    ArtifactListView,
    ArtifactReference,
    AttemptSummary,
    BackendErrorView,
    DocumentProcessingFacade,
    ExtractionResultView,
    JobDetailView,
    JobHistoryView,
    JobStatusView,
    JobSummary,
    MarkdownExportView,
    SubmitDocumentResult,
)
from document_digitization_ai.core import AppSettings


def test_create_app_registers_routes_and_uses_injected_facade(tmp_path: Path) -> None:
    facade = FakeDocumentFacade()

    app = create_app(
        settings=_app_settings(tmp_path),
        facade=cast(DocumentProcessingFacade, facade),
    )

    assert isinstance(app, FastAPI)
    assert facade.calls == []
    assert {
        "/documents",
        "/jobs",
        "/jobs/{job_id}",
        "/jobs/{job_id}/status",
        "/jobs/{job_id}/result",
        "/jobs/{job_id}/markdown",
        "/jobs/{job_id}/markdown/export",
        "/jobs/{job_id}/artifacts",
        "/health",
    }.issubset(app.openapi()["paths"])

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert facade.calls == []


def test_web_ui_static_serving_under_app_keeps_api_routes_clean(
    tmp_path: Path,
) -> None:
    facade = FakeDocumentFacade()
    client = _client(tmp_path, facade)

    app_index = client.get("/app")
    app_slash = client.get("/app/")
    stylesheet = client.get("/app/styles.css")
    app_script = client.get("/app/js/app.js")
    api_client_script = client.get("/app/js/apiClient.js")
    result_dialog_script = client.get("/app/js/uiResultDialog.js")
    root = client.get("/")
    health = client.get("/health")

    assert app_index.status_code == 200
    assert '<html lang="ru">' in app_index.text
    assert app_slash.status_code == 200
    assert '<script src="./js/apiClient.js"></script>' in app_slash.text
    assert stylesheet.status_code == 200
    assert "text/css" in stylesheet.headers["content-type"]
    assert "--color-primary" in stylesheet.text
    assert app_script.status_code == 200
    assert "Stage19AWorkspace.init({ apiClient })" in app_script.text
    assert api_client_script.status_code == 200
    assert "Stage19BApiClient" in api_client_script.text
    assert "localhost" not in api_client_script.text
    assert result_dialog_script.status_code == 200
    assert 'VALIDATION_PARTIAL: "Частичная проверка"' in result_dialog_script.text
    assert 'en: "Английский"' in result_dialog_script.text
    assert root.status_code == 404
    assert health.status_code == 200
    assert facade.calls == []


def test_upload_endpoint_passes_file_to_facade(tmp_path: Path) -> None:
    facade = FakeDocumentFacade()
    client = _client(tmp_path, facade)

    response = client.post(
        "/documents",
        files={"file": ("upload.jpg", b"image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {
        "accepted": True,
        "job_id": "job-001",
        "status": "result_ready",
        "result_available": True,
        "error": None,
    }
    assert facade.submitted_file == {
        "filename": "upload.jpg",
        "content_type": "image/jpeg",
        "data": b"image-bytes",
    }


def test_upload_endpoint_rejects_empty_missing_too_large_and_unsafe_uploads(
    tmp_path: Path,
) -> None:
    empty_facade = FakeDocumentFacade()
    empty_response = _client(tmp_path, empty_facade).post(
        "/documents",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )

    missing_response = _client(tmp_path, FakeDocumentFacade()).post("/documents")

    too_large_facade = FakeDocumentFacade()
    too_large_response = _client(
        tmp_path,
        too_large_facade,
        max_upload_size_bytes=4,
    ).post(
        "/documents",
        files={"file": ("large.jpg", b"12345", "image/jpeg")},
    )

    unsafe_facade = FakeDocumentFacade()
    unsafe_response = _client(tmp_path, unsafe_facade).post(
        "/documents",
        files={"file": ("../unsafe.jpg", b"image-bytes", "image/jpeg")},
    )

    no_source_path_response = _client(tmp_path, FakeDocumentFacade()).post(
        "/documents/source_path",
        json={"source_path": "C:/Users/User/secret.jpg"},
    )

    assert empty_response.status_code == 400
    assert empty_response.json()["error_type"] == "invalid_input"
    assert empty_facade.calls == []
    assert missing_response.status_code == 422
    assert too_large_response.status_code == 413
    assert too_large_response.json()["error_type"] == "too_large_upload"
    assert too_large_facade.calls == []
    assert unsafe_response.status_code == 400
    assert unsafe_response.json()["error_type"] == "invalid_input"
    assert unsafe_facade.submitted_file is not None
    assert no_source_path_response.status_code == 404


def test_job_endpoints_delegate_to_facade(tmp_path: Path) -> None:
    facade = FakeDocumentFacade()
    client = _client(tmp_path, facade)

    history = client.get("/jobs", params={"limit": 10, "offset": 2, "status": "created"})
    detail = client.get("/jobs/job-001")
    status = client.get("/jobs/job-001/status")
    result = client.get("/jobs/job-001/result")
    markdown = client.get("/jobs/job-001/markdown")
    markdown_export = client.post("/jobs/job-001/markdown/export")
    artifacts = client.get("/jobs/job-001/artifacts")

    assert history.status_code == 200
    assert history.json()["jobs"][0]["job_id"] == "job-001"
    assert detail.status_code == 200
    assert detail.json()["summary"]["job_id"] == "job-001"
    assert status.status_code == 200
    assert status.json()["status"] == "result_ready"
    assert result.status_code == 200
    assert result.json()["result"]["raw_text"]["text"] == "Deterministic text."
    assert markdown.status_code == 200
    assert markdown.json()["markdown"] == "# Result\n"
    assert markdown_export.status_code == 200
    assert markdown_export.json()["artifact"]["relative_path"] == (
        "jobs/job-001/exports/result.md"
    )
    assert artifacts.status_code == 200
    assert artifacts.json()["artifacts"][0]["relative_path"] == (
        "jobs/job-001/exports/result.md"
    )
    assert facade.calls == [
        ("list_jobs", 10, 2, "created"),
        ("get_job_detail", "job-001"),
        ("get_job_status", "job-001"),
        ("get_extraction_result", "job-001"),
        ("get_result_markdown", "job-001", False),
        ("get_result_markdown", "job-001", True),
        ("get_job_artifacts", "job-001"),
    ]


def test_error_mapping_is_safe_and_result_unavailable_stays_normal(
    tmp_path: Path,
) -> None:
    facade = FakeDocumentFacade()
    facade.detail_response = JobDetailView(
        job_id="missing",
        summary=None,
        status=None,
        error=_error("job_not_found", "Document job was not found."),
    )
    facade.history_response = JobHistoryView(
        jobs=(),
        limit=0,
        offset=0,
        total=0,
        error=_error("invalid_input", "Job history limit is invalid."),
    )
    facade.submit_response = SubmitDocumentResult(
        accepted=False,
        job_id=None,
        status=None,
        result_available=False,
        error=_error("unsupported_file", "Uploaded file is unsupported."),
    )
    facade.artifacts_response = ArtifactListView(
        job_id="job-001",
        artifacts=(),
        error=_error("artifact_access_denied", "Artifact access denied."),
    )
    facade.result_response = ExtractionResultView(
        job_id="job-001",
        result_available=False,
        error=_error(
            "result_unavailable",
            "Document job does not have an extraction result.",
        ),
    )
    client = _client(tmp_path, facade)

    missing = client.get("/jobs/missing")
    invalid = client.get("/jobs")
    unsupported = client.post(
        "/documents",
        files={"file": ("upload.tiff", b"image-bytes", "image/tiff")},
    )
    denied = client.get("/jobs/job-001/artifacts")
    unavailable = client.get("/jobs/job-001/result")

    assert missing.status_code == 404
    assert missing.json()["error_type"] == "job_not_found"
    assert invalid.status_code == 400
    assert invalid.json()["error_type"] == "invalid_input"
    assert unsupported.status_code == 415
    assert unsupported.json()["error_type"] == "unsupported_file"
    assert denied.status_code == 403
    assert denied.json()["error_type"] == "artifact_access_denied"
    assert unavailable.status_code == 200
    assert unavailable.json()["result_available"] is False
    assert unavailable.json()["error"]["error_type"] == "result_unavailable"


def test_not_found_and_internal_error_mapping_are_safe(tmp_path: Path) -> None:
    facade = FakeDocumentFacade()
    facade.artifacts_response = ArtifactListView(
        job_id="job-001",
        artifacts=(),
        error=_error("artifact_not_found", r"C:\Users\User\secret\artifact.json"),
    )
    facade.raise_on_status = RuntimeError(r"C:\Users\User\.env OPENROUTER_API_KEY=secret")
    client = _client(tmp_path, facade)

    missing_artifact = client.get("/jobs/job-001/artifacts")
    internal_error = client.get("/jobs/job-001/status")

    assert missing_artifact.status_code == 404
    assert missing_artifact.json()["error_type"] == "artifact_not_found"
    assert missing_artifact.json()["error_message"] == "Artifact was not found."
    assert r"C:\Users" not in str(missing_artifact.json())
    assert internal_error.status_code == 500
    assert internal_error.json() == {
        "error_type": "internal_error",
        "error_message": "Internal server error.",
    }
    assert "OPENROUTER_API_KEY" not in str(internal_error.json())
    assert r"C:\Users" not in str(internal_error.json())


def test_backend_500_error_types_use_safe_messages(tmp_path: Path) -> None:
    facade = FakeDocumentFacade()
    facade.markdown_export_response = MarkdownExportView(
        job_id="job-001",
        result_available=False,
        error=_error("artifact_write_failed", r"C:\Users\User\secret\result.md"),
    )
    facade.result_response = ExtractionResultView(
        job_id="job-001",
        result_available=False,
        error=_error("malformed_result_payload", "SQL row payload repr"),
    )
    client = _client(tmp_path, facade)

    artifact_write = client.post("/jobs/job-001/markdown/export")
    malformed_result = client.get("/jobs/job-001/result")

    assert artifact_write.status_code == 500
    assert artifact_write.json() == {
        "error_type": "artifact_write_failed",
        "error_message": "Artifact could not be written.",
    }
    assert r"C:\Users" not in str(artifact_write.json())
    assert malformed_result.status_code == 500
    assert malformed_result.json() == {
        "error_type": "malformed_result_payload",
        "error_message": "Result payload could not be returned.",
    }
    assert "SQL row payload repr" not in str(malformed_result.json())


def test_artifact_download_endpoint_is_deferred(tmp_path: Path) -> None:
    client = _client(tmp_path, FakeDocumentFacade())

    response = client.get(
        "/jobs/job-001/artifacts/download",
        params={"path": "jobs/job-001/exports/result.md"},
    )

    assert response.status_code == 404


def test_http_adapter_boundaries() -> None:
    api_http_files = tuple(Path("src/document_digitization_ai/api/http").rglob("*.py"))
    route_files = tuple(Path("src/document_digitization_ai/api/http/routes").glob("*.py"))

    assert api_http_files
    assert any(
        _imports_module(path, "document_digitization_ai.application")
        for path in api_http_files
    )
    for path in Path("src/document_digitization_ai/application").glob("*.py"):
        assert not _imports_module(path, "document_digitization_ai.api")
        assert "fastapi" not in path.read_text(encoding="utf-8").lower()

    for path in Path("src/document_digitization_ai").rglob("*.py"):
        if "api\\http" in str(path) or "api/http" in str(path):
            continue
        assert not _imports_module(path, "fastapi")
        assert not _imports_module(path, "starlette")

    for path in route_files:
        source = path.read_text(encoding="utf-8")
        assert "LocalDocumentApplication" not in source
        assert "_session_factory" not in source
        assert "DocumentJobRepository" not in source
        assert "build_extraction_provider" not in source
        assert "build_media_staging_service" not in source
        imported_modules = _imported_module_names(path)
        assert not any(
            imported_module.startswith("document_digitization_ai.db")
            or imported_module.startswith("document_digitization_ai.providers")
            or imported_module.startswith("document_digitization_ai.media")
            or imported_module.startswith(
                "document_digitization_ai.services.extraction_workflow"
            )
            or imported_module.startswith("document_digitization_ai.storage")
            for imported_module in imported_modules
        )

    web_path = Path("src/document_digitization_ai/web")
    assert web_path.exists()
    assert (web_path / "static" / "index.html").exists()
    for path in web_path.rglob("*.py"):
        assert not _imports_module(path, "fastapi")
        assert not _imports_module(path, "starlette")
        assert not _imports_module(path, "document_digitization_ai.api")
    assert not Path("src/document_digitization_ai/templates").exists()
    assert not Path("src/document_digitization_ai/static").exists()


class FakeDocumentFacade:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.submitted_file: dict[str, object] | None = None
        self.submit_response = SubmitDocumentResult(
            accepted=True,
            job_id="job-001",
            status="result_ready",
            result_available=True,
        )
        self.history_response = JobHistoryView(
            jobs=(
                JobSummary(
                    job_id="job-001",
                    status="result_ready",
                    result_available=True,
                    document_type="plain_text",
                    warning_count=0,
                    table_count=0,
                    field_count=1,
                ),
            ),
            limit=50,
            offset=0,
            total=1,
        )
        self.status_response = JobStatusView(
            job_id="job-001",
            status="result_ready",
            result_available=True,
        )
        artifact = ArtifactReference(
            kind="markdown_export",
            relative_path="jobs/job-001/exports/result.md",
            exists=True,
            content_type="text/markdown; charset=utf-8",
            size_bytes=9,
        )
        self.detail_response = JobDetailView(
            job_id="job-001",
            summary=self.history_response.jobs[0],
            status=self.status_response,
            attempts=(
                AttemptSummary(
                    attempt_id="attempt-001",
                    attempt_number=1,
                    status="succeeded",
                    provider_name="fake",
                    model_name="fake-model-v0",
                ),
            ),
            result_artifacts=(artifact,),
            metadata={"source_image_size_bytes": 128},
        )
        self.result_response = ExtractionResultView(
            job_id="job-001",
            result_available=True,
            result={"raw_text": {"text": "Deterministic text."}},
        )
        self.markdown_read_response = MarkdownExportView(
            job_id="job-001",
            result_available=True,
            markdown="# Result\n",
        )
        self.markdown_export_response = MarkdownExportView(
            job_id="job-001",
            result_available=True,
            markdown="# Result\n",
            artifact=artifact,
        )
        self.artifacts_response = ArtifactListView(
            job_id="job-001",
            artifacts=(artifact,),
        )
        self.raise_on_status: Exception | None = None

    async def submit_document_file(
        self,
        filename: str,
        content_type: str,
        data: bytes | bytearray | memoryview,
        **_kwargs: object,
    ) -> SubmitDocumentResult:
        self.calls.append(("submit_document_file", filename, content_type, bytes(data)))
        self.submitted_file = {
            "filename": filename,
            "content_type": content_type,
            "data": bytes(data),
        }
        if "/" in filename or "\\" in filename or ":" in filename:
            return SubmitDocumentResult(
                accepted=False,
                job_id=None,
                status=None,
                result_available=False,
                error=_error("invalid_input", "Submitted filename is invalid."),
            )
        return self.submit_response

    async def list_jobs(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        status: str | None = None,
    ) -> JobHistoryView:
        self.calls.append(("list_jobs", limit, offset, status))
        return self.history_response

    async def get_job_detail(self, job_id: str) -> JobDetailView:
        self.calls.append(("get_job_detail", job_id))
        return self.detail_response

    async def get_job_status(self, job_id: str) -> JobStatusView:
        self.calls.append(("get_job_status", job_id))
        if self.raise_on_status is not None:
            raise self.raise_on_status
        return self.status_response

    async def get_extraction_result(self, job_id: str) -> ExtractionResultView:
        self.calls.append(("get_extraction_result", job_id))
        return self.result_response

    async def get_result_markdown(
        self,
        job_id: str,
        *,
        write_artifact: bool = False,
    ) -> MarkdownExportView:
        self.calls.append(("get_result_markdown", job_id, write_artifact))
        if write_artifact:
            return self.markdown_export_response
        return self.markdown_read_response

    async def get_job_artifacts(self, job_id: str) -> ArtifactListView:
        self.calls.append(("get_job_artifacts", job_id))
        return self.artifacts_response


def _client(
    tmp_path: Path,
    facade: FakeDocumentFacade,
    *,
    max_upload_size_bytes: int = 1024,
) -> TestClient:
    app = create_app(
        settings=_app_settings(
            tmp_path,
            max_upload_size_bytes=max_upload_size_bytes,
        ),
        facade=cast(DocumentProcessingFacade, facade),
    )
    return TestClient(app)


def _app_settings(
    tmp_path: Path,
    *,
    max_upload_size_bytes: int = 1024,
) -> AppSettings:
    kwargs = cast(
        dict[str, Any],
        {
            "_env_file": None,
            "database_url": f"sqlite+aiosqlite:///{tmp_path / 'app.db'}",
            "llm_model": "openai/test-vision",
            "storage_data_dir": tmp_path / "data",
            "storage_uploads_dir": tmp_path / "data" / "uploads",
            "storage_results_dir": tmp_path / "data" / "results",
            "image_diagnostics_max_file_size_bytes": max_upload_size_bytes,
            "image_diagnostics_hard_min_width_px": 32,
            "image_diagnostics_hard_min_height_px": 32,
        },
    )
    return AppSettings(**kwargs)


def _error(error_type: str, error_message: str) -> BackendErrorView:
    return BackendErrorView(error_type=error_type, error_message=error_message)


def _imports_module(path: Path, expected_module: str) -> bool:
    return any(
        imported_module == expected_module
        or imported_module.startswith(f"{expected_module}.")
        for imported_module in _imported_module_names(path)
    )


def _imported_module_names(path: Path) -> tuple[str, ...]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)
    return tuple(imported_modules)
