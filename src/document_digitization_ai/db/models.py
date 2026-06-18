from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.schema import UniqueConstraint

from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


class ExtractionAttemptStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class DocumentJob(Base):
    __tablename__ = "document_jobs"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    status: Mapped[JobStatus] = mapped_column(
        Enum(
            JobStatus,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            validate_strings=True,
        ),
        nullable=False,
        default=JobStatus.CREATED,
    )
    user_mode_hint: Mapped[DocumentModeHint] = mapped_column(
        Enum(
            DocumentModeHint,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            validate_strings=True,
        ),
        nullable=False,
    )
    source_image_path: Mapped[str | None] = mapped_column(Text)
    source_image_mime_type: Mapped[str | None] = mapped_column(String(255))
    source_image_size_bytes: Mapped[int | None] = mapped_column(Integer)
    image_diagnostics_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    extraction_result_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    validation_status: Mapped[str | None] = mapped_column(String(64))
    completed_attempt_id: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    extraction_attempts: Mapped[list[ExtractionAttempt]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
    )


class ExtractionAttempt(Base):
    __tablename__ = "extraction_attempts"
    __table_args__ = (
        UniqueConstraint(
            "job_id",
            "attempt_number",
            name="uq_extraction_attempts_job_id_attempt_number",
        ),
    )

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    job_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("document_jobs.id"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ExtractionAttemptStatus] = mapped_column(
        Enum(
            ExtractionAttemptStatus,
            values_callable=lambda enum_type: [item.value for item in enum_type],
            validate_strings=True,
        ),
        nullable=False,
        default=ExtractionAttemptStatus.PENDING,
    )

    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(128), nullable=False)
    schema_mode: Mapped[str] = mapped_column(String(64), nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[int | None] = mapped_column(Integer)

    request_metadata_json: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    response_metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    raw_response_artifact_path: Mapped[str | None] = mapped_column(Text)
    sanitized_response_artifact_path: Mapped[str | None] = mapped_column(Text)
    raw_response_size_bytes: Mapped[int | None] = mapped_column(Integer)
    sanitized_response_size_bytes: Mapped[int | None] = mapped_column(Integer)

    validation_outcome: Mapped[str | None] = mapped_column(String(64))
    validation_issue_count: Mapped[int | None] = mapped_column(Integer)

    error_type: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    retryable: Mapped[bool | None] = mapped_column(Boolean)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )

    job: Mapped[DocumentJob] = relationship(back_populates="extraction_attempts")
