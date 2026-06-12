from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Enum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from document_digitization_ai.contracts import DocumentModeHint, JobStatus
from document_digitization_ai.db.base import Base


def utc_now() -> datetime:
    return datetime.now(UTC)


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
