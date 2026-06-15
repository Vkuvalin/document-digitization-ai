from typing import cast

import pytest
from pydantic import SecretStr

from document_digitization_ai.core import (
    ExtractionProviderName,
    ExtractionSettings,
    OpenRouterSettings,
)
from document_digitization_ai.extraction import (
    ExtractionProviderError,
    ExtractionProviderFactory,
    FakeExtractionProvider,
    OpenRouterExtractionProvider,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderMalformedResponseError,
    ProviderRateLimitError,
    ProviderRejectedRequestError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    build_extraction_provider,
)


PROVIDER_ERROR_TYPES = (
    ProviderConfigurationError,
    ProviderAuthenticationError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    ProviderMalformedResponseError,
    ProviderRejectedRequestError,
)


def test_provider_error_taxonomy_uses_sdk_free_base_error() -> None:
    for error_type in PROVIDER_ERROR_TYPES:
        error = error_type("provider boundary failure")

        assert isinstance(error, ExtractionProviderError)
        assert error.args == ("provider boundary failure",)


def test_provider_factory_selects_fake_provider_without_secrets_or_network() -> None:
    settings = ExtractionSettings()

    provider = build_extraction_provider(settings)

    assert isinstance(provider, FakeExtractionProvider)
    assert provider.provider_name == ExtractionProviderName.FAKE.value


def test_provider_factory_class_delegates_to_settings_provider_name() -> None:
    factory = ExtractionProviderFactory(
        ExtractionSettings(provider_name=ExtractionProviderName.FAKE)
    )

    assert isinstance(factory.build(), FakeExtractionProvider)


def test_provider_factory_requires_openrouter_settings_for_openrouter() -> None:
    settings = ExtractionSettings(provider_name=ExtractionProviderName.OPENROUTER)

    with pytest.raises(ProviderConfigurationError, match="OpenRouter settings"):
        build_extraction_provider(settings)


def test_provider_factory_builds_openrouter_with_explicit_settings() -> None:
    provider = build_extraction_provider(
        ExtractionSettings(
            provider_name=ExtractionProviderName.OPENROUTER,
            model="openai/test-vision",
        ),
        openrouter_settings=OpenRouterSettings(
            api_key=SecretStr("fake-openrouter-key"),
            base_url="https://openrouter.example/api/v1",
        ),
        openrouter_client=_NoopOpenRouterClient(),
    )

    assert isinstance(provider, OpenRouterExtractionProvider)


def test_provider_factory_rejects_openrouter_placeholder_key_before_client_call() -> None:
    client = _NoopOpenRouterClient()

    with pytest.raises(ProviderAuthenticationError, match="OPENROUTER_API_KEY"):
        build_extraction_provider(
            ExtractionSettings(
                provider_name=ExtractionProviderName.OPENROUTER,
                model="openai/test-vision",
            ),
            openrouter_settings=OpenRouterSettings(),
            openrouter_client=client,
        )

    assert client.called is False


def test_provider_factory_rejects_unsupported_provider_explicitly() -> None:
    settings = ExtractionSettings.model_construct(
        provider_name=cast(ExtractionProviderName, "unsupported"),
        model="change_me",
        temperature=0.1,
        timeout_seconds=60,
        max_retries=2,
        structured_outputs_enabled=True,
        structured_outputs_require_parameters=False,
    )

    with pytest.raises(ProviderConfigurationError, match="Unsupported extraction provider"):
        build_extraction_provider(settings)


def test_provider_factory_rejects_non_settings_input() -> None:
    with pytest.raises(ProviderConfigurationError, match="ExtractionSettings"):
        build_extraction_provider(object())  # type: ignore[arg-type]


class _NoopOpenRouterClient:
    called: bool = False

    async def create_chat_completion(
        self,
        **kwargs: object,
    ) -> object:
        self.called = True
        return object()
