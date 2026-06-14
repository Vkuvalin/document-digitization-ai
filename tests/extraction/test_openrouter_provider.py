import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

import pytest
from pydantic import SecretStr

from document_digitization_ai.contracts import DocumentModeHint, ExtractionResult, JobStatus
from document_digitization_ai.core import (
    ExtractionProviderName,
    ExtractionSettings,
    OpenRouterSettings,
    ProviderSchemaMode,
)
from document_digitization_ai.extraction import (
    ExtractionProviderFactory,
    ExtractionProviderRequest,
    FakeExtractionProvider,
    OpenRouterExtractionProvider,
    OpenRouterHTTPResponseData,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderRejectedRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    build_extraction_prompt_package,
    build_extraction_provider,
    build_extraction_schema_package,
    build_openrouter_chat_completion_payload,
    build_openrouter_response_format,
)
from document_digitization_ai.media import (
    StagedMediaReference,
    StagedMediaReferenceKind,
)
from document_digitization_ai.providers import (
    ProviderDiagnosticsSummary,
    ProviderExtractionRuntimeSettings,
    ProviderImageInput,
    ProviderInputContext,
)


_UNSET = object()


def test_openrouter_request_builder_uses_public_url_without_private_data(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    request = _provider_request(
        image_path,
        staged_media=StagedMediaReference(
            kind=StagedMediaReferenceKind.PUBLIC_URL,
            value="https://i.ibb.co/example/staged.jpg",
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            metadata={
                "private_cleanup_url_available": True,
                "private_cleanup_token": "delete-private-token",
            },
        ),
    )

    payload = build_openrouter_chat_completion_payload(request)
    serialized_payload = json.dumps(payload, sort_keys=True)
    user_content = _user_content(payload)

    assert payload["model"] == "openai/test-vision"
    assert payload["temperature"] == 0.2
    assert payload["stream"] is False
    assert user_content[0]["type"] == "text"
    assert user_content[1]["type"] == "image_url"
    image_url = cast(Mapping[str, object], user_content[1]["image_url"])
    assert image_url["url"] == "https://i.ibb.co/example/staged.jpg"
    assert str(image_path) not in serialized_payload
    assert "delete-private-token" not in serialized_payload
    assert "private_cleanup" not in serialized_payload
    assert "fake-openrouter-key" not in serialized_payload


def test_openrouter_request_builder_adds_provider_require_parameters_when_enabled(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    request = _provider_request(
        image_path,
        structured_outputs_require_parameters=True,
        staged_media=StagedMediaReference(
            kind=StagedMediaReferenceKind.PUBLIC_URL,
            value="https://i.ibb.co/example/staged.jpg",
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
            metadata={
                "delete_url": "https://ibb.co/private-delete",
                "private_cleanup_token": "delete-private-token",
            },
        ),
    )

    payload = build_openrouter_chat_completion_payload(request)
    serialized_payload = json.dumps(payload, sort_keys=True)

    provider_payload = cast(Mapping[str, object], payload["provider"])
    assert provider_payload["require_parameters"] is True
    assert str(image_path) not in serialized_payload
    assert "fake-openrouter-key" not in serialized_payload
    assert "delete_url" not in serialized_payload
    assert "delete-private-token" not in serialized_payload
    assert "private-delete" not in serialized_payload


def test_openrouter_request_builder_omits_provider_require_parameters_when_disabled(
    tmp_path: Path,
) -> None:
    request = _provider_request(
        tmp_path / "original.jpg",
        structured_outputs_require_parameters=False,
    )

    payload = build_openrouter_chat_completion_payload(request)

    assert "provider" not in payload


@pytest.mark.asyncio
async def test_openrouter_provider_rejects_disabled_structured_outputs_before_transport_call(
    tmp_path: Path,
) -> None:
    transport = FakeOpenRouterHTTPTransport(response=_openrouter_response())
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        transport=transport,
    )
    request = _provider_request(
        tmp_path / "original.jpg",
        structured_outputs_enabled=False,
    )

    with pytest.raises(ProviderConfigurationError, match="structured outputs"):
        build_openrouter_chat_completion_payload(request)

    with pytest.raises(ProviderConfigurationError, match="structured outputs"):
        await provider.extract(request)

    assert transport.calls == []


def test_openrouter_response_format_maps_provider_neutral_schema(
    tmp_path: Path,
) -> None:
    request = _provider_request(tmp_path / "original.jpg")
    assert request.schema_package is not None

    response_format = build_openrouter_response_format(
        request.schema_package.to_dict()
    )

    assert response_format["type"] == "json_schema"
    json_schema = cast(Mapping[str, object], response_format["json_schema"])
    assert json_schema["name"] == "document_extraction_result_v0"
    assert json_schema["strict"] is True
    schema = cast(Mapping[str, object], json_schema["schema"])
    required = cast(list[str], schema["required"])
    properties = cast(Mapping[str, object], schema["properties"])
    assert schema["type"] == "object"
    assert "raw_text" in required
    assert "fields" in properties


@pytest.mark.asyncio
async def test_openrouter_provider_parses_success_response_and_calls_fake_transport_once(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    transport = FakeOpenRouterHTTPTransport(
        response=_openrouter_response(
            content={"raw_text": {"text": "Extracted text."}, "fields": []},
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )
    )
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        transport=transport,
    )

    response = await provider.extract(_provider_request(image_path))

    assert len(transport.calls) == 1
    call = transport.calls[0]
    assert call.url == "https://openrouter.example/api/v1/chat/completions"
    assert call.timeout_seconds == 45
    assert call.headers["Authorization"] == "Bearer fake-openrouter-key"
    assert call.headers["HTTP-Referer"] == "https://example.test"
    assert call.headers["X-OpenRouter-Title"] == "test-app"
    assert "fake-openrouter-key" not in json.dumps(call.payload, sort_keys=True)
    assert response.provider_name == "openrouter"
    assert response.model_name == "openai/test-vision"
    raw_payload = cast(Mapping[str, object], response.raw_payload)
    raw_text = cast(Mapping[str, object], raw_payload["raw_text"])
    assert raw_text["text"] == "Extracted text."
    assert response.raw_text == "Extracted text."
    assert response.finish_reason == "stop"
    assert response.metadata["usage"] == {"prompt_tokens": 10, "completion_tokens": 20}
    assert response.metadata["provider"] == "openai"
    assert response.metadata["provider_response_id"] == "cmpl-test"
    assert not isinstance(response, ExtractionResult)


@pytest.mark.parametrize(
    ("status_code", "error_type"),
    [
        (401, ProviderAuthenticationError),
        (403, ProviderAuthenticationError),
        (429, ProviderRateLimitError),
        (500, ProviderUnavailableError),
        (400, ProviderRejectedRequestError),
        (422, ProviderRejectedRequestError),
    ],
)
@pytest.mark.asyncio
async def test_openrouter_provider_maps_http_errors(
    tmp_path: Path,
    status_code: int,
    error_type: type[Exception],
) -> None:
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        transport=FakeOpenRouterHTTPTransport(
            response=OpenRouterHTTPResponseData(status_code=status_code, body=b"{}")
        ),
    )

    with pytest.raises(error_type):
        await provider.extract(_provider_request(tmp_path / "original.jpg"))


@pytest.mark.parametrize(
    ("response", "error_match"),
    [
        (
            OpenRouterHTTPResponseData(status_code=200, body=b"not-json"),
            "not valid JSON",
        ),
        (
            OpenRouterHTTPResponseData(status_code=200, body=json.dumps({}).encode()),
            "missing choices",
        ),
        (
            OpenRouterHTTPResponseData(
                status_code=200,
                body=json.dumps({"choices": [{"message": {}}]}).encode(),
            ),
            "missing content",
        ),
        (
            OpenRouterHTTPResponseData(
                status_code=200,
                body=json.dumps(
                    {"choices": [{"message": {"content": "[]"}}]}
                ).encode(),
            ),
            "must be an object",
        ),
    ],
)
@pytest.mark.asyncio
async def test_openrouter_provider_maps_malformed_responses(
    tmp_path: Path,
    response: OpenRouterHTTPResponseData,
    error_match: str,
) -> None:
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        transport=FakeOpenRouterHTTPTransport(response=response),
    )

    with pytest.raises(ProviderMalformedResponseError, match=error_match):
        await provider.extract(_provider_request(tmp_path / "original.jpg"))


@pytest.mark.asyncio
async def test_openrouter_provider_maps_transport_timeout(
    tmp_path: Path,
) -> None:
    transport = FakeOpenRouterHTTPTransport(
        response=_openrouter_response(),
        error=TimeoutError("timed out"),
    )
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        transport=transport,
    )

    with pytest.raises(ProviderTimeoutError, match="timed out"):
        await provider.extract(_provider_request(tmp_path / "original.jpg"))

    assert len(transport.calls) == 1


@pytest.mark.parametrize(
    ("request_kwargs", "error_match"),
    [
        ({"prompt_package": None}, "prompt_package"),
        ({"schema_package": None}, "schema_package"),
        ({"staged_media": None}, "staged_media"),
        (
            {
                "staged_media": StagedMediaReference(
                    kind=StagedMediaReferenceKind.LOCAL_FILE,
                    value="C:/tmp/local.jpg",
                    mime_type="image/jpeg",
                    file_size_bytes=128,
                )
            },
            "PUBLIC_URL",
        ),
    ],
)
def test_openrouter_request_builder_rejects_unsupported_request_shape(
    tmp_path: Path,
    request_kwargs: Mapping[str, object],
    error_match: str,
) -> None:
    request = _provider_request(
        tmp_path / "original.jpg",
        staged_media=request_kwargs.get("staged_media", _UNSET),
        prompt_package=request_kwargs.get("prompt_package", _UNSET),
        schema_package=request_kwargs.get("schema_package", _UNSET),
    )

    with pytest.raises(ProviderRejectedRequestError, match=error_match):
        build_openrouter_chat_completion_payload(request)


def test_openrouter_factory_builds_explicit_adapter_with_fake_transport() -> None:
    transport = FakeOpenRouterHTTPTransport(response=_openrouter_response())
    provider = build_extraction_provider(
        ExtractionSettings(
            provider_name=ExtractionProviderName.OPENROUTER,
            model="openai/test-vision",
        ),
        openrouter_settings=_openrouter_settings(),
        openrouter_transport=transport,
    )

    assert isinstance(provider, OpenRouterExtractionProvider)


def test_openrouter_factory_rejects_placeholder_api_key_before_transport_call() -> None:
    transport = FakeOpenRouterHTTPTransport(response=_openrouter_response())

    with pytest.raises(ProviderAuthenticationError, match="OPENROUTER_API_KEY"):
        build_extraction_provider(
            ExtractionSettings(
                provider_name=ExtractionProviderName.OPENROUTER,
                model="openai/test-vision",
            ),
            openrouter_settings=OpenRouterSettings(),
            openrouter_transport=transport,
        )

    assert transport.calls == []


def test_fake_provider_factory_still_builds_without_openrouter_settings() -> None:
    provider = ExtractionProviderFactory(
        ExtractionSettings(provider_name=ExtractionProviderName.FAKE)
    ).build()

    assert isinstance(provider, FakeExtractionProvider)


@dataclass(frozen=True, slots=True)
class TransportCall:
    url: str
    headers: Mapping[str, str]
    payload: Mapping[str, object]
    timeout_seconds: int


@dataclass(slots=True)
class FakeOpenRouterHTTPTransport:
    response: OpenRouterHTTPResponseData
    calls: list[TransportCall] = field(default_factory=list)
    error: Exception | None = None

    def post_json(
        self,
        url: str,
        headers: Mapping[str, str],
        payload: Mapping[str, object],
        *,
        timeout_seconds: int,
    ) -> OpenRouterHTTPResponseData:
        self.calls.append(
            TransportCall(
                url=url,
                headers=dict(headers),
                payload=dict(payload),
                timeout_seconds=timeout_seconds,
            )
        )
        if self.error is not None:
            raise self.error
        return self.response


def _provider_request(
    image_path: Path,
    *,
    staged_media: object = _UNSET,
    prompt_package: object = _UNSET,
    schema_package: object = _UNSET,
    structured_outputs_enabled: bool = True,
    structured_outputs_require_parameters: bool = False,
) -> ExtractionProviderRequest:
    image_path = _write_image_bytes(image_path)
    context = _provider_context(
        image_path,
        structured_outputs_enabled=structured_outputs_enabled,
        structured_outputs_require_parameters=structured_outputs_require_parameters,
    )
    prompt = (
        build_extraction_prompt_package(context)
        if prompt_package is _UNSET
        else prompt_package
    )
    schema = (
        build_extraction_schema_package(context)
        if schema_package is _UNSET
        else schema_package
    )
    media = (
        StagedMediaReference(
            kind=StagedMediaReferenceKind.PUBLIC_URL,
            value="https://i.ibb.co/example/staged.jpg",
            mime_type="image/jpeg",
            file_size_bytes=image_path.stat().st_size,
        )
        if staged_media is _UNSET
        else staged_media
    )
    return ExtractionProviderRequest(
        correlation_id="job-001",
        context=context,
        staged_media=media,  # type: ignore[arg-type]
        prompt_package=prompt,  # type: ignore[arg-type]
        schema_package=schema,  # type: ignore[arg-type]
    )


def _provider_context(
    image_path: Path,
    *,
    structured_outputs_enabled: bool = True,
    structured_outputs_require_parameters: bool = False,
) -> ProviderInputContext:
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
            provider_name=ExtractionProviderName.OPENROUTER,
            model="openai/test-vision",
            temperature=0.2,
            timeout_seconds=45,
            max_retries=2,
            provider_schema_mode=ProviderSchemaMode.COMPACT,
            structured_outputs_enabled=structured_outputs_enabled,
            structured_outputs_require_parameters=structured_outputs_require_parameters,
        ),
    )


def _openrouter_settings() -> OpenRouterSettings:
    return OpenRouterSettings(
        api_key=SecretStr("fake-openrouter-key"),
        base_url="https://openrouter.example/api/v1",
        app_title="test-app",
        http_referer="https://example.test",
    )


def _openrouter_response(
    *,
    content: Mapping[str, object] | None = None,
    usage: Mapping[str, object] | None = None,
) -> OpenRouterHTTPResponseData:
    payload = {
        "id": "cmpl-test",
        "model": "openai/test-vision",
        "provider": "openai",
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        content or {"raw_text": {"text": "Extracted text."}}
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": dict(usage or {"prompt_tokens": 1, "completion_tokens": 2}),
    }
    return OpenRouterHTTPResponseData(
        status_code=200,
        body=json.dumps(payload).encode("utf-8"),
    )


def _user_content(payload: Mapping[str, object]) -> list[dict[str, object]]:
    messages = payload["messages"]
    assert isinstance(messages, list)
    user_message = messages[1]
    assert isinstance(user_message, Mapping)
    content = user_message["content"]
    assert isinstance(content, list)
    return cast(list[dict[str, object]], content)


def _write_image_bytes(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"fake-image-bytes")
    return path
