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
    build_openrouter_chat_completion_kwargs,
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


def test_openrouter_kwargs_use_public_url_without_private_data(
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

    kwargs = build_openrouter_chat_completion_kwargs(
        request,
        app_title="test-app",
        http_referer="https://example.test",
    )
    serialized_kwargs = json.dumps(kwargs, sort_keys=True)
    user_content = _user_content(kwargs)
    extra_headers = cast(Mapping[str, object], kwargs["extra_headers"])

    assert kwargs["model"] == "openai/test-vision"
    assert kwargs["temperature"] == 0.2
    assert kwargs["timeout"] == 45
    assert user_content[0]["type"] == "text"
    user_text = cast(str, user_content[0]["text"])
    assert (
        "Provider output top-level sections: document, raw_text, fields, tables, "
        "blocks, warnings, metadata."
    ) in user_text
    assert "Expected top-level sections: document, image_diagnostics" not in user_text
    assert (
        "use image_diagnostics only as guidance and do not include these sections "
        "in provider output"
    ) in user_text
    assert user_content[1]["type"] == "image_url"
    image_url = cast(Mapping[str, object], user_content[1]["image_url"])
    assert image_url["url"] == "https://i.ibb.co/example/staged.jpg"
    assert image_url["detail"] == "high"
    assert extra_headers["HTTP-Referer"] == "https://example.test"
    assert extra_headers["X-Title"] == "test-app"
    assert str(image_path) not in serialized_kwargs
    assert "delete-private-token" not in serialized_kwargs
    assert "private_cleanup" not in serialized_kwargs
    assert "fake-openrouter-key" not in serialized_kwargs
    assert "Authorization" not in serialized_kwargs


def test_openrouter_kwargs_add_provider_require_parameters_when_enabled(
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

    kwargs = build_openrouter_chat_completion_kwargs(request)
    serialized_kwargs = json.dumps(kwargs, sort_keys=True)

    extra_body = cast(Mapping[str, object], kwargs["extra_body"])
    provider_payload = cast(Mapping[str, object], extra_body["provider"])
    assert provider_payload["require_parameters"] is True
    assert str(image_path) not in serialized_kwargs
    assert "fake-openrouter-key" not in serialized_kwargs
    assert "delete_url" not in serialized_kwargs
    assert "delete-private-token" not in serialized_kwargs
    assert "private-delete" not in serialized_kwargs


def test_openrouter_kwargs_omit_provider_require_parameters_when_disabled(
    tmp_path: Path,
) -> None:
    request = _provider_request(
        tmp_path / "original.jpg",
        structured_outputs_require_parameters=False,
    )

    kwargs = build_openrouter_chat_completion_kwargs(request)

    assert "extra_body" not in kwargs


@pytest.mark.asyncio
async def test_openrouter_provider_rejects_disabled_structured_outputs_before_client_call(
    tmp_path: Path,
) -> None:
    client = FakeOpenRouterChatCompletionClient(response=_openrouter_response())
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=client,
    )
    request = _provider_request(
        tmp_path / "original.jpg",
        structured_outputs_enabled=False,
    )

    with pytest.raises(ProviderConfigurationError, match="structured outputs"):
        build_openrouter_chat_completion_kwargs(request)

    with pytest.raises(ProviderConfigurationError, match="structured outputs"):
        await provider.extract(request)

    assert client.calls == []


def test_openrouter_response_format_maps_provider_neutral_schema(
    tmp_path: Path,
) -> None:
    request = _provider_request(tmp_path / "original.jpg")
    assert request.schema_package is not None
    package_payload = request.schema_package.to_dict()
    schema_required = cast(list[str], package_payload["required_sections"])
    assert "image_diagnostics" in schema_required

    response_format = build_openrouter_response_format(package_payload)

    assert response_format["type"] == "json_schema"
    json_schema = cast(Mapping[str, object], response_format["json_schema"])
    assert json_schema["name"] == "document_extraction_result_v0"
    assert json_schema["strict"] is True
    schema = cast(Mapping[str, object], json_schema["schema"])
    required = cast(list[str], schema["required"])
    properties = cast(Mapping[str, object], schema["properties"])
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert properties
    assert set(required) == {
        "document",
        "raw_text",
        "fields",
        "tables",
        "blocks",
        "warnings",
        "metadata",
    }
    assert set(properties) == set(required)
    assert "image_diagnostics" not in required
    assert "image_diagnostics" not in properties
    json.dumps(response_format, sort_keys=True)


def test_openrouter_response_format_preserves_diagnostics_context_for_prompt(
    tmp_path: Path,
) -> None:
    request = _provider_request(tmp_path / "original.jpg")
    assert request.prompt_package is not None
    assert request.schema_package is not None
    assert request.context.diagnostics.diagnostics_present is True

    schema_payload = request.schema_package.to_dict()
    prompt_payload = request.prompt_package.to_dict()
    schema_required = cast(list[str], schema_payload["required_sections"])
    diagnostics_guidance = cast(list[str], prompt_payload["diagnostics_guidance"])

    assert "image_diagnostics" in schema_required
    assert any("diagnostics" in item.lower() for item in diagnostics_guidance)


def test_openrouter_response_format_uses_explicit_nested_section_schemas(
    tmp_path: Path,
) -> None:
    request = _provider_request(tmp_path / "original.jpg")
    assert request.schema_package is not None

    schema = _provider_response_schema(request.schema_package.to_dict())
    properties = _properties(schema)

    _assert_explicit_object_schema(properties["document"])
    _assert_explicit_object_schema(properties["raw_text"])
    _assert_explicit_object_schema(properties["metadata"])
    assert "image_diagnostics" not in properties
    assert "text" in _properties(properties["raw_text"])
    assert "schema_version" in _properties(properties["metadata"])

    for section in ("fields", "tables", "blocks", "warnings"):
        section_schema = cast(Mapping[str, object], properties[section])
        assert section_schema["type"] == "array"
        _assert_explicit_object_schema(section_schema["items"])

    field_properties = _properties(_array_items(properties["fields"]))
    table_properties = _properties(_array_items(properties["tables"]))
    block_properties = _properties(_array_items(properties["blocks"]))
    warning_properties = _properties(_array_items(properties["warnings"]))

    assert {"label", "value", "confidence", "source", "warnings"} <= set(
        field_properties
    )
    assert {"title", "columns", "rows", "confidence", "warnings"} <= set(
        table_properties
    )
    assert {"type", "text", "order", "level", "confidence", "warnings"} <= set(
        block_properties
    )
    assert {"code", "message", "severity", "target"} <= set(warning_properties)


def test_openrouter_response_format_has_no_shallow_known_object_sections(
    tmp_path: Path,
) -> None:
    request = _provider_request(tmp_path / "original.jpg")
    assert request.schema_package is not None

    schema = _provider_response_schema(request.schema_package.to_dict())
    properties = _properties(schema)

    known_object_sections = (
        properties["document"],
        properties["raw_text"],
        properties["metadata"],
        _array_items(properties["fields"]),
        _array_items(properties["tables"]),
        _array_items(properties["blocks"]),
        _array_items(properties["warnings"]),
    )
    for section_schema in known_object_sections:
        assert section_schema != {"type": "object"}
        _assert_explicit_object_schema(section_schema)


def test_openrouter_response_format_compact_and_full_modes_affect_provider_schema(
    tmp_path: Path,
) -> None:
    compact_request = _provider_request(
        tmp_path / "compact.jpg",
        provider_schema_mode=ProviderSchemaMode.COMPACT,
    )
    full_request = _provider_request(
        tmp_path / "full.jpg",
        provider_schema_mode=ProviderSchemaMode.FULL,
    )
    assert compact_request.schema_package is not None
    assert full_request.schema_package is not None

    compact_schema = _provider_response_schema(compact_request.schema_package.to_dict())
    full_schema = _provider_response_schema(full_request.schema_package.to_dict())

    assert compact_schema != full_schema
    assert _contains_key(full_schema, "description")
    assert not _contains_key(compact_schema, "description")
    assert _properties(compact_schema).keys() == _properties(full_schema).keys()


def test_openrouter_response_format_consumes_schema_package_payload(
    tmp_path: Path,
) -> None:
    request = _provider_request(tmp_path / "original.jpg")
    assert request.schema_package is not None
    package_payload = dict(request.schema_package.to_dict())
    schema_payload = dict(cast(Mapping[str, object], package_payload["schema_payload"]))
    schema_payload["schema_detail"] = "full"
    package_payload["schema_payload"] = schema_payload

    with pytest.raises(ProviderRejectedRequestError, match="schema_detail"):
        build_openrouter_response_format(package_payload)


@pytest.mark.asyncio
async def test_openrouter_provider_parses_success_response_and_calls_fake_client_once(
    tmp_path: Path,
) -> None:
    image_path = _write_image_bytes(tmp_path / "original.jpg")
    client = FakeOpenRouterChatCompletionClient(
        response=_openrouter_response(
            content={"raw_text": {"text": "Extracted text."}, "fields": []},
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )
    )
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=client,
    )

    response = await provider.extract(_provider_request(image_path))

    assert len(client.calls) == 1
    call = client.calls[0]
    assert call.kwargs["model"] == "openai/test-vision"
    assert call.kwargs["timeout"] == 45
    assert "Authorization" not in json.dumps(call.kwargs, sort_keys=True)
    assert "fake-openrouter-key" not in json.dumps(call.kwargs, sort_keys=True)
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
    assert response.raw_response_json is not None
    raw_response = cast(Mapping[str, object], response.raw_response_json)
    assert raw_response["id"] == "cmpl-test"
    assert "choices" in raw_response
    assert not isinstance(response, ExtractionResult)


@pytest.mark.asyncio
async def test_openrouter_provider_parses_list_content_response(
    tmp_path: Path,
) -> None:
    client = FakeOpenRouterChatCompletionClient(
        response=_openrouter_response(
            content=[
                {
                    "type": "text",
                    "text": json.dumps({"raw_text": {"text": "List content text."}}),
                }
            ],
        )
    )
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=client,
    )

    response = await provider.extract(_provider_request(tmp_path / "original.jpg"))

    assert response.raw_text == "List content text."


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
async def test_openrouter_provider_maps_sdk_status_errors(
    tmp_path: Path,
    status_code: int,
    error_type: type[Exception],
) -> None:
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=FakeOpenRouterChatCompletionClient(
            response=_openrouter_response(),
            error=FakeSDKError(status_code=status_code, body={}),
        ),
    )

    with pytest.raises(error_type):
        await provider.extract(_provider_request(tmp_path / "original.jpg"))


@pytest.mark.asyncio
async def test_openrouter_provider_includes_sdk_error_message_for_rejected_request(
    tmp_path: Path,
) -> None:
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=FakeOpenRouterChatCompletionClient(
            response=_openrouter_response(),
            error=FakeSDKError(
                status_code=400,
                body={"error": {"message": "Invalid schema for response_format."}},
            ),
        ),
    )

    with pytest.raises(ProviderRejectedRequestError, match="Invalid schema"):
        await provider.extract(_provider_request(tmp_path / "original.jpg"))


@pytest.mark.asyncio
async def test_openrouter_provider_redacts_secrets_from_sdk_error_message(
    tmp_path: Path,
) -> None:
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=FakeOpenRouterChatCompletionClient(
            response=_openrouter_response(),
            error=FakeSDKError(
                status_code=400,
                body={
                    "message": (
                        "Invalid Authorization: Bearer fake-openrouter-key; "
                        "api_key=fake-openrouter-key"
                    )
                },
            ),
        ),
    )

    with pytest.raises(ProviderRejectedRequestError) as exc_info:
        await provider.extract(_provider_request(tmp_path / "original.jpg"))

    message = str(exc_info.value)
    assert "fake-openrouter-key" not in message
    assert "<redacted>" in message


@pytest.mark.parametrize(
    ("response_case", "error_match"),
    [
        ("empty_choices", "missing choices"),
        ("missing_message", "missing message"),
        ("missing_content", "missing content"),
        ("invalid_json", "not valid JSON"),
        ("empty_list_content", "missing content"),
        ("non_object_json", "must be an object"),
    ],
)
@pytest.mark.asyncio
async def test_openrouter_provider_maps_malformed_responses(
    tmp_path: Path,
    response_case: str,
    error_match: str,
) -> None:
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=FakeOpenRouterChatCompletionClient(
            response=_malformed_response(response_case)
        ),
    )

    with pytest.raises(ProviderMalformedResponseError, match=error_match):
        await provider.extract(_provider_request(tmp_path / "original.jpg"))


@pytest.mark.asyncio
async def test_openrouter_provider_maps_client_timeout(
    tmp_path: Path,
) -> None:
    client = FakeOpenRouterChatCompletionClient(
        response=_openrouter_response(),
        error=TimeoutError("timed out"),
    )
    provider = OpenRouterExtractionProvider.from_settings(
        _openrouter_settings(),
        client=client,
    )

    with pytest.raises(ProviderTimeoutError, match="timed out|timed out"):
        await provider.extract(_provider_request(tmp_path / "original.jpg"))

    assert len(client.calls) == 1


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
        build_openrouter_chat_completion_kwargs(request)


def test_openrouter_factory_builds_explicit_adapter_with_fake_client() -> None:
    client = FakeOpenRouterChatCompletionClient(response=_openrouter_response())
    provider = build_extraction_provider(
        ExtractionSettings(
            provider_name=ExtractionProviderName.OPENROUTER,
            model="openai/test-vision",
        ),
        openrouter_settings=_openrouter_settings(),
        openrouter_client=client,
    )

    assert isinstance(provider, OpenRouterExtractionProvider)


def test_openrouter_factory_rejects_placeholder_api_key_before_client_call() -> None:
    client = FakeOpenRouterChatCompletionClient(response=_openrouter_response())

    with pytest.raises(ProviderAuthenticationError, match="OPENROUTER_API_KEY"):
        build_extraction_provider(
            ExtractionSettings(
                provider_name=ExtractionProviderName.OPENROUTER,
                model="openai/test-vision",
            ),
            openrouter_settings=OpenRouterSettings(),
            openrouter_client=client,
        )

    assert client.calls == []


def test_fake_provider_factory_still_builds_without_openrouter_settings() -> None:
    provider = ExtractionProviderFactory(
        ExtractionSettings(provider_name=ExtractionProviderName.FAKE)
    ).build()

    assert isinstance(provider, FakeExtractionProvider)


@dataclass(frozen=True, slots=True)
class ClientCall:
    kwargs: Mapping[str, object]


@dataclass(slots=True)
class FakeOpenRouterChatCompletionClient:
    response: object
    calls: list[ClientCall] = field(default_factory=list)
    error: Exception | None = None

    async def create_chat_completion(self, **kwargs: object) -> object:
        self.calls.append(ClientCall(kwargs=dict(kwargs)))
        if self.error is not None:
            raise self.error
        return self.response


class FakeSDKError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        body: object | None = None,
        message: str = "fake sdk error",
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body
        self.message = message


@dataclass(frozen=True, slots=True)
class FakeCompletionMessage:
    content: object


@dataclass(frozen=True, slots=True)
class FakeCompletionChoice:
    message: FakeCompletionMessage | None
    finish_reason: str | None = "stop"


@dataclass(frozen=True, slots=True)
class FakeUsage:
    prompt_tokens: int
    completion_tokens: int

    def model_dump(self) -> dict[str, object]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
        }


@dataclass(frozen=True, slots=True)
class FakeCompletionResponse:
    choices: list[FakeCompletionChoice]
    model: str = "openai/test-vision"
    id: str = "cmpl-test"
    provider: str | None = "openai"
    usage: object | None = None


def _provider_request(
    image_path: Path,
    *,
    staged_media: object = _UNSET,
    prompt_package: object = _UNSET,
    schema_package: object = _UNSET,
    structured_outputs_enabled: bool = True,
    structured_outputs_require_parameters: bool = False,
    provider_schema_mode: ProviderSchemaMode = ProviderSchemaMode.COMPACT,
) -> ExtractionProviderRequest:
    image_path = _write_image_bytes(image_path)
    context = _provider_context(
        image_path,
        structured_outputs_enabled=structured_outputs_enabled,
        structured_outputs_require_parameters=structured_outputs_require_parameters,
        provider_schema_mode=provider_schema_mode,
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
    provider_schema_mode: ProviderSchemaMode = ProviderSchemaMode.COMPACT,
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
            provider_schema_mode=provider_schema_mode,
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
    content: object = _UNSET,
    usage: Mapping[str, object] | None = None,
    choices: list[FakeCompletionChoice] | None = None,
    message: FakeCompletionMessage | None | object = _UNSET,
) -> FakeCompletionResponse:
    if choices is None:
        if message is _UNSET:
            if content is _UNSET:
                content = {"raw_text": {"text": "Extracted text."}}
            if isinstance(content, Mapping):
                content = json.dumps(content)
            message = FakeCompletionMessage(content=content)
        choice_message = (
            cast(FakeCompletionMessage | None, message)
            if message is not _UNSET
            else None
        )
        choices = [FakeCompletionChoice(message=choice_message)]
    usage_payload: object | None = None
    if usage is not None:
        usage_payload = dict(usage)
    else:
        usage_payload = FakeUsage(prompt_tokens=1, completion_tokens=2)
    return FakeCompletionResponse(choices=choices, usage=usage_payload)


def _malformed_response(response_case: str) -> FakeCompletionResponse:
    if response_case == "empty_choices":
        return _openrouter_response(choices=[])
    if response_case == "missing_message":
        return _openrouter_response(message=None)
    if response_case == "missing_content":
        return _openrouter_response(content=None)
    if response_case == "invalid_json":
        return _openrouter_response(content="not-json")
    if response_case == "empty_list_content":
        return _openrouter_response(content=[])
    if response_case == "non_object_json":
        return _openrouter_response(content="[]")
    raise AssertionError(f"Unknown malformed response case: {response_case}")


def _user_content(kwargs: Mapping[str, object]) -> list[dict[str, object]]:
    messages = kwargs["messages"]
    assert isinstance(messages, list)
    user_message = messages[1]
    assert isinstance(user_message, Mapping)
    content = user_message["content"]
    assert isinstance(content, list)
    return cast(list[dict[str, object]], content)


def _provider_response_schema(
    schema_package_payload: Mapping[str, object],
) -> Mapping[str, object]:
    response_format = build_openrouter_response_format(schema_package_payload)
    json_schema = cast(Mapping[str, object], response_format["json_schema"])
    return cast(Mapping[str, object], json_schema["schema"])


def _properties(schema: object) -> Mapping[str, object]:
    assert isinstance(schema, Mapping)
    properties = schema["properties"]
    assert isinstance(properties, Mapping)
    return cast(Mapping[str, object], properties)


def _array_items(schema: object) -> Mapping[str, object]:
    assert isinstance(schema, Mapping)
    items = schema["items"]
    assert isinstance(items, Mapping)
    return cast(Mapping[str, object], items)


def _assert_explicit_object_schema(schema: object) -> None:
    assert isinstance(schema, Mapping)
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert isinstance(schema["required"], list)
    assert _properties(schema)


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(_contains_key(item, key) for item in value.values())
    if isinstance(value, list):
        return any(_contains_key(item, key) for item in value)
    return False


def _write_image_bytes(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(b"fake-image-bytes")
    return path
