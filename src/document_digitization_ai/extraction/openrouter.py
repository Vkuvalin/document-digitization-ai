from __future__ import annotations

import json
import re
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, cast

from openai import APITimeoutError, AsyncOpenAI, OpenAIError

from document_digitization_ai.contracts import (
    BlockType,
    DetectedDocumentType,
    DocumentModeHint,
    FieldSource,
    ImageOrientation,
    WarningCode,
    WarningSeverity,
)
from document_digitization_ai.core import OpenRouterSettings, SettingsError
from document_digitization_ai.extraction.provider import (
    ExtractionProviderError,
    ExtractionProviderRequest,
    ExtractionProviderResponse,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderRejectedRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    validate_provider_request,
)
from document_digitization_ai.media import StagedMediaReferenceKind


MAX_PROVIDER_ERROR_MESSAGE_LENGTH = 500
COMPACT_SCHEMA_METADATA_KEYS = frozenset({"title", "description", "default", "examples"})
BACKEND_OWNED_PROVIDER_CONTEXT_SECTIONS = frozenset({"image_diagnostics"})
_SECRET_MESSAGE_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)(bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|token|secret)\s*[:=]\s*)[^\s,;]+"),
)


class OpenRouterChatCompletionClient(Protocol):
    async def create_chat_completion(self, **kwargs: object) -> object: ...


@dataclass(frozen=True, slots=True)
class DefaultOpenRouterChatCompletionClient:
    api_key: str = field(repr=False)
    base_url: str
    _client: Any = field(init=False, repr=False)

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.api_key, "api_key")
        _ensure_non_empty_text(self.base_url, "base_url")
        object.__setattr__(
            self,
            "_client",
            AsyncOpenAI(api_key=self.api_key, base_url=self.base_url),
        )

    async def create_chat_completion(self, **kwargs: object) -> object:
        completions = cast(Any, self._client.chat.completions)
        return await completions.create(**kwargs)


@dataclass(frozen=True, slots=True)
class OpenRouterExtractionProvider:
    client: OpenRouterChatCompletionClient = field(repr=False)
    app_title: str
    http_referer: str | None = None
    secret_values: tuple[str, ...] = field(default_factory=tuple, repr=False)

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.app_title, "app_title")
        _ensure_optional_text(self.http_referer, "http_referer")

    @classmethod
    def from_settings(
        cls,
        settings: OpenRouterSettings,
        *,
        client: OpenRouterChatCompletionClient | None = None,
    ) -> OpenRouterExtractionProvider:
        try:
            api_key = settings.require_api_key()
        except SettingsError as exc:
            raise ProviderAuthenticationError(str(exc)) from exc

        chat_client = client
        if chat_client is None:
            chat_client = DefaultOpenRouterChatCompletionClient(
                api_key=api_key,
                base_url=settings.base_url,
            )
        return cls(
            client=chat_client,
            app_title=settings.app_title,
            http_referer=settings.http_referer,
            secret_values=(api_key,),
        )

    async def extract(
        self,
        request: ExtractionProviderRequest,
    ) -> ExtractionProviderResponse:
        validate_provider_request(request)
        kwargs = build_openrouter_chat_completion_kwargs(
            request,
            app_title=self.app_title,
            http_referer=self.http_referer,
        )
        response = await self._create_completion(kwargs)
        parsed_content, finish_reason, metadata = _parse_completion_response(response)
        return ExtractionProviderResponse(
            provider_name="openrouter",
            model_name=_extract_response_model(
                response,
                fallback=request.context.extraction.model,
            ),
            raw_payload=parsed_content,
            raw_text=_extract_raw_text(parsed_content),
            finish_reason=finish_reason,
            metadata=metadata,
        )

    async def _create_completion(
        self,
        kwargs: Mapping[str, object],
    ) -> object:
        try:
            return await self.client.create_chat_completion(**dict(kwargs))
        except ExtractionProviderError:
            raise
        except Exception as exc:
            raise _map_sdk_error(exc, secret_values=self.secret_values) from exc


def build_openrouter_chat_completion_kwargs(
    request: ExtractionProviderRequest,
    *,
    app_title: str | None = None,
    http_referer: str | None = None,
) -> dict[str, object]:
    validate_provider_request(request)
    if not request.context.extraction.structured_outputs_enabled:
        msg = "OpenRouter adapter requires structured outputs to be enabled"
        raise ProviderConfigurationError(msg)
    prompt_package = _require_package_payload(request.prompt_package, "prompt_package")
    schema_package = _require_package_payload(request.schema_package, "schema_package")
    public_url = _require_public_staged_media_url(request)
    provider_output_sections = _provider_output_sections(
        _require_string_list(
            schema_package.get("required_sections"),
            "required_sections",
        )
    )
    user_text = _build_user_prompt_text(
        prompt_package,
        provider_output_sections=provider_output_sections,
    )

    kwargs: dict[str, object] = {
        "model": request.context.extraction.model,
        "temperature": request.context.extraction.temperature,
        "timeout": request.context.extraction.timeout_seconds,
        "messages": [
            {
                "role": "system",
                "content": _require_text(prompt_package, "system_instruction"),
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": user_text,
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": public_url,
                            "detail": "high",
                        },
                    },
                ],
            },
        ],
        "response_format": build_openrouter_response_format(schema_package),
    }
    extra_headers = _build_extra_headers(
        app_title=app_title,
        http_referer=http_referer,
    )
    if extra_headers:
        kwargs["extra_headers"] = extra_headers
    if request.context.extraction.structured_outputs_require_parameters:
        kwargs["extra_body"] = {"provider": {"require_parameters": True}}
    return kwargs


def build_openrouter_chat_completion_payload(
    request: ExtractionProviderRequest,
) -> dict[str, object]:
    return build_openrouter_chat_completion_kwargs(request)


def build_openrouter_response_format(
    schema_package_payload: Mapping[str, object],
) -> dict[str, object]:
    schema_version = _require_text(schema_package_payload, "target_schema_version")
    schema_mode = _require_text(schema_package_payload, "schema_mode")
    required_sections = _require_string_list(
        schema_package_payload.get("required_sections"),
        "required_sections",
    )
    schema_payload = _require_mapping_field(
        schema_package_payload.get("schema_payload"),
        "schema_payload",
    )
    _validate_schema_package_payload(
        schema_payload,
        schema_mode=schema_mode,
        required_sections=required_sections,
    )
    provider_schema = _build_provider_extraction_result_schema(
        _provider_output_sections(required_sections)
    )
    if schema_mode == "compact":
        provider_schema = _compact_json_schema_for_provider(provider_schema)
    elif schema_mode == "full":
        provider_schema = _sanitize_json_schema_for_provider(provider_schema)
    else:
        msg = f"Unsupported provider schema mode: {schema_mode}"
        raise ProviderRejectedRequestError(msg)
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _schema_name(schema_version),
            "strict": True,
            "schema": provider_schema,
        },
    }


def _provider_output_sections(required_sections: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        section
        for section in required_sections
        if section not in BACKEND_OWNED_PROVIDER_CONTEXT_SECTIONS
    )


def _parse_completion_response(
    response: object,
) -> tuple[Mapping[str, object], str | None, Mapping[str, object]]:
    choices = _get_value(response, "choices")
    if not isinstance(choices, list) or not choices:
        msg = "OpenRouter response is missing choices"
        raise ProviderMalformedResponseError(msg)
    first_choice = choices[0]
    message = _get_value(first_choice, "message")
    if message is None:
        msg = "OpenRouter response choice is missing message"
        raise ProviderMalformedResponseError(msg)
    content = _get_value(message, "content")
    parsed_content = _parse_message_content(content)
    finish_reason = _optional_text(_get_value(first_choice, "finish_reason"))
    metadata: dict[str, object] = {}
    usage = _mapping_from_jsonish_object(_get_value(response, "usage"), "usage")
    if usage is not None:
        metadata["usage"] = usage
    provider = _optional_text(_get_value(response, "provider"))
    if provider is not None:
        metadata["provider"] = provider
    response_id = _optional_text(_get_value(response, "id"))
    if response_id is not None:
        metadata["provider_response_id"] = response_id
    return parsed_content, finish_reason, metadata


def _parse_message_content(content: object) -> Mapping[str, object]:
    if isinstance(content, str):
        return _parse_json_content_text(content)
    if isinstance(content, list):
        text_parts = tuple(_content_text_part(item) for item in content)
        content_text = "".join(part for part in text_parts if part is not None)
        if content_text:
            return _parse_json_content_text(content_text)
    if isinstance(content, Mapping):
        return _json_mapping(content, "message.content")
    msg = "OpenRouter response message is missing content"
    raise ProviderMalformedResponseError(msg)


def _parse_json_content_text(content: str) -> Mapping[str, object]:
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError as exc:
        msg = "OpenRouter message content was not valid JSON"
        raise ProviderMalformedResponseError(msg) from exc
    if not isinstance(parsed, Mapping):
        msg = "OpenRouter message content JSON must be an object"
        raise ProviderMalformedResponseError(msg)
    return _json_mapping(parsed, "message.content")


def _content_text_part(item: object) -> str | None:
    if isinstance(item, str):
        return item
    text = _get_value(item, "text")
    if isinstance(text, str):
        return text
    return None


def _map_sdk_error(
    exc: Exception,
    *,
    secret_values: tuple[str, ...],
) -> ExtractionProviderError:
    if isinstance(exc, TimeoutError | APITimeoutError):
        return ProviderTimeoutError("OpenRouter request timed out")

    status_code = _sdk_status_code(exc)
    detail = _sdk_error_message(exc, secret_values=secret_values)
    if status_code in (401, 403):
        msg = f"OpenRouter authentication failed with HTTP status {status_code}"
        return ProviderAuthenticationError(_with_detail(msg, detail))
    if status_code == 429:
        return ProviderRateLimitError(_with_detail("OpenRouter rate limit exceeded", detail))
    if status_code is not None and status_code >= 500:
        msg = f"OpenRouter is unavailable with HTTP status {status_code}"
        return ProviderUnavailableError(_with_detail(msg, detail))
    if status_code in (400, 422):
        msg = f"OpenRouter rejected request with HTTP status {status_code}"
        return ProviderRejectedRequestError(_with_detail(msg, detail))
    if status_code is not None:
        msg = f"OpenRouter request failed with HTTP status {status_code}"
        return ProviderRejectedRequestError(_with_detail(msg, detail))
    if isinstance(exc, OpenAIError):
        return ProviderUnavailableError(
            _with_detail("OpenRouter SDK request failed", detail)
        )
    return ProviderUnavailableError(_with_detail("OpenRouter client failed", detail))


def _sdk_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    if isinstance(response_status, int):
        return response_status
    return None


def _sdk_error_message(
    exc: Exception,
    *,
    secret_values: tuple[str, ...],
) -> str | None:
    body_message = _message_from_error_payload(getattr(exc, "body", None))
    if body_message is not None:
        return _truncate_provider_error_message(
            _sanitize_provider_error_message(body_message, secret_values=secret_values)
        )
    message = getattr(exc, "message", None)
    if not isinstance(message, str) or not message.strip():
        message = str(exc)
    if not message.strip():
        return None
    return _truncate_provider_error_message(
        _sanitize_provider_error_message(message, secret_values=secret_values)
    )


def _message_from_error_payload(payload: object) -> str | None:
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return payload if payload.strip() else None
        return _message_from_error_payload(decoded)
    if not isinstance(payload, Mapping):
        return None
    error = payload.get("error")
    message: object | None = None
    if isinstance(error, Mapping):
        message = error.get("message")
    if message is None:
        message = payload.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    return message.strip()


def _with_detail(base_message: str, detail: str | None) -> str:
    if detail is None:
        return base_message
    return f"{base_message}: {detail}"


def _sanitize_provider_error_message(
    message: str,
    *,
    secret_values: tuple[str, ...],
) -> str:
    sanitized = " ".join(message.split())
    for secret in secret_values:
        if secret:
            sanitized = sanitized.replace(secret, "<redacted>")
    for pattern in _SECRET_MESSAGE_PATTERNS:
        sanitized = pattern.sub(r"\1<redacted>", sanitized)
    return sanitized


def _truncate_provider_error_message(message: str) -> str:
    if len(message) <= MAX_PROVIDER_ERROR_MESSAGE_LENGTH:
        return message
    return f"{message[:MAX_PROVIDER_ERROR_MESSAGE_LENGTH]}..."


def _require_package_payload(value: object | None, field_name: str) -> Mapping[str, object]:
    if value is None:
        msg = f"{field_name} is required for OpenRouter requests"
        raise ProviderRejectedRequestError(msg)
    to_dict = getattr(value, "to_dict", None)
    if not callable(to_dict):
        msg = f"{field_name} must provide callable to_dict()"
        raise ProviderRejectedRequestError(msg)
    payload = to_dict()
    if not isinstance(payload, Mapping):
        msg = f"{field_name}.to_dict() must return a JSON object"
        raise ProviderRejectedRequestError(msg)
    return _json_mapping(payload, field_name)


def _require_mapping_field(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be a JSON object"
        raise ProviderRejectedRequestError(msg)
    return _json_mapping(value, field_name)


def _require_public_staged_media_url(request: ExtractionProviderRequest) -> str:
    staged_media = request.staged_media
    if staged_media is None:
        msg = "staged_media with public URL is required for OpenRouter requests"
        raise ProviderRejectedRequestError(msg)
    if staged_media.kind is not StagedMediaReferenceKind.PUBLIC_URL:
        msg = "OpenRouter requests require PUBLIC_URL staged media"
        raise ProviderRejectedRequestError(msg)
    value = staged_media.value.strip()
    if not (value.startswith("https://") or value.startswith("http://")):
        msg = "OpenRouter staged media URL must be HTTP(S)"
        raise ProviderRejectedRequestError(msg)
    return value


def _build_user_prompt_text(
    prompt_package: Mapping[str, object],
    *,
    provider_output_sections: tuple[str, ...] | None = None,
) -> str:
    parts = [
        _require_text(prompt_package, "task_instruction"),
        _require_text(prompt_package, "document_mode_guidance"),
        *_require_string_list(
            prompt_package.get("diagnostics_guidance"),
            "diagnostics_guidance",
        ),
        *_provider_output_requirements(
            _require_string_list(
                prompt_package.get("output_requirements"),
                "output_requirements",
            ),
            provider_output_sections=provider_output_sections,
        ),
        *_require_string_list(
            prompt_package.get("uncertainty_guidance"),
            "uncertainty_guidance",
        ),
    ]
    return "\n\n".join(parts)


def _provider_output_requirements(
    output_requirements: tuple[str, ...],
    *,
    provider_output_sections: tuple[str, ...] | None,
) -> tuple[str, ...]:
    if provider_output_sections is None:
        return output_requirements

    provider_sections_text = ", ".join(provider_output_sections)
    provider_requirements = tuple(
        (
            f"Provider output top-level sections: {provider_sections_text}."
            if requirement.startswith("Expected top-level sections:")
            else requirement
        )
        for requirement in output_requirements
    )
    if not BACKEND_OWNED_PROVIDER_CONTEXT_SECTIONS:
        return provider_requirements
    backend_sections_text = ", ".join(sorted(BACKEND_OWNED_PROVIDER_CONTEXT_SECTIONS))
    return (
        *provider_requirements,
        (
            "Backend-owned context sections are already supplied by the backend; "
            f"use {backend_sections_text} only as guidance and do not include "
            "these sections in provider output."
        ),
    )


def _build_extra_headers(
    *,
    app_title: str | None,
    http_referer: str | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if http_referer is not None and http_referer.strip():
        headers["HTTP-Referer"] = http_referer.strip()
    if app_title is not None and app_title.strip():
        headers["X-Title"] = app_title.strip()
    return headers


def _schema_name(schema_version: str) -> str:
    sanitized = "".join(
        character if character.isalnum() else "_"
        for character in schema_version.strip().lower()
    ).strip("_")
    if not sanitized:
        return "document_extraction_result"
    return f"document_{sanitized}"


def _validate_schema_package_payload(
    schema_payload: Mapping[str, object],
    *,
    schema_mode: str,
    required_sections: tuple[str, ...],
) -> None:
    schema_detail = schema_payload.get("schema_detail")
    if schema_detail != schema_mode:
        msg = "schema_payload.schema_detail must match schema_mode"
        raise ProviderRejectedRequestError(msg)

    payload_required = schema_payload.get("required")
    if isinstance(payload_required, list):
        missing_sections = sorted(set(required_sections) - set(payload_required))
        if missing_sections:
            msg = (
                "schema_payload.required is missing expected sections: "
                f"{', '.join(missing_sections)}"
            )
            raise ProviderRejectedRequestError(msg)

    if schema_mode == "compact":
        if not isinstance(schema_payload.get("sections"), Mapping):
            msg = "compact schema_payload must include sections"
            raise ProviderRejectedRequestError(msg)
        return

    if schema_mode == "full":
        if not isinstance(schema_payload.get("properties"), Mapping):
            msg = "full schema_payload must include properties"
            raise ProviderRejectedRequestError(msg)
        return


def _build_provider_extraction_result_schema(
    required_sections: tuple[str, ...],
) -> dict[str, object]:
    section_schemas = _extraction_result_section_schemas()
    properties: dict[str, object] = {}
    for section in required_sections:
        section_schema = section_schemas.get(section)
        if section_schema is None:
            msg = f"Unsupported extraction result section for OpenRouter schema: {section}"
            raise ProviderRejectedRequestError(msg)
        properties[section] = section_schema
    return _object_schema(
        properties=properties,
        required=required_sections,
        title="DocumentExtractionResult",
        description=(
            "Validated backend target shape for document extraction provider output."
        ),
    )


def _extraction_result_section_schemas() -> dict[str, object]:
    return {
        "document": _document_schema(),
        "image_diagnostics": _image_diagnostics_schema(),
        "raw_text": _raw_text_schema(),
        "fields": _array_schema(
            _field_schema(),
            description="Visible label/value pairs extracted from the document.",
        ),
        "tables": _array_schema(
            _table_schema(),
            description="Visible tabular structures extracted from the document.",
        ),
        "blocks": _array_schema(
            _block_schema(),
            description="Ordered visible text blocks extracted from the document.",
        ),
        "warnings": _array_schema(
            _warning_schema(),
            description="Provider warnings about uncertainty or partial extraction.",
        ),
        "metadata": _extraction_metadata_schema(),
    }


def _document_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "user_mode_hint": _enum_schema(DocumentModeHint),
            "detected_type": _enum_schema(DetectedDocumentType),
            "detected_type_confidence": _nullable_unit_interval_schema(),
            "language": _nullable_string_schema(),
            "summary": _nullable_string_schema(),
        },
        title="DocumentInfo",
        description="Document-level interpretation. User mode hint is guidance.",
    )


def _image_diagnostics_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "file": _object_schema(
                properties={
                    "mime_type": _string_schema(),
                    "file_size_bytes": _positive_integer_schema(),
                    "file_extension": _string_schema(),
                    "sha256": _nullable_string_schema(),
                },
                title="ImageFileMetadata",
                description="Backend image file metadata echoed for traceability.",
            ),
            "image": _object_schema(
                properties={
                    "width": _positive_integer_schema(),
                    "height": _positive_integer_schema(),
                    "aspect_ratio": _positive_number_schema(),
                    "orientation": _enum_schema(ImageOrientation),
                    "exif_orientation": _nullable_positive_integer_schema(),
                    "color_mode": _nullable_string_schema(),
                    "format": _nullable_string_schema(),
                },
                title="ImageShape",
                description="Backend image dimensions and format metadata.",
            ),
            "quality": _object_schema(
                properties={
                    "blur_score": _nullable_non_negative_number_schema(),
                    "sharpness_score": _nullable_non_negative_number_schema(),
                    "brightness": _nullable_non_negative_number_schema(),
                    "contrast": _nullable_non_negative_number_schema(),
                    "is_low_resolution": _nullable_boolean_schema(),
                    "is_probably_blurry": _nullable_boolean_schema(),
                    "is_low_contrast": _nullable_boolean_schema(),
                },
                title="ImageQualityIndicators",
                description="Backend image quality diagnostics.",
            ),
            "warnings": _array_schema(_warning_schema()),
            "metadata": _object_schema(
                properties={"schema_version": _nullable_string_schema()},
                title="ImageDiagnosticsMetadata",
                description="Image diagnostics metadata.",
            ),
        },
        title="ImageDiagnostics",
        description="Backend diagnostics context; not a substitute for extraction.",
    )


def _raw_text_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "text": _string_schema(description="Best-effort visible text."),
            "confidence": _nullable_unit_interval_schema(),
            "warnings": _array_schema(_warning_schema()),
        },
        title="RawText",
        description="Best-effort raw visible text with uncertainty.",
    )


def _field_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "label": _string_schema(),
            "value": _string_schema(),
            "confidence": _nullable_unit_interval_schema(),
            "source": _enum_schema(FieldSource),
            "warnings": _array_schema(_warning_schema()),
        },
        title="ExtractedField",
        description="Visible document field with label and value.",
    )


def _table_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "title": _nullable_string_schema(),
            "columns": _array_schema(_string_schema()),
            "rows": _array_schema(_table_row_schema()),
            "confidence": _nullable_unit_interval_schema(),
            "warnings": _array_schema(_warning_schema()),
        },
        title="ExtractedTable",
        description="Visible table with columns and rows.",
    )


def _table_row_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "cells": _array_schema(_string_schema()),
            "confidence": _nullable_unit_interval_schema(),
            "warnings": _array_schema(_warning_schema()),
        },
        title="TableRow",
        description="Visible table row cells aligned to table columns.",
    )


def _block_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "type": _enum_schema(BlockType),
            "level": _nullable_positive_integer_schema(),
            "text": _string_schema(),
            "order": _non_negative_integer_schema(),
            "confidence": _nullable_unit_interval_schema(),
            "warnings": _array_schema(_warning_schema()),
        },
        title="TextBlock",
        description="Ordered visible text block.",
    )


def _warning_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "code": _enum_schema(WarningCode),
            "message": _string_schema(),
            "severity": _enum_schema(WarningSeverity),
            "target": _nullable_string_schema(),
        },
        title="Warning",
        description="Extraction or validation warning.",
    )


def _extraction_metadata_schema() -> dict[str, object]:
    return _object_schema(
        properties={
            "schema_version": _string_schema(),
            "provider": _nullable_string_schema(),
            "model": _nullable_string_schema(),
            "created_at": _nullable_string_schema(),
        },
        title="ExtractionMetadata",
        description="Provider result metadata for backend validation.",
    )


def _object_schema(
    *,
    properties: Mapping[str, object],
    required: tuple[str, ...] | None = None,
    title: str | None = None,
    description: str | None = None,
) -> dict[str, object]:
    schema: dict[str, object] = {
        "type": "object",
        "additionalProperties": False,
        "required": list(required or tuple(properties)),
        "properties": dict(properties),
    }
    if title is not None:
        schema["title"] = title
    if description is not None:
        schema["description"] = description
    return schema


def _array_schema(
    items: Mapping[str, object],
    *,
    description: str | None = None,
) -> dict[str, object]:
    schema: dict[str, object] = {"type": "array", "items": dict(items)}
    if description is not None:
        schema["description"] = description
    return schema


def _string_schema(*, description: str | None = None) -> dict[str, object]:
    schema: dict[str, object] = {"type": "string"}
    if description is not None:
        schema["description"] = description
    return schema


def _nullable_string_schema() -> dict[str, object]:
    return {"type": ["string", "null"]}


def _nullable_boolean_schema() -> dict[str, object]:
    return {"type": ["boolean", "null"]}


def _positive_integer_schema() -> dict[str, object]:
    return {"type": "integer", "minimum": 1}


def _non_negative_integer_schema() -> dict[str, object]:
    return {"type": "integer", "minimum": 0}


def _nullable_positive_integer_schema() -> dict[str, object]:
    return {"type": ["integer", "null"], "minimum": 1}


def _positive_number_schema() -> dict[str, object]:
    return {"type": "number", "exclusiveMinimum": 0}


def _nullable_non_negative_number_schema() -> dict[str, object]:
    return {"type": ["number", "null"], "minimum": 0}


def _nullable_unit_interval_schema() -> dict[str, object]:
    return {"type": ["number", "null"], "minimum": 0, "maximum": 1}


def _enum_schema(enum_type: type[StrEnum]) -> dict[str, object]:
    return {
        "type": "string",
        "enum": [item.value for item in enum_type],
    }


def _compact_json_schema_for_provider(schema: dict[str, object]) -> dict[str, object]:
    sanitized = _sanitize_json_schema_for_provider(schema)
    compacted = _remove_json_schema_metadata(sanitized, parent_key=None)
    if not isinstance(compacted, dict):
        msg = "JSON Schema root must be an object."
        raise ProviderRejectedRequestError(msg)
    return dict(_json_mapping(compacted, "response_format.schema"))


def _sanitize_json_schema_for_provider(schema: dict[str, object]) -> dict[str, object]:
    root_schema = deepcopy(schema)
    sanitized = _sanitize_json_schema_value(
        value=root_schema,
        root_schema=root_schema,
        ref_stack=set(),
    )
    if not isinstance(sanitized, dict):
        msg = "JSON Schema root must be an object."
        raise ProviderRejectedRequestError(msg)
    return dict(_json_mapping(sanitized, "response_format.schema"))


def _sanitize_json_schema_value(
    value: Any,
    root_schema: dict[str, object],
    ref_stack: set[str],
) -> Any:
    if isinstance(value, dict):
        ref = value.get("$ref")
        if isinstance(ref, str) and len(value) > 1:
            if ref in ref_stack:
                msg = f"Cyclic JSON Schema $ref detected: {ref}"
                raise ProviderRejectedRequestError(msg)
            referenced_schema = _resolve_local_json_pointer_ref(
                root_schema=root_schema,
                ref=ref,
            )
            merged_schema = deepcopy(referenced_schema)
            for key, item in value.items():
                if key == "$ref":
                    continue
                merged_schema[key] = deepcopy(item)
            return _sanitize_json_schema_value(
                value=merged_schema,
                root_schema=root_schema,
                ref_stack=ref_stack | {ref},
            )
        if isinstance(ref, str):
            return deepcopy(value)
        return {
            key: _sanitize_json_schema_value(
                value=item,
                root_schema=root_schema,
                ref_stack=ref_stack,
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [
            _sanitize_json_schema_value(
                value=item,
                root_schema=root_schema,
                ref_stack=ref_stack,
            )
            for item in value
        ]
    return deepcopy(value)


def _remove_json_schema_metadata(value: Any, parent_key: str | None) -> Any:
    if isinstance(value, dict):
        if parent_key in {"$defs", "properties", "patternProperties"}:
            return {
                key: _remove_json_schema_metadata(item, parent_key=key)
                for key, item in value.items()
            }
        return {
            key: _remove_json_schema_metadata(item, parent_key=key)
            for key, item in value.items()
            if key not in COMPACT_SCHEMA_METADATA_KEYS
        }
    if isinstance(value, list):
        return [
            _remove_json_schema_metadata(item, parent_key=parent_key)
            for item in value
        ]
    return deepcopy(value)


def _resolve_local_json_pointer_ref(
    root_schema: dict[str, object],
    ref: str,
) -> dict[str, object]:
    if ref == "#":
        return root_schema
    if not ref.startswith("#/"):
        msg = f"Only local JSON Schema $ref values are supported: {ref}"
        raise ProviderRejectedRequestError(msg)
    current: Any = root_schema
    for raw_token in ref[2:].split("/"):
        token = _unescape_json_pointer_token(raw_token)
        if not isinstance(current, dict) or token not in current:
            msg = f"Could not resolve JSON Schema $ref: {ref}"
            raise ProviderRejectedRequestError(msg)
        current = current[token]
    if not isinstance(current, dict):
        msg = f"JSON Schema $ref does not point to an object: {ref}"
        raise ProviderRejectedRequestError(msg)
    return current


def _unescape_json_pointer_token(token: str) -> str:
    return token.replace("~1", "/").replace("~0", "~")


def _extract_response_model(
    response: object,
    *,
    fallback: str,
) -> str:
    model = _get_value(response, "model")
    if isinstance(model, str) and model.strip():
        return model.strip()
    return fallback


def _extract_raw_text(payload: Mapping[str, object]) -> str | None:
    raw_text = payload.get("raw_text")
    if not isinstance(raw_text, Mapping):
        return None
    text = raw_text.get("text")
    if not isinstance(text, str) or not text.strip():
        return None
    return text


def _get_value(source: object, key: str) -> object:
    if isinstance(source, Mapping):
        return source.get(key)
    return getattr(source, key, None)


def _mapping_from_jsonish_object(
    value: object,
    field_name: str,
) -> Mapping[str, object] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return _json_mapping(value, field_name)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, Mapping):
            return _json_mapping(dumped, field_name)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        dumped = to_dict()
        if isinstance(dumped, Mapping):
            return _json_mapping(dumped, field_name)
    return None


def _require_text(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        msg = f"{key} must be present"
        raise ProviderRejectedRequestError(msg)
    return value.strip()


def _optional_text(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _require_string_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        msg = f"{field_name} must contain at least one string"
        raise ProviderRejectedRequestError(msg)
    values: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            msg = f"{field_name} must contain only non-empty strings"
            raise ProviderRejectedRequestError(msg)
        values.append(item.strip())
    return tuple(values)


def _json_mapping(value: Mapping[object, object], field_name: str) -> Mapping[str, object]:
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            msg = f"{field_name} keys must be non-empty strings"
            raise ProviderMalformedResponseError(msg)
        result[key] = _json_value(item, f"{field_name}.{key}")
    return result


def _json_value(value: object, field_name: str) -> object:
    if value is None or isinstance(value, str | bool | int):
        return value
    if isinstance(value, float):
        if not value == value or value in (float("inf"), float("-inf")):
            msg = f"{field_name} must be finite"
            raise ProviderMalformedResponseError(msg)
        return value
    if isinstance(value, list):
        return [_json_value(item, f"{field_name}[]") for item in value]
    if isinstance(value, Mapping):
        return dict(_json_mapping(value, field_name))
    msg = f"{field_name} must be JSON-compatible"
    raise ProviderMalformedResponseError(msg)


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_optional_text(value: str | None, field_name: str) -> None:
    if value is not None:
        _ensure_non_empty_text(value, field_name)
