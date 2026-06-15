from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from document_digitization_ai.contracts import (
    DocumentModeHint,
    ExtractionResult,
    ImageDiagnostics,
    JobStatus,
)
from document_digitization_ai.core import (
    AppSettings,
    ExtractionProviderName,
    MediaStagingBackend,
    SettingsError,
)
from document_digitization_ai.diagnostics import ImageDiagnosticsError
from document_digitization_ai.diagnostics import collect_image_diagnostics
from document_digitization_ai.extraction import (
    ExtractionProviderError,
    ExtractionProviderRequest,
    ExtractionValidationError,
    OpenRouterExtractionProvider,
    build_extraction_prompt_package,
    build_extraction_provider,
    build_extraction_schema_package,
    validate_provider_output,
)
from document_digitization_ai.media import (
    MediaStagingConfigurationError,
    MediaStagingError,
    MediaStagingInput,
    MediaStagingResult,
    StagedMediaReferenceKind,
    build_media_staging_service,
)
from document_digitization_ai.providers import (
    ProviderDiagnosticWarning,
    ProviderDiagnosticsSummary,
    ProviderExtractionRuntimeSettings,
    ProviderImageInput,
    ProviderInputContext,
    attach_staged_media,
)


EXIT_UNEXPECTED = 1
EXIT_PRECONDITION = 2
EXIT_MEDIA_STAGING = 3
EXIT_PROVIDER = 4
EXIT_VALIDATION = 5

RUN_GATE_ENV = "RUN_REAL_PROVIDER_SMOKE"
RUN_GATE_VALUE = "1"
RUN_GATE_MESSAGE = "Set RUN_REAL_PROVIDER_SMOKE=1 to run real provider smoke."

_SENSITIVE_KEY_PARTS = (
    "api_key",
    "authorization",
    "bearer",
    "cleanup",
    "delete_url",
    "private",
    "secret",
    "token",
)
_URL_KEY_PARTS = ("url", "uri")
_REDACTED = "<redacted>"
_REDACTED_URL = "<redacted-url>"


class ManualProviderSmokeError(RuntimeError):
    """Base error for manual smoke control-flow failures."""


class ManualProviderSmokePreconditionError(ManualProviderSmokeError):
    """Raised when env, settings, or local image preconditions fail."""


@dataclass(frozen=True, slots=True)
class SmokeCliArgs:
    image: Path
    print_result: bool
    verbose: bool
    json_summary: bool


@dataclass(frozen=True, slots=True)
class SmokeOutput:
    summary: Mapping[str, object]
    sanitized_result: object | None = None


def parse_cli_args(argv: Sequence[str] | None = None) -> SmokeCliArgs:
    parser = argparse.ArgumentParser(
        description="Manual env-gated real ImgBB/OpenRouter smoke script.",
    )
    parser.add_argument(
        "--image",
        required=True,
        type=Path,
        help="Path to a local image file for manual smoke.",
    )
    parser.add_argument(
        "--print-result",
        action="store_true",
        help="Print sanitized structured validation result.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Include additional non-sensitive summary fields.",
    )
    parser.add_argument(
        "--json-summary",
        action="store_true",
        help="Print the safe summary as JSON.",
    )
    namespace = parser.parse_args(argv)
    return SmokeCliArgs(
        image=cast(Path, namespace.image),
        print_result=cast(bool, namespace.print_result),
        verbose=cast(bool, namespace.verbose),
        json_summary=cast(bool, namespace.json_summary),
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    dotenv_path: Path | None = Path(".env"),
) -> int:
    args = parse_cli_args(argv)
    runtime_env = _load_smoke_env_gate(env=env, dotenv_path=dotenv_path)
    if runtime_env.get(RUN_GATE_ENV) != RUN_GATE_VALUE:
        print(RUN_GATE_MESSAGE, file=sys.stderr)
        return EXIT_PRECONDITION

    try:
        image_path = _require_local_image_file(args.image)
        settings = _load_and_validate_settings()
        output = asyncio.run(_run_smoke(image_path, settings, args))
        _print_output(output, json_summary=args.json_summary)
        return 0
    except ManualProviderSmokePreconditionError as exc:
        print(f"Precondition failed: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION
    except MediaStagingConfigurationError as exc:
        print(f"Precondition failed: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION
    except ImageDiagnosticsError as exc:
        print(f"Precondition failed: {exc}", file=sys.stderr)
        return EXIT_PRECONDITION
    except MediaStagingError as exc:
        print(f"Media staging failed: {exc}", file=sys.stderr)
        return EXIT_MEDIA_STAGING
    except ExtractionProviderError as exc:
        print(f"Provider call failed: {exc}", file=sys.stderr)
        return EXIT_PROVIDER
    except ExtractionValidationError as exc:
        print(f"Validation failed: {exc}", file=sys.stderr)
        return EXIT_VALIDATION
    except Exception as exc:
        print(f"Unexpected smoke failure: {exc}", file=sys.stderr)
        return EXIT_UNEXPECTED


async def _run_smoke(
    image_path: Path,
    settings: AppSettings,
    args: SmokeCliArgs,
) -> SmokeOutput:
    timings: dict[str, float] = {}

    diagnostics_start = time.perf_counter()
    image_diagnostics = collect_image_diagnostics(
        image_path,
        config=settings.image_diagnostics.to_diagnostics_config(),
    )
    timings["diagnostics_seconds"] = _elapsed_seconds(diagnostics_start)

    context = _build_manual_context(image_path, image_diagnostics, settings)

    staging_start = time.perf_counter()
    staging_service = build_media_staging_service(settings.media_staging)
    staging_result = await staging_service.stage(
        MediaStagingInput(
            local_path=image_path,
            mime_type=image_diagnostics.file.mime_type,
            file_size_bytes=image_diagnostics.file.file_size_bytes,
            sha256=image_diagnostics.file.sha256,
        )
    )
    _validate_staging_result(staging_result)
    timings["staging_seconds"] = _elapsed_seconds(staging_start)

    staged_context = attach_staged_media(context, staging_result.reference)
    prompt_package = build_extraction_prompt_package(staged_context)
    schema_package = build_extraction_schema_package(staged_context)
    request = ExtractionProviderRequest(
        correlation_id=staged_context.job_id,
        context=staged_context,
        staged_media=staging_result.reference,
        prompt_package=prompt_package,
        schema_package=schema_package,
    )

    provider = build_extraction_provider(
        settings.extraction,
        openrouter_settings=settings.openrouter,
    )
    if not isinstance(provider, OpenRouterExtractionProvider):
        msg = "EXTRACTION_PROVIDER=openrouter did not build OpenRouter provider"
        raise ManualProviderSmokePreconditionError(msg)

    provider_start = time.perf_counter()
    provider_response = await provider.extract(request)
    timings["provider_seconds"] = _elapsed_seconds(provider_start)

    validation_start = time.perf_counter()
    validation_result = validate_provider_output(
        provider_response,
        context=staged_context,
        image_diagnostics=image_diagnostics,
    )
    timings["validation_seconds"] = _elapsed_seconds(validation_start)

    extraction_result = validation_result.extraction_result
    summary = _build_safe_summary(
        provider_name=provider_response.provider_name,
        model_name=provider_response.model_name,
        finish_reason=provider_response.finish_reason,
        validation_outcome=validation_result.outcome.value,
        validation_issue_count=len(validation_result.validation_warnings),
        raw_text_length=len(extraction_result.raw_text.text),
        usable_content=_has_usable_content(extraction_result),
        staging_result=staging_result,
        diagnostics=image_diagnostics,
        timings=timings,
        verbose=args.verbose,
    )
    sanitized_result = (
        redact_for_output(extraction_result.to_dict())
        if args.print_result
        else None
    )
    return SmokeOutput(summary=summary, sanitized_result=sanitized_result)


def redact_for_output(
    value: object,
    *,
    extra_secrets: Sequence[str] = (),
) -> object:
    secrets = tuple(secret for secret in extra_secrets if secret)
    return _redact_value(value, key_path=(), extra_secrets=secrets)


def _load_smoke_env_gate(
    *,
    env: Mapping[str, str] | None = None,
    dotenv_path: Path | None = Path(".env"),
) -> dict[str, str]:
    merged_env: dict[str, str] = {}
    if dotenv_path is not None:
        merged_env.update(_read_dotenv_file(dotenv_path))
    runtime_env = os.environ if env is None else env
    merged_env.update(dict(runtime_env))
    return merged_env


def _read_dotenv_file(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.is_file():
        return {}
    values: dict[str, str] = {}
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped.removeprefix("export ").strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _strip_dotenv_quotes(value.strip())
    return values


def _strip_dotenv_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
        return value[1:-1]
    return value


def _load_and_validate_settings() -> AppSettings:
    try:
        settings = AppSettings()
    except Exception as exc:
        msg = f"settings could not be loaded: {exc}"
        raise ManualProviderSmokePreconditionError(msg) from exc

    if settings.media_staging.backend is not MediaStagingBackend.IMGBB:
        msg = "MEDIA_STAGING_BACKEND must be imgbb for real provider smoke"
        raise ManualProviderSmokePreconditionError(msg)
    if settings.extraction.provider_name is not ExtractionProviderName.OPENROUTER:
        msg = "EXTRACTION_PROVIDER must be openrouter for real provider smoke"
        raise ManualProviderSmokePreconditionError(msg)
    if not settings.extraction.structured_outputs_enabled:
        msg = "LLM_STRUCTURED_OUTPUTS_ENABLED must be true for OpenRouter smoke"
        raise ManualProviderSmokePreconditionError(msg)

    try:
        settings.media_staging.require_imgbb_api_key()
        settings.openrouter.require_api_key()
        settings.extraction.require_model_name()
    except SettingsError as exc:
        raise ManualProviderSmokePreconditionError(str(exc)) from exc

    return settings


def _require_local_image_file(image_path: Path) -> Path:
    path = image_path.expanduser()
    if not path.exists() or not path.is_file():
        msg = "Image path must point to an existing file."
        raise ManualProviderSmokePreconditionError(msg)
    return path


def _build_manual_context(
    image_path: Path,
    diagnostics: ImageDiagnostics,
    settings: AppSettings,
) -> ProviderInputContext:
    try:
        model_name = settings.extraction.require_model_name()
    except SettingsError as exc:
        raise ManualProviderSmokePreconditionError(str(exc)) from exc

    return ProviderInputContext(
        job_id="manual-provider-smoke",
        job_status=JobStatus.IMAGE_DIAGNOSTICS_READY,
        document_mode_hint=DocumentModeHint.AUTO,
        image=ProviderImageInput(
            local_path=image_path,
            mime_type=diagnostics.file.mime_type,
            file_size_bytes=diagnostics.file.file_size_bytes,
            width=diagnostics.image.width,
            height=diagnostics.image.height,
            sha256=diagnostics.file.sha256,
        ),
        diagnostics=ProviderDiagnosticsSummary(
            diagnostics_present=True,
            warnings=tuple(
                ProviderDiagnosticWarning(
                    code=warning.code.value,
                    message=warning.message,
                    severity=warning.severity.value,
                    target=warning.target,
                )
                for warning in diagnostics.warnings
            ),
            brightness=diagnostics.quality.brightness,
            contrast=diagnostics.quality.contrast,
            is_low_resolution=diagnostics.quality.is_low_resolution,
            is_low_contrast=diagnostics.quality.is_low_contrast,
            exif_orientation=diagnostics.image.exif_orientation,
            schema_version=_optional_str(diagnostics.metadata.get("schema_version")),
            diagnostics_version=_optional_str(
                diagnostics.metadata.get("diagnostics_version")
            ),
        ),
        extraction=ProviderExtractionRuntimeSettings(
            provider_name=settings.extraction.provider_name,
            model=model_name,
            temperature=settings.extraction.temperature,
            timeout_seconds=settings.extraction.timeout_seconds,
            max_retries=settings.extraction.max_retries,
            provider_schema_mode=settings.extraction.provider_schema_mode,
            structured_outputs_enabled=(
                settings.extraction.structured_outputs_enabled
            ),
            structured_outputs_require_parameters=(
                settings.extraction.structured_outputs_require_parameters
            ),
        ),
    )


def _validate_staging_result(staging_result: MediaStagingResult) -> None:
    if not staging_result.external_upload_performed:
        msg = "ImgBB smoke must perform external media upload"
        raise MediaStagingError(msg)
    if staging_result.reference.kind is not StagedMediaReferenceKind.PUBLIC_URL:
        msg = "ImgBB smoke must produce PUBLIC_URL staged media"
        raise MediaStagingError(msg)


def _build_safe_summary(
    *,
    provider_name: str,
    model_name: str,
    finish_reason: str | None,
    validation_outcome: str,
    validation_issue_count: int,
    raw_text_length: int,
    usable_content: bool,
    staging_result: MediaStagingResult,
    diagnostics: ImageDiagnostics,
    timings: Mapping[str, float],
    verbose: bool,
) -> dict[str, object]:
    summary: dict[str, object] = {
        "provider_name": provider_name,
        "model_name": model_name,
        "finish_reason": finish_reason,
        "validation_outcome": validation_outcome,
        "validation_issue_count": validation_issue_count,
        "raw_text_length": raw_text_length,
        "usable_content": usable_content,
        "external_upload_performed": staging_result.external_upload_performed,
        "staged_media_kind": staging_result.reference.kind.value,
        "durations": dict(timings),
    }
    if verbose:
        summary["diagnostics_warning_count"] = len(diagnostics.warnings)
        summary["diagnostics_warning_codes"] = [
            warning.code.value for warning in diagnostics.warnings
        ]
        summary["staging_warnings_count"] = len(staging_result.warnings)
    return summary


def _has_usable_content(result: ExtractionResult) -> bool:
    return bool(
        result.raw_text.text.strip()
        or result.fields
        or result.tables
        or result.blocks
    )


def _print_output(output: SmokeOutput, *, json_summary: bool) -> None:
    if json_summary:
        payload: dict[str, object] = {"summary": dict(output.summary)}
        if output.sanitized_result is not None:
            payload["sanitized_result"] = output.sanitized_result
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return

    print("Manual provider smoke summary")
    for key, value in output.summary.items():
        if isinstance(value, Mapping):
            print(f"{key}:")
            for nested_key, nested_value in value.items():
                print(f"  {nested_key}: {nested_value}")
        else:
            print(f"{key}: {value}")

    if output.sanitized_result is not None:
        print("Sanitized validation result:")
        print(
            json.dumps(
                output.sanitized_result,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )


def _redact_value(
    value: object,
    *,
    key_path: tuple[str, ...],
    extra_secrets: tuple[str, ...],
) -> object:
    current_key = key_path[-1].lower() if key_path else ""
    if _is_sensitive_key(current_key):
        return _REDACTED
    if _is_url_key(current_key):
        return _REDACTED_URL
    if key_path[-2:] == ("raw_text", "text") and isinstance(value, str):
        return f"<redacted raw text length={len(value)}>"

    if isinstance(value, Mapping):
        return {
            str(key): _redact_value(
                item,
                key_path=(*key_path, str(key).lower()),
                extra_secrets=extra_secrets,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _redact_value(item, key_path=key_path, extra_secrets=extra_secrets)
            for item in value
        ]
    if isinstance(value, tuple):
        return [
            _redact_value(item, key_path=key_path, extra_secrets=extra_secrets)
            for item in value
        ]
    if isinstance(value, str):
        if value.startswith(("https://", "http://")):
            return _REDACTED_URL
        redacted = value
        for secret in extra_secrets:
            redacted = redacted.replace(secret, _REDACTED)
        return redacted
    return value


def _is_sensitive_key(key: str) -> bool:
    return any(part in key for part in _SENSITIVE_KEY_PARTS)


def _is_url_key(key: str) -> bool:
    return any(part in key for part in _URL_KEY_PARTS)


def _optional_str(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _elapsed_seconds(started_at: float) -> float:
    return round(time.perf_counter() - started_at, 3)


if __name__ == "__main__":
    raise SystemExit(main())
