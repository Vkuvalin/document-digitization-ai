from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class JobStatus(StrEnum):
    CREATED = "CREATED"
    IMAGE_UPLOADED = "IMAGE_UPLOADED"
    IMAGE_DIAGNOSTICS_READY = "IMAGE_DIAGNOSTICS_READY"
    MEDIA_STAGED = "MEDIA_STAGED"
    EXTRACTION_RUNNING = "EXTRACTION_RUNNING"
    EXTRACTION_SUCCEEDED = "EXTRACTION_SUCCEEDED"
    VALIDATION_SUCCEEDED = "VALIDATION_SUCCEEDED"
    VALIDATION_PARTIAL = "VALIDATION_PARTIAL"
    RESULT_READY = "RESULT_READY"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


BASIC_HAPPY_PATH_JOB_STATUSES: tuple[JobStatus, ...] = (
    JobStatus.CREATED,
    JobStatus.IMAGE_UPLOADED,
    JobStatus.IMAGE_DIAGNOSTICS_READY,
    JobStatus.MEDIA_STAGED,
    JobStatus.EXTRACTION_RUNNING,
    JobStatus.EXTRACTION_SUCCEEDED,
    JobStatus.VALIDATION_SUCCEEDED,
    JobStatus.RESULT_READY,
)

PARTIAL_VALIDATION_JOB_STATUSES: tuple[JobStatus, ...] = (
    JobStatus.CREATED,
    JobStatus.IMAGE_UPLOADED,
    JobStatus.IMAGE_DIAGNOSTICS_READY,
    JobStatus.MEDIA_STAGED,
    JobStatus.EXTRACTION_RUNNING,
    JobStatus.EXTRACTION_SUCCEEDED,
    JobStatus.VALIDATION_PARTIAL,
    JobStatus.RESULT_READY,
)

TERMINAL_JOB_STATUSES: frozenset[JobStatus] = frozenset(
    {
        JobStatus.FAILED,
        JobStatus.CANCELLED,
    }
)

ALLOWED_JOB_STATUS_TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = {
    JobStatus.CREATED: frozenset(
        {
            JobStatus.IMAGE_UPLOADED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.IMAGE_UPLOADED: frozenset(
        {
            JobStatus.IMAGE_DIAGNOSTICS_READY,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.IMAGE_DIAGNOSTICS_READY: frozenset(
        {
            JobStatus.MEDIA_STAGED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.MEDIA_STAGED: frozenset(
        {
            JobStatus.EXTRACTION_RUNNING,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.EXTRACTION_RUNNING: frozenset(
        {
            JobStatus.EXTRACTION_SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.EXTRACTION_SUCCEEDED: frozenset(
        {
            JobStatus.VALIDATION_SUCCEEDED,
            JobStatus.VALIDATION_PARTIAL,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.VALIDATION_SUCCEEDED: frozenset(
        {
            JobStatus.RESULT_READY,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.VALIDATION_PARTIAL: frozenset(
        {
            JobStatus.RESULT_READY,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    ),
    JobStatus.RESULT_READY: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


def can_transition_job_status(current: JobStatus, next_status: JobStatus) -> bool:
    return next_status in ALLOWED_JOB_STATUS_TRANSITIONS[current]


class DocumentModeHint(StrEnum):
    AUTO = "auto"
    FORM = "form"
    TABLE = "table"
    FREE_HANDWRITTEN_TEXT = "free_handwritten_text"
    MIXED_DOCUMENT = "mixed_document"
    PLAIN_TEXT = "plain_text"


class DetectedDocumentType(StrEnum):
    UNKNOWN = "unknown"
    PLAIN_TEXT = "plain_text"
    FORM = "form"
    TABLE = "table"
    MIXED_DOCUMENT = "mixed_document"
    FREE_HANDWRITTEN_TEXT = "free_handwritten_text"
    LABEL_OR_PLATE = "label_or_plate"
    OTHER = "other"


class FieldSource(StrEnum):
    DETECTED = "detected"
    INFERRED = "inferred"
    TEMPLATE = "template"
    USER_HINT = "user_hint"
    UNKNOWN = "unknown"


class BlockType(StrEnum):
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    FIELD_GROUP = "field_group"
    SIGNATURE = "signature"
    UNKNOWN = "unknown"


class WarningSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class WarningCode(StrEnum):
    INVALID_IMAGE = "invalid_image"
    UNSUPPORTED_FORMAT = "unsupported_format"
    TOO_LARGE = "too_large"
    TOO_SMALL = "too_small"
    LOW_RESOLUTION = "low_resolution"
    LOW_QUALITY_IMAGE = "low_quality_image"
    BLURRED_IMAGE = "blurred_image"
    LOW_CONTRAST = "low_contrast"
    TOO_DARK = "too_dark"
    TOO_BRIGHT = "too_bright"
    POSSIBLE_ROTATION = "possible_rotation"
    POSSIBLE_SKEW = "possible_skew"
    EXIF_ORIENTATION_PRESENT = "exif_orientation_present"
    UNREADABLE_TEXT = "unreadable_text"
    AMBIGUOUS_FIELD = "ambiguous_field"
    AMBIGUOUS_TABLE = "ambiguous_table"
    MODE_MISMATCH = "mode_mismatch"
    PARTIAL_EXTRACTION = "partial_extraction"
    PROVIDER_ERROR = "provider_error"
    VALIDATION_ERROR = "validation_error"
    MISSING_EXPECTED_FIELD = "missing_expected_field"
    UNMATCHED_TEXT = "unmatched_text"


class ImageOrientation(StrEnum):
    LANDSCAPE = "landscape"
    PORTRAIT = "portrait"
    SQUARE = "square"
    UNKNOWN = "unknown"


class ExtractionGoal(StrEnum):
    EXTRACT_TEXT_AND_STRUCTURE = "extract_text_and_structure"


class ExpectedResultSection(StrEnum):
    DOCUMENT = "document"
    IMAGE_DIAGNOSTICS = "image_diagnostics"
    RAW_TEXT = "raw_text"
    FIELDS = "fields"
    TABLES = "tables"
    BLOCKS = "blocks"
    WARNINGS = "warnings"
    METADATA = "metadata"


class ProviderConstraint(StrEnum):
    DO_NOT_INVENT_UNREADABLE_TEXT = "do_not_invent_unreadable_text"
    MARK_UNCERTAIN_VALUES_EXPLICITLY = "mark_uncertain_values_explicitly"
    PRESERVE_VISIBLE_TABLE_STRUCTURE = "preserve_visible_table_structure"
    RETURN_MODE_MISMATCH_WARNING = "return_mode_mismatch_warning"
    RETURN_PARTIAL_RESULT_WITH_WARNINGS = "return_partial_result_with_warnings"
    DO_NOT_SILENTLY_CLEAN_UP_HANDWRITING = "do_not_silently_clean_up_handwriting"
    RETURN_VALID_STRUCTURED_OUTPUT = "return_valid_structured_output"
