from pathlib import Path
from typing import cast

import pytest

from document_digitization_ai.contracts import (
    DEFAULT_EXPECTED_RESULT_SHAPE,
    DocumentModeHint,
    ExpectedResultSection,
    JobStatus,
)
from document_digitization_ai.core import ProviderSchemaMode
from document_digitization_ai.extraction import (
    ExtractionProviderRequest,
    ExtractionSchemaPackage,
    build_extraction_prompt_package,
    build_extraction_schema_package,
)
from document_digitization_ai.providers import (
    ProviderDiagnosticsSummary,
    ProviderExtractionRuntimeSettings,
    ProviderImageInput,
    ProviderInputContext,
)


def test_schema_package_builds_deterministically_in_compact_mode(
    tmp_path: Path,
) -> None:
    context = _provider_context(tmp_path, ProviderSchemaMode.COMPACT)

    first = build_extraction_schema_package(context)
    second = build_extraction_schema_package(context)

    assert first == second
    assert first.schema_mode is ProviderSchemaMode.COMPACT
    assert first.schema_payload["schema_detail"] == "compact"


def test_schema_package_builds_deterministically_in_full_mode(
    tmp_path: Path,
) -> None:
    context = _provider_context(tmp_path, ProviderSchemaMode.FULL)

    first = build_extraction_schema_package(context)
    second = build_extraction_schema_package(context)

    assert first == second
    assert first.schema_mode is ProviderSchemaMode.FULL
    assert first.schema_payload["schema_detail"] == "full"


def test_compact_and_full_schema_modes_share_target_contract_but_differ_in_detail(
    tmp_path: Path,
) -> None:
    compact = build_extraction_schema_package(
        _provider_context(tmp_path, ProviderSchemaMode.COMPACT)
    )
    full = build_extraction_schema_package(
        _provider_context(tmp_path, ProviderSchemaMode.FULL)
    )

    assert compact.target_schema_version == full.target_schema_version
    assert compact.required_sections == full.required_sections
    assert compact.schema_payload != full.schema_payload


def test_schema_package_includes_required_result_sections(tmp_path: Path) -> None:
    package = build_extraction_schema_package(
        _provider_context(tmp_path, ProviderSchemaMode.FULL)
    )
    payload = package.to_dict()
    required_sections = cast(list[str], payload["required_sections"])

    assert package.required_sections == DEFAULT_EXPECTED_RESULT_SHAPE
    for section in (
        ExpectedResultSection.FIELDS,
        ExpectedResultSection.TABLES,
        ExpectedResultSection.BLOCKS,
        ExpectedResultSection.WARNINGS,
        ExpectedResultSection.METADATA,
    ):
        assert section.value in required_sections


def test_schema_package_marks_provider_output_untrusted(tmp_path: Path) -> None:
    compact = build_extraction_schema_package(
        _provider_context(tmp_path, ProviderSchemaMode.COMPACT)
    )
    full = build_extraction_schema_package(
        _provider_context(tmp_path, ProviderSchemaMode.FULL)
    )

    for package in (compact, full):
        assert package.schema_payload["provider_output_is_untrusted"] is True
        assert package.schema_payload["validation_owner"] == "backend"


def test_full_schema_package_includes_explicit_property_descriptions(
    tmp_path: Path,
) -> None:
    package = build_extraction_schema_package(
        _provider_context(tmp_path, ProviderSchemaMode.FULL)
    )

    assert "properties" in package.schema_payload


def test_provider_request_can_carry_prompt_and_schema_packages(
    tmp_path: Path,
) -> None:
    context = _provider_context(tmp_path, ProviderSchemaMode.COMPACT)
    prompt_package = build_extraction_prompt_package(context)
    schema_package = build_extraction_schema_package(context)

    request = ExtractionProviderRequest(
        correlation_id=context.job_id,
        context=context,
        prompt_package=prompt_package,
        schema_package=schema_package,
    )
    payload = request.to_dict()

    assert payload["prompt_package"] == prompt_package.to_dict()
    assert payload["schema_package"] == schema_package.to_dict()


def test_schema_package_does_not_require_provider_or_media_secrets(
    tmp_path: Path,
) -> None:
    package = build_extraction_schema_package(
        _provider_context(tmp_path, ProviderSchemaMode.COMPACT)
    )

    assert package.target_schema_version == "extraction_result_v0"


def test_schema_package_rejects_non_json_schema_payload() -> None:
    with pytest.raises(ValueError, match="schema_payload"):
        ExtractionSchemaPackage(
            schema_mode=ProviderSchemaMode.COMPACT,
            target_schema_version="extraction_result_v0",
            required_sections=DEFAULT_EXPECTED_RESULT_SHAPE,
            schema_payload={"bad": {object()}},
        )

    with pytest.raises(ValueError, match="schema_payload"):
        ExtractionSchemaPackage(
            schema_mode=ProviderSchemaMode.COMPACT,
            target_schema_version="extraction_result_v0",
            required_sections=DEFAULT_EXPECTED_RESULT_SHAPE,
            schema_payload={"bad": float("inf")},
        )


def _provider_context(
    tmp_path: Path,
    schema_mode: ProviderSchemaMode,
) -> ProviderInputContext:
    image_path = tmp_path / "original.jpg"
    image_path.write_bytes(b"fake-image-bytes")
    return ProviderInputContext(
        job_id="job-001",
        job_status=JobStatus.IMAGE_DIAGNOSTICS_READY,
        document_mode_hint=DocumentModeHint.AUTO,
        image=ProviderImageInput(
            local_path=image_path,
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            width=1000,
            height=800,
        ),
        diagnostics=ProviderDiagnosticsSummary(
            diagnostics_present=True,
            warnings=(),
            is_low_resolution=False,
        ),
        extraction=ProviderExtractionRuntimeSettings(
            model="openai/test-vision",
            temperature=0.1,
            timeout_seconds=60,
            max_retries=2,
            provider_schema_mode=schema_mode,
            structured_outputs_enabled=True,
            structured_outputs_require_parameters=False,
        ),
    )
