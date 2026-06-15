from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from document_digitization_ai.core import (
    ExtractionProviderName,
    ExtractionSettings,
    OpenRouterSettings,
)
from document_digitization_ai.extraction.fake import FakeExtractionProvider
from document_digitization_ai.extraction.provider import (
    ExtractionProviderPort,
    ProviderConfigurationError,
)

if TYPE_CHECKING:
    from document_digitization_ai.extraction.openrouter import (
        OpenRouterChatCompletionClient,
    )


@dataclass(frozen=True, slots=True)
class ExtractionProviderFactory:
    settings: ExtractionSettings
    openrouter_settings: OpenRouterSettings | None = None
    openrouter_client: OpenRouterChatCompletionClient | None = None

    def build(self) -> ExtractionProviderPort:
        return build_extraction_provider(
            self.settings,
            openrouter_settings=self.openrouter_settings,
            openrouter_client=self.openrouter_client,
        )


def build_extraction_provider(
    settings: ExtractionSettings,
    *,
    openrouter_settings: OpenRouterSettings | None = None,
    openrouter_client: OpenRouterChatCompletionClient | None = None,
) -> ExtractionProviderPort:
    if not isinstance(settings, ExtractionSettings):
        msg = "settings must be an ExtractionSettings value"
        raise ProviderConfigurationError(msg)
    provider_name = _coerce_provider_name(settings.provider_name)
    if provider_name is ExtractionProviderName.FAKE:
        return FakeExtractionProvider()
    if provider_name is ExtractionProviderName.OPENROUTER:
        if openrouter_settings is None:
            msg = "OpenRouter settings are required for openrouter extraction provider"
            raise ProviderConfigurationError(msg)
        from document_digitization_ai.extraction.openrouter import (
            OpenRouterExtractionProvider,
        )

        return OpenRouterExtractionProvider.from_settings(
            openrouter_settings,
            client=openrouter_client,
        )
    msg = f"Unsupported extraction provider: {provider_name}"
    raise ProviderConfigurationError(msg)


def _coerce_provider_name(value: object) -> ExtractionProviderName:
    if isinstance(value, ExtractionProviderName):
        return value
    if isinstance(value, str):
        try:
            return ExtractionProviderName(value.strip().lower())
        except ValueError as exc:
            msg = f"Unsupported extraction provider: {value}"
            raise ProviderConfigurationError(msg) from exc
    msg = "extraction provider name must be a string or ExtractionProviderName value"
    raise ProviderConfigurationError(msg)
