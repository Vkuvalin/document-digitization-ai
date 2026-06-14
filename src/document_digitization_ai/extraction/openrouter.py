from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from document_digitization_ai.core import OpenRouterSettings, SettingsError
from document_digitization_ai.extraction.provider import (
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


OPENROUTER_CHAT_COMPLETIONS_PATH = "/chat/completions"


@dataclass(frozen=True, slots=True)
class OpenRouterHTTPResponseData:
    status_code: int
    body: bytes
    headers: Mapping[str, str] = field(default_factory=dict)


class OpenRouterHTTPTransport(Protocol):
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        *,
        timeout_seconds: int,
    ) -> OpenRouterHTTPResponseData: ...


@dataclass(frozen=True, slots=True)
class DefaultOpenRouterHTTPTransport:
    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        *,
        timeout_seconds: int,
    ) -> OpenRouterHTTPResponseData:
        request = Request(
            url=url,
            data=json.dumps(payload).encode("utf-8"),
            headers=dict(headers),
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                response_obj = cast(Any, response)
                status_code = int(response_obj.status)
                response_headers = {
                    str(key): str(value)
                    for key, value in response_obj.headers.items()
                }
                body = cast(bytes, response_obj.read())
        except HTTPError as exc:
            body = cast(bytes, exc.read())
            return OpenRouterHTTPResponseData(
                status_code=int(exc.code),
                body=body,
                headers={str(key): str(value) for key, value in exc.headers.items()},
            )
        except TimeoutError:
            raise
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise exc.reason from exc
            raise
        return OpenRouterHTTPResponseData(
            status_code=status_code,
            body=body,
            headers=response_headers,
        )


@dataclass(frozen=True, slots=True)
class OpenRouterExtractionProvider:
    api_key: str = field(repr=False)
    base_url: str
    app_title: str
    http_referer: str | None = None
    transport: OpenRouterHTTPTransport = field(
        default_factory=DefaultOpenRouterHTTPTransport,
        repr=False,
    )

    @classmethod
    def from_settings(
        cls,
        settings: OpenRouterSettings,
        *,
        transport: OpenRouterHTTPTransport | None = None,
    ) -> OpenRouterExtractionProvider:
        try:
            api_key = settings.require_api_key()
        except SettingsError as exc:
            raise ProviderAuthenticationError(str(exc)) from exc
        if transport is None:
            return cls(
                api_key=api_key,
                base_url=settings.base_url,
                app_title=settings.app_title,
                http_referer=settings.http_referer,
            )
        return cls(
            api_key=api_key,
            base_url=settings.base_url,
            app_title=settings.app_title,
            http_referer=settings.http_referer,
            transport=transport,
        )

    async def extract(
        self,
        request: ExtractionProviderRequest,
    ) -> ExtractionProviderResponse:
        validate_provider_request(request)
        payload = build_openrouter_chat_completion_payload(request)
        response = await self._post_completion(
            payload,
            timeout_seconds=request.context.extraction.timeout_seconds,
        )
        response_payload = _parse_http_response(response)
        parsed_content, finish_reason, metadata = _parse_completion_payload(
            response_payload
        )
        return ExtractionProviderResponse(
            provider_name="openrouter",
            model_name=_extract_response_model(
                response_payload,
                fallback=request.context.extraction.model,
            ),
            raw_payload=parsed_content,
            raw_text=_extract_raw_text(parsed_content),
            finish_reason=finish_reason,
            metadata=metadata,
        )

    async def _post_completion(
        self,
        payload: Mapping[str, object],
        *,
        timeout_seconds: int,
    ) -> OpenRouterHTTPResponseData:
        try:
            return await asyncio.to_thread(
                self.transport.post_json,
                _join_url(self.base_url, OPENROUTER_CHAT_COMPLETIONS_PATH),
                self._headers(),
                payload,
                timeout_seconds=timeout_seconds,
            )
        except TimeoutError as exc:
            msg = "OpenRouter request timed out"
            raise ProviderTimeoutError(msg) from exc
        except ProviderTimeoutError:
            raise
        except Exception as exc:
            msg = "OpenRouter transport failed"
            raise ProviderUnavailableError(msg) from exc

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "X-OpenRouter-Title": self.app_title,
        }
        if self.http_referer is not None:
            headers["HTTP-Referer"] = self.http_referer
        return headers


def build_openrouter_chat_completion_payload(
    request: ExtractionProviderRequest,
) -> dict[str, object]:
    validate_provider_request(request)
    if not request.context.extraction.structured_outputs_enabled:
        msg = "OpenRouter adapter requires structured outputs to be enabled"
        raise ProviderConfigurationError(msg)
    prompt_package = _require_package_payload(request.prompt_package, "prompt_package")
    schema_package = _require_package_payload(request.schema_package, "schema_package")
    public_url = _require_public_staged_media_url(request)
    user_text = _build_user_prompt_text(prompt_package)
    payload: dict[str, object] = {
        "model": request.context.extraction.model,
        "temperature": request.context.extraction.temperature,
        "stream": False,
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
                        },
                    },
                ],
            },
        ],
        "response_format": build_openrouter_response_format(schema_package),
    }
    if request.context.extraction.structured_outputs_require_parameters:
        payload["provider"] = {"require_parameters": True}
    return payload


def build_openrouter_response_format(
    schema_package_payload: Mapping[str, object],
) -> dict[str, object]:
    schema_version = _require_text(schema_package_payload, "target_schema_version")
    required_sections = _require_string_list(
        schema_package_payload.get("required_sections"),
        "required_sections",
    )
    return {
        "type": "json_schema",
        "json_schema": {
            "name": _schema_name(schema_version),
            "strict": True,
            "schema": {
                "type": "object",
                "additionalProperties": False,
                "required": required_sections,
                "properties": _schema_properties(required_sections),
            },
        },
    }


def _parse_http_response(
    response: OpenRouterHTTPResponseData,
) -> Mapping[str, object]:
    if response.status_code in (401, 403):
        msg = f"OpenRouter authentication failed with HTTP status {response.status_code}"
        raise ProviderAuthenticationError(msg)
    if response.status_code == 429:
        msg = "OpenRouter rate limit exceeded"
        raise ProviderRateLimitError(msg)
    if response.status_code >= 500:
        msg = f"OpenRouter is unavailable with HTTP status {response.status_code}"
        raise ProviderUnavailableError(msg)
    if response.status_code in (400, 422):
        msg = f"OpenRouter rejected request with HTTP status {response.status_code}"
        raise ProviderRejectedRequestError(msg)
    if response.status_code < 200 or response.status_code >= 300:
        msg = f"OpenRouter request failed with HTTP status {response.status_code}"
        raise ProviderRejectedRequestError(msg)
    try:
        payload = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        msg = "OpenRouter response was not valid JSON"
        raise ProviderMalformedResponseError(msg) from exc
    if not isinstance(payload, Mapping):
        msg = "OpenRouter response must be a JSON object"
        raise ProviderMalformedResponseError(msg)
    return payload


def _parse_completion_payload(
    payload: Mapping[str, object],
) -> tuple[Mapping[str, object], str | None, Mapping[str, object]]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        msg = "OpenRouter response is missing choices"
        raise ProviderMalformedResponseError(msg)
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        msg = "OpenRouter response choice must be an object"
        raise ProviderMalformedResponseError(msg)
    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        msg = "OpenRouter response choice is missing message"
        raise ProviderMalformedResponseError(msg)
    content = message.get("content")
    parsed_content = _parse_message_content(content)
    finish_reason = _optional_text(first_choice.get("finish_reason"))
    metadata: dict[str, object] = {}
    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        metadata["usage"] = _json_mapping(usage, "usage")
    provider = payload.get("provider")
    if isinstance(provider, str) and provider.strip():
        metadata["provider"] = provider.strip()
    response_id = payload.get("id")
    if isinstance(response_id, str) and response_id.strip():
        metadata["provider_response_id"] = response_id.strip()
    return parsed_content, finish_reason, metadata


def _parse_message_content(content: object) -> Mapping[str, object]:
    if isinstance(content, str):
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            msg = "OpenRouter message content was not valid JSON"
            raise ProviderMalformedResponseError(msg) from exc
        if not isinstance(parsed, Mapping):
            msg = "OpenRouter message content JSON must be an object"
            raise ProviderMalformedResponseError(msg)
        return _json_mapping(parsed, "message.content")
    if isinstance(content, Mapping):
        return _json_mapping(content, "message.content")
    msg = "OpenRouter response message is missing content"
    raise ProviderMalformedResponseError(msg)


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


def _build_user_prompt_text(prompt_package: Mapping[str, object]) -> str:
    parts = [
        _require_text(prompt_package, "task_instruction"),
        _require_text(prompt_package, "document_mode_guidance"),
        *_require_string_list(
            prompt_package.get("diagnostics_guidance"),
            "diagnostics_guidance",
        ),
        *_require_string_list(
            prompt_package.get("output_requirements"),
            "output_requirements",
        ),
        *_require_string_list(
            prompt_package.get("uncertainty_guidance"),
            "uncertainty_guidance",
        ),
    ]
    return "\n\n".join(parts)


def _schema_name(schema_version: str) -> str:
    sanitized = "".join(
        character if character.isalnum() else "_"
        for character in schema_version.strip().lower()
    ).strip("_")
    if not sanitized:
        return "document_extraction_result"
    return f"document_{sanitized}"


def _schema_properties(required_sections: tuple[str, ...]) -> dict[str, object]:
    array_sections = {"fields", "tables", "blocks", "warnings"}
    properties: dict[str, object] = {}
    for section in required_sections:
        if section in array_sections:
            properties[section] = {"type": "array", "items": {"type": "object"}}
        else:
            properties[section] = {"type": "object"}
    return properties


def _extract_response_model(
    payload: Mapping[str, object],
    *,
    fallback: str,
) -> str:
    model = payload.get("model")
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


def _join_url(base_url: str, path: str) -> str:
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
