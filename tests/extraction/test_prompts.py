from pathlib import Path

import pytest

from document_digitization_ai.contracts import (
    DEFAULT_EXPECTED_RESULT_SHAPE,
    DocumentModeHint,
    JobStatus,
)
from document_digitization_ai.core import ProviderSchemaMode
from document_digitization_ai.extraction import (
    ExtractionPromptError,
    ExtractionPromptPackage,
    build_extraction_prompt_package,
)
from document_digitization_ai.providers import (
    ProviderDiagnosticWarning,
    ProviderDiagnosticsSummary,
    ProviderExtractionRuntimeSettings,
    ProviderImageInput,
    ProviderInputContext,
)


def test_prompt_package_builds_deterministically(tmp_path: Path) -> None:
    context = _provider_context(tmp_path, DocumentModeHint.AUTO)

    first = build_extraction_prompt_package(context)
    second = build_extraction_prompt_package(context)

    assert first == second
    assert first.to_dict() == second.to_dict()


def test_prompt_includes_output_requirements_aligned_with_result_v0(
    tmp_path: Path,
) -> None:
    package = build_extraction_prompt_package(
        _provider_context(tmp_path, DocumentModeHint.FORM)
    )
    output_text = "\n".join(package.output_requirements)

    assert "extraction_result_v0" in output_text
    for section in DEFAULT_EXPECTED_RESULT_SHAPE:
        assert section.value in output_text


@pytest.mark.parametrize(
    ("mode_hint", "expected_fragment"),
    [
        (DocumentModeHint.AUTO, "Infer the visible document structure"),
        (DocumentModeHint.FORM, "label/value pairs"),
        (DocumentModeHint.TABLE, "tabular structure"),
        (DocumentModeHint.FREE_HANDWRITTEN_TEXT, "handwritten free text"),
        (DocumentModeHint.MIXED_DOCUMENT, "fields, tables, and free-text blocks"),
        (DocumentModeHint.PLAIN_TEXT, "raw text and ordered text blocks"),
    ],
)
def test_prompt_handles_each_document_mode_hint(
    tmp_path: Path,
    mode_hint: DocumentModeHint,
    expected_fragment: str,
) -> None:
    package = build_extraction_prompt_package(_provider_context(tmp_path, mode_hint))

    assert expected_fragment in package.document_mode_guidance
    assert "guidance" in package.document_mode_guidance or mode_hint is not DocumentModeHint.AUTO


def test_prompt_uses_diagnostics_warnings_as_guidance_only(tmp_path: Path) -> None:
    package = build_extraction_prompt_package(
        _provider_context(
            tmp_path,
            DocumentModeHint.AUTO,
            warnings=(
                ProviderDiagnosticWarning(
                    code="low_resolution",
                    message="Image resolution is low.",
                    severity="warning",
                ),
                ProviderDiagnosticWarning(
                    code="low_contrast",
                    message="Image contrast is low.",
                    severity="warning",
                ),
                ProviderDiagnosticWarning(
                    code="too_dark",
                    message="Image is dark.",
                    severity="warning",
                ),
                ProviderDiagnosticWarning(
                    code="too_bright",
                    message="Image is bright.",
                    severity="warning",
                ),
                ProviderDiagnosticWarning(
                    code="exif_orientation_present",
                    message="EXIF orientation is present.",
                    severity="info",
                ),
            ),
        )
    )
    guidance = "\n".join(package.diagnostics_guidance)

    assert "low resolution" in guidance
    assert "low contrast" in guidance
    assert "dark image" in guidance
    assert "bright image" in guidance
    assert "EXIF orientation" in guidance
    assert "not as extraction results" in guidance


def test_prompt_does_not_include_local_filesystem_path(tmp_path: Path) -> None:
    context = _provider_context(tmp_path, DocumentModeHint.AUTO)
    package = build_extraction_prompt_package(context)
    payload_text = str(package.to_dict())

    assert str(context.image.local_path) not in payload_text


def test_prompt_package_does_not_require_provider_or_media_secrets(
    tmp_path: Path,
) -> None:
    package = build_extraction_prompt_package(
        _provider_context(tmp_path, DocumentModeHint.PLAIN_TEXT)
    )

    assert package.metadata["document_mode_hint"] == DocumentModeHint.PLAIN_TEXT.value


def test_prompt_builder_rejects_invalid_context() -> None:
    with pytest.raises(ExtractionPromptError, match="context"):
        build_extraction_prompt_package(object())  # type: ignore[arg-type]


def test_prompt_package_rejects_non_json_metadata() -> None:
    with pytest.raises(ValueError, match="metadata"):
        ExtractionPromptPackage(
            system_instruction="system",
            task_instruction="task",
            document_mode_guidance="mode",
            diagnostics_guidance=("diagnostics",),
            output_requirements=("output",),
            uncertainty_guidance=("uncertainty",),
            metadata={"bad": {object()}},
        )

    with pytest.raises(ValueError, match="metadata"):
        ExtractionPromptPackage(
            system_instruction="system",
            task_instruction="task",
            document_mode_guidance="mode",
            diagnostics_guidance=("diagnostics",),
            output_requirements=("output",),
            uncertainty_guidance=("uncertainty",),
            metadata={"bad": float("nan")},
        )


def _provider_context(
    tmp_path: Path,
    mode_hint: DocumentModeHint,
    *,
    warnings: tuple[ProviderDiagnosticWarning, ...] = (),
) -> ProviderInputContext:
    image_path = tmp_path / "original.jpg"
    image_path.write_bytes(b"fake-image-bytes")
    return ProviderInputContext(
        job_id="job-001",
        job_status=JobStatus.IMAGE_DIAGNOSTICS_READY,
        document_mode_hint=mode_hint,
        image=ProviderImageInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            width=1000,
            height=800,
        ),
        diagnostics=ProviderDiagnosticsSummary(
            diagnostics_present=True,
            warnings=warnings,
            is_low_resolution=False,
        ),
        extraction=ProviderExtractionRuntimeSettings(
            model="openai/test-vision",
            temperature=0.1,
            timeout_seconds=60,
            max_retries=2,
            provider_schema_mode=ProviderSchemaMode.COMPACT,
            structured_outputs_enabled=True,
            structured_outputs_require_parameters=False,
        ),
    )
