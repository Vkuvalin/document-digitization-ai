from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from document_digitization_ai.application import (
    ArtifactListView,
    ArtifactReference,
    AttemptSummary,
    BackendErrorView,
    DeleteJobView,
    ExtractionResultView,
    JobDetailView,
    JobHistoryView,
    JobStatusView,
    JobSummary,
    MarkdownExportView,
    SubmitDocumentResult,
)


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ApiErrorResponse(ApiModel):
    error_type: str
    error_message: str

    @classmethod
    def from_view(cls, view: BackendErrorView) -> ApiErrorResponse:
        return cls.model_validate(view.to_dict())


class ArtifactReferenceResponse(ApiModel):
    kind: str
    relative_path: str
    exists: bool
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None

    @classmethod
    def from_view(cls, view: ArtifactReference) -> ArtifactReferenceResponse:
        return cls.model_validate(view.to_dict())


class SubmitDocumentResponse(ApiModel):
    accepted: bool
    job_id: str | None
    status: str | None
    result_available: bool
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: SubmitDocumentResult) -> SubmitDocumentResponse:
        return cls.model_validate(view.to_dict())


class DeleteJobResponse(ApiModel):
    job_id: str
    deleted: bool
    artifacts_deleted: int
    unsafe_artifacts_skipped: int
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: DeleteJobView) -> DeleteJobResponse:
        return cls.model_validate(view.to_dict())


class JobStatusResponse(ApiModel):
    job_id: str
    status: str | None
    result_available: bool
    latest_attempt_status: str | None = None
    validation_status: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    completed_at: str | None = None
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: JobStatusView) -> JobStatusResponse:
        return cls.model_validate(view.to_dict())


class JobSummaryResponse(ApiModel):
    job_id: str
    status: str
    result_available: bool
    document_type: str | None = None
    warning_count: int | None = None
    table_count: int | None = None
    field_count: int | None = None
    created_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_view(cls, view: JobSummary) -> JobSummaryResponse:
        return cls.model_validate(view.to_dict())


class JobHistoryResponse(ApiModel):
    jobs: list[JobSummaryResponse]
    limit: int
    offset: int
    total: int
    status_filter: str | None = None
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: JobHistoryView) -> JobHistoryResponse:
        return cls.model_validate(view.to_dict())


class AttemptSummaryResponse(ApiModel):
    attempt_id: str
    attempt_number: int
    status: str
    provider_name: str
    model_name: str
    validation_outcome: str | None = None
    validation_issue_count: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    retryable: bool | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_ms: int | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def from_view(cls, view: AttemptSummary) -> AttemptSummaryResponse:
        return cls.model_validate(view.to_dict())


class JobDetailResponse(ApiModel):
    job_id: str
    summary: JobSummaryResponse | None
    status: JobStatusResponse | None
    attempts: list[AttemptSummaryResponse]
    input_artifacts: list[ArtifactReferenceResponse]
    result_artifacts: list[ArtifactReferenceResponse]
    export_artifacts: list[ArtifactReferenceResponse]
    metadata: dict[str, Any]
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: JobDetailView) -> JobDetailResponse:
        return cls.model_validate(view.to_dict())


class ExtractionResultResponse(ApiModel):
    job_id: str
    result_available: bool
    result: dict[str, Any] | None = None
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: ExtractionResultView) -> ExtractionResultResponse:
        return cls.model_validate(view.to_dict())


class MarkdownExportResponse(ApiModel):
    job_id: str
    result_available: bool
    markdown: str | None = None
    artifact: ArtifactReferenceResponse | None = None
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: MarkdownExportView) -> MarkdownExportResponse:
        return cls.model_validate(view.to_dict())


class ArtifactListResponse(ApiModel):
    job_id: str
    artifacts: list[ArtifactReferenceResponse]
    error: ApiErrorResponse | None = None

    @classmethod
    def from_view(cls, view: ArtifactListView) -> ArtifactListResponse:
        return cls.model_validate(view.to_dict())
