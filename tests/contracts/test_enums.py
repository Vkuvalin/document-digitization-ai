from itertools import pairwise

from document_digitization_ai.contracts import (
    BASIC_HAPPY_PATH_JOB_STATUSES,
    PARTIAL_VALIDATION_JOB_STATUSES,
    TERMINAL_JOB_STATUSES,
    DocumentModeHint,
    JobStatus,
    can_transition_job_status,
)


def test_job_status_values_match_approved_lifecycle() -> None:
    assert [status.value for status in JobStatus] == [
        "CREATED",
        "IMAGE_UPLOADED",
        "IMAGE_DIAGNOSTICS_READY",
        "MEDIA_STAGED",
        "EXTRACTION_RUNNING",
        "EXTRACTION_SUCCEEDED",
        "VALIDATION_SUCCEEDED",
        "VALIDATION_PARTIAL",
        "RESULT_READY",
        "FAILED",
        "CANCELLED",
    ]


def test_document_mode_hint_values_match_approved_initial_hints() -> None:
    assert [hint.value for hint in DocumentModeHint] == [
        "auto",
        "form",
        "table",
        "free_handwritten_text",
        "mixed_document",
        "plain_text",
    ]


def test_job_status_transitions_allow_success_and_partial_paths() -> None:
    for current, next_status in pairwise(BASIC_HAPPY_PATH_JOB_STATUSES):
        assert can_transition_job_status(current, next_status)

    for current, next_status in pairwise(PARTIAL_VALIDATION_JOB_STATUSES):
        assert can_transition_job_status(current, next_status)


def test_job_status_transitions_reject_skips_and_terminal_moves() -> None:
    assert not can_transition_job_status(JobStatus.CREATED, JobStatus.RESULT_READY)
    assert not can_transition_job_status(JobStatus.RESULT_READY, JobStatus.FAILED)
    assert can_transition_job_status(
        JobStatus.IMAGE_DIAGNOSTICS_READY,
        JobStatus.EXTRACTION_RUNNING,
    )


def test_terminal_job_statuses_match_approved_terminal_states() -> None:
    assert TERMINAL_JOB_STATUSES == frozenset(
        {
            JobStatus.RESULT_READY,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }
    )
