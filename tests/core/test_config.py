from pathlib import Path
from typing import Any, cast

import pytest
from pydantic import ValidationError

from document_digitization_ai.core import (
    AppSettings,
    MediaStagingBackend,
    ProviderSchemaMode,
    SettingsError,
    clear_settings_cache,
    get_settings,
)


SUPPORTED_ENV_NAMES = {
    "ENVIRONMENT",
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "OPENROUTER_MODEL",
    "OPENROUTER_APP_TITLE",
    "OPENROUTER_HTTP_REFERER",
    "LLM_TEMPERATURE",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "LLM_STRUCTURED_OUTPUTS_ENABLED",
    "LLM_STRUCTURED_OUTPUTS_REQUIRE_PARAMETERS",
    "LLM_PROVIDER_SCHEMA_MODE",
    "DATABASE_URL",
    "DATABASE_ECHO",
    "STORAGE_DATA_DIR",
    "STORAGE_UPLOADS_DIR",
    "STORAGE_RESULTS_DIR",
    "MEDIA_STAGING_BACKEND",
    "IMGBB_API_KEY",
    "MEDIA_STAGING_TTL_SECONDS",
    "MEDIA_STAGING_EXPIRY_SAFETY_SECONDS",
    "MEDIA_STAGING_VERIFY_DOWNLOAD",
    "MEDIA_STAGING_STRICT_VERIFY",
    "IMAGE_DIAGNOSTICS_MAX_FILE_SIZE_BYTES",
    "IMAGE_DIAGNOSTICS_HARD_MIN_WIDTH_PX",
    "IMAGE_DIAGNOSTICS_HARD_MIN_HEIGHT_PX",
    "IMAGE_DIAGNOSTICS_LOW_RESOLUTION_MIN_WIDTH_PX",
    "IMAGE_DIAGNOSTICS_LOW_RESOLUTION_MIN_HEIGHT_PX",
    "IMAGE_DIAGNOSTICS_LOW_CONTRAST_THRESHOLD",
    "IMAGE_DIAGNOSTICS_TOO_DARK_BRIGHTNESS_THRESHOLD",
    "IMAGE_DIAGNOSTICS_TOO_BRIGHT_BRIGHTNESS_THRESHOLD",
}


def test_app_settings_loads_without_real_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_supported_env(monkeypatch)

    settings = _app_settings_without_env_file()

    assert settings.environment.name == "local"
    assert settings.database.url == "sqlite+aiosqlite:///./data/app.db"
    assert settings.storage.data_dir == Path("data")
    assert settings.media_staging.backend is MediaStagingBackend.NONE
    assert settings.media_staging.require_imgbb_api_key() is None
    assert settings.extraction.provider_schema_mode is ProviderSchemaMode.COMPACT

    with pytest.raises(SettingsError, match="OPENROUTER_API_KEY"):
        settings.openrouter.require_api_key()
    with pytest.raises(SettingsError, match="OPENROUTER_MODEL"):
        settings.extraction.require_model_name()


def test_app_settings_reads_environment_into_grouped_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_supported_env(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", "sqlite+aiosqlite:///./tmp/test.db")
    monkeypatch.setenv("DATABASE_ECHO", "true")
    monkeypatch.setenv("STORAGE_DATA_DIR", "./tmp/data")
    monkeypatch.setenv("STORAGE_UPLOADS_DIR", "./tmp/uploads")
    monkeypatch.setenv("STORAGE_RESULTS_DIR", "./tmp/results")
    monkeypatch.setenv("OPENROUTER_API_KEY", "openrouter-real-key")
    monkeypatch.setenv("OPENROUTER_BASE_URL", "https://example.test/api")
    monkeypatch.setenv("OPENROUTER_MODEL", "openai/example-vision")
    monkeypatch.setenv("OPENROUTER_APP_TITLE", "test-app")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "")
    monkeypatch.setenv("LLM_TEMPERATURE", "0.25")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("LLM_MAX_RETRIES", "3")
    monkeypatch.setenv("LLM_STRUCTURED_OUTPUTS_ENABLED", "false")
    monkeypatch.setenv("LLM_STRUCTURED_OUTPUTS_REQUIRE_PARAMETERS", "true")
    monkeypatch.setenv("LLM_PROVIDER_SCHEMA_MODE", "full")

    settings = _app_settings_without_env_file()

    assert settings.environment.name == "test"
    assert settings.database.echo is True
    assert settings.storage.database_url == "sqlite+aiosqlite:///./tmp/test.db"
    assert settings.storage.uploads_dir == Path("tmp/uploads")
    assert settings.openrouter.require_api_key() == "openrouter-real-key"
    assert settings.openrouter.http_referer is None
    assert "openrouter-real-key" not in repr(settings.openrouter)
    assert settings.extraction.require_model_name() == "openai/example-vision"
    assert settings.extraction.temperature == 0.25
    assert settings.extraction.timeout_seconds == 45
    assert settings.extraction.max_retries == 3
    assert settings.extraction.structured_outputs_enabled is False
    assert settings.extraction.structured_outputs_require_parameters is True
    assert settings.llm_provider_schema_mode is ProviderSchemaMode.FULL
    assert settings.extraction.provider_schema_mode is ProviderSchemaMode.FULL


def test_media_staging_requires_imgbb_secret_only_for_imgbb(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_supported_env(monkeypatch)
    monkeypatch.setenv("MEDIA_STAGING_BACKEND", "none")
    monkeypatch.setenv("IMGBB_API_KEY", "change_me")

    none_settings = _app_settings_without_env_file().media_staging
    assert none_settings.require_imgbb_api_key() is None

    monkeypatch.setenv("MEDIA_STAGING_BACKEND", "imgbb")
    imgbb_settings = _app_settings_without_env_file().media_staging
    with pytest.raises(SettingsError, match="IMGBB_API_KEY"):
        imgbb_settings.require_imgbb_api_key()

    monkeypatch.setenv("IMGBB_API_KEY", "imgbb-real-key")
    imgbb_ready_settings = _app_settings_without_env_file().media_staging
    assert imgbb_ready_settings.require_imgbb_api_key() == "imgbb-real-key"
    assert imgbb_ready_settings.requires_imgbb_api_key() is True
    assert "imgbb-real-key" not in repr(imgbb_ready_settings)


def test_image_diagnostics_settings_build_existing_diagnostics_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_supported_env(monkeypatch)
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_MAX_FILE_SIZE_BYTES", "1024")
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_HARD_MIN_WIDTH_PX", "40")
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_HARD_MIN_HEIGHT_PX", "50")
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_LOW_RESOLUTION_MIN_WIDTH_PX", "900")
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_LOW_RESOLUTION_MIN_HEIGHT_PX", "1000")
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_LOW_CONTRAST_THRESHOLD", "12.5")
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_TOO_DARK_BRIGHTNESS_THRESHOLD", "30")
    monkeypatch.setenv("IMAGE_DIAGNOSTICS_TOO_BRIGHT_BRIGHTNESS_THRESHOLD", "230")

    diagnostics_config = (
        _app_settings_without_env_file().image_diagnostics.to_diagnostics_config()
    )

    assert diagnostics_config.max_file_size_bytes == 1024
    assert diagnostics_config.hard_min_width_px == 40
    assert diagnostics_config.hard_min_height_px == 50
    assert diagnostics_config.low_resolution_min_width_px == 900
    assert diagnostics_config.low_resolution_min_height_px == 1000
    assert diagnostics_config.low_contrast_threshold == 12.5
    assert diagnostics_config.too_dark_brightness_threshold == 30
    assert diagnostics_config.too_bright_brightness_threshold == 230


def test_app_settings_validates_invalid_numeric_runtime_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_supported_env(monkeypatch)
    monkeypatch.setenv("LLM_MAX_RETRIES", "-1")

    settings = _app_settings_without_env_file()

    with pytest.raises(ValidationError, match="max_retries"):
        _ = settings.extraction


def test_app_settings_rejects_invalid_provider_schema_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_supported_env(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER_SCHEMA_MODE", "strict")

    with pytest.raises(ValidationError, match="LLM_PROVIDER_SCHEMA_MODE"):
        _app_settings_without_env_file()


def test_get_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear_supported_env(monkeypatch)
    clear_settings_cache()
    monkeypatch.setenv("ENVIRONMENT", "cached-one")

    first = get_settings()
    monkeypatch.setenv("ENVIRONMENT", "cached-two")
    second = get_settings()

    assert first is second
    assert second.environment.name == "cached-one"
    clear_settings_cache()


def test_env_example_lists_supported_env_names() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")

    for env_name in SUPPORTED_ENV_NAMES:
        assert f"{env_name}=" in env_example


def _clear_supported_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in SUPPORTED_ENV_NAMES:
        monkeypatch.delenv(env_name, raising=False)


def _app_settings_without_env_file() -> AppSettings:
    settings_kwargs = cast(dict[str, Any], {"_env_file": None})
    return AppSettings(**settings_kwargs)
