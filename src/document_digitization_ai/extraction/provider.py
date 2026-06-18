from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from typing import Protocol

from document_digitization_ai.media import StagedMediaReference
from document_digitization_ai.providers import ProviderInputContext, SupportsToDict


class ExtractionProviderError(RuntimeError):
    """Base error for extraction provider boundary failures."""


class ExtractionProviderRequestError(ExtractionProviderError):
    """Raised when provider request data is invalid at the boundary."""


class ProviderConfigurationError(ExtractionProviderError):
    """Raised when provider settings or implementation availability are invalid."""


class ProviderAuthenticationError(ExtractionProviderError):
    """Raised when provider authentication fails."""


class ProviderRateLimitError(ExtractionProviderError):
    """Raised when a provider rate limit blocks extraction."""


class ProviderTimeoutError(ExtractionProviderError):
    """Raised when a provider call exceeds the configured timeout."""


class ProviderUnavailableError(ExtractionProviderError):
    """Raised when a provider is temporarily unavailable."""


class ProviderMalformedResponseError(ExtractionProviderError):
    """Raised when a provider response cannot be parsed into the provider boundary."""


class ProviderRejectedRequestError(ExtractionProviderError):
    """Raised when a provider rejects the request payload."""


class FakeExtractionProviderError(ExtractionProviderError):
    """Raised by the deterministic fake provider when configured to fail."""


@dataclass(frozen=True, slots=True)
class ExtractionProviderRequest:
    correlation_id: str
    context: ProviderInputContext
    staged_media: StagedMediaReference | None = None
    provider_options: Mapping[str, object] = field(default_factory=dict)
    prompt_package: SupportsToDict | None = None
    schema_package: SupportsToDict | None = None

    def __post_init__(self) -> None:
        try:
            _ensure_non_empty_text(self.correlation_id, "correlation_id")
            _ensure_json_object(self.provider_options, "provider_options")
            _ensure_to_dict_package(self.prompt_package, "prompt_package")
            _ensure_to_dict_package(self.schema_package, "schema_package")
        except ValueError as exc:
            raise ExtractionProviderRequestError(str(exc)) from exc
        if not isinstance(self.context, ProviderInputContext):
            msg = "context must be a ProviderInputContext value"
            raise ExtractionProviderRequestError(msg)
        if self.staged_media is not None and not isinstance(
            self.staged_media,
            StagedMediaReference,
        ):
            msg = "staged_media must be a StagedMediaReference value"
            raise ExtractionProviderRequestError(msg)

    def to_dict(self) -> dict[str, object]:
        return {
            "correlation_id": self.correlation_id,
            "context": self.context.to_dict(),
            "staged_media": (
                self.staged_media.to_dict() if self.staged_media is not None else None
            ),
            "provider_options": dict(self.provider_options),
            "prompt_package": (
                self.prompt_package.to_dict()
                if self.prompt_package is not None
                else None
            ),
            "schema_package": (
                self.schema_package.to_dict()
                if self.schema_package is not None
                else None
            ),
        }


@dataclass(frozen=True, slots=True)
class ExtractionProviderResponse:
    provider_name: str
    model_name: str
    raw_payload: object
    raw_text: str | None = None
    finish_reason: str | None = None
    warnings: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, object] = field(default_factory=dict)
    raw_response_json: object | None = None

    def __post_init__(self) -> None:
        _ensure_non_empty_text(self.provider_name, "provider_name")
        _ensure_non_empty_text(self.model_name, "model_name")
        _ensure_json_compatible(self.raw_payload, "raw_payload")
        _ensure_optional_non_empty_text(self.raw_text, "raw_text")
        _ensure_optional_non_empty_text(self.finish_reason, "finish_reason")
        for warning in self.warnings:
            _ensure_non_empty_text(warning, "warnings")
        _ensure_json_object(self.metadata, "metadata")
        _ensure_json_compatible(self.raw_response_json, "raw_response_json")

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "raw_payload": self.raw_payload,
            "raw_text": self.raw_text,
            "finish_reason": self.finish_reason,
            "warnings": list(self.warnings),
            "metadata": dict(self.metadata),
            "raw_response_json": self.raw_response_json,
        }


class ExtractionProviderPort(Protocol):
    async def extract(
        self,
        request: ExtractionProviderRequest,
    ) -> ExtractionProviderResponse: ...


def validate_provider_request(request: ExtractionProviderRequest) -> None:
    if not isinstance(request, ExtractionProviderRequest):
        msg = "request must be an ExtractionProviderRequest value"
        raise ExtractionProviderRequestError(msg)


def _ensure_json_object(value: Mapping[str, object], field_name: str) -> None:
    if not isinstance(value, Mapping):
        msg = f"{field_name} must be a JSON object"
        raise ValueError(msg)
    for key, item in value.items():
        if not isinstance(key, str) or not key.strip():
            msg = f"{field_name} keys must be non-empty strings"
            raise ValueError(msg)
        _ensure_json_compatible(item, f"{field_name}.{key}")


def _ensure_json_compatible(value: object, field_name: str) -> None:
    if value is None or isinstance(value, str | bool | int):
        return
    if isinstance(value, float):
        if not isfinite(value):
            msg = f"{field_name} must be finite"
            raise ValueError(msg)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _ensure_json_compatible(item, f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        _ensure_json_object(value, field_name)
        return
    msg = f"{field_name} must be JSON-compatible"
    raise ValueError(msg)


def _ensure_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        msg = f"{field_name} must not be empty"
        raise ValueError(msg)


def _ensure_optional_non_empty_text(value: str | None, field_name: str) -> None:
    if value is not None:
        _ensure_non_empty_text(value, field_name)


def _ensure_to_dict_package(value: object | None, field_name: str) -> None:
    if value is None:
        return
    if not callable(getattr(value, "to_dict", None)):
        msg = f"{field_name} must provide callable to_dict()"
        raise ValueError(msg)
