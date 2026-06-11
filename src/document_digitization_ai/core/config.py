from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from document_digitization_ai.diagnostics import ImageDiagnosticsConfig


PLACEHOLDER_SECRET_VALUES = frozenset({"", "change_me"})
_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG = ImageDiagnosticsConfig()


class SettingsError(RuntimeError):
    """Raised when settings are insufficient for an explicit runtime action."""


class MediaStagingBackend(StrEnum):
    NONE = "none"
    IMGBB = "imgbb"


class ProviderSchemaMode(StrEnum):
    COMPACT = "compact"
    FULL = "full"


class EnvironmentSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = "local"

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "environment name must not be empty"
            raise ValueError(msg)
        return value


class DatabaseSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    echo: bool = False

    @field_validator("url")
    @classmethod
    def _validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "database url must not be empty"
            raise ValueError(msg)
        return value


class StorageSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    database_url: str
    data_dir: Path
    uploads_dir: Path
    results_dir: Path


class OpenRouterSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    api_key: SecretStr = Field(default=SecretStr("change_me"), repr=False)
    base_url: str = "https://openrouter.ai/api/v1"
    app_title: str = "document-digitization-ai"
    http_referer: str | None = None

    @field_validator("base_url", "app_title")
    @classmethod
    def _validate_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "setting must not be empty"
            raise ValueError(msg)
        return value

    @field_validator("http_referer", mode="before")
    @classmethod
    def _empty_referer_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def require_api_key(self) -> str:
        value = self.api_key.get_secret_value().strip()
        if _is_placeholder_secret(value):
            msg = "OPENROUTER_API_KEY must be set before provider calls"
            raise SettingsError(msg)
        return value


class ExtractionSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    model: str = "change_me"
    temperature: float = Field(default=0.1, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=60, gt=0)
    max_retries: int = Field(default=2, ge=0)
    structured_outputs_enabled: bool = True
    structured_outputs_require_parameters: bool = False
    provider_schema_mode: ProviderSchemaMode = ProviderSchemaMode.COMPACT

    @field_validator("model")
    @classmethod
    def _validate_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "setting must not be empty"
            raise ValueError(msg)
        return value

    def require_model_name(self) -> str:
        value = self.model.strip()
        if _is_placeholder_secret(value):
            msg = "OPENROUTER_MODEL must be set before provider calls"
            raise SettingsError(msg)
        return value


class MediaStagingSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    backend: MediaStagingBackend = MediaStagingBackend.NONE
    imgbb_api_key: SecretStr | None = Field(default=SecretStr("change_me"), repr=False)
    ttl_seconds: int = Field(default=3600, gt=0)
    expiry_safety_seconds: int = Field(default=60, ge=0)
    verify_download: bool = False
    strict_verify: bool = False

    def requires_imgbb_api_key(self) -> bool:
        return self.backend is MediaStagingBackend.IMGBB

    def require_imgbb_api_key(self) -> str | None:
        if not self.requires_imgbb_api_key():
            return None
        value = _secret_to_str(self.imgbb_api_key)
        if _is_placeholder_secret(value):
            msg = "IMGBB_API_KEY must be set when MEDIA_STAGING_BACKEND=imgbb"
            raise SettingsError(msg)
        return value


class ImageDiagnosticsSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_file_size_bytes: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.max_file_size_bytes,
        gt=0,
    )
    hard_min_width_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.hard_min_width_px,
        gt=0,
    )
    hard_min_height_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.hard_min_height_px,
        gt=0,
    )
    low_resolution_min_width_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.low_resolution_min_width_px,
        gt=0,
    )
    low_resolution_min_height_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.low_resolution_min_height_px,
        gt=0,
    )
    low_contrast_threshold: float = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.low_contrast_threshold,
        ge=0.0,
        le=255.0,
    )
    too_dark_brightness_threshold: float = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.too_dark_brightness_threshold,
        ge=0.0,
        le=255.0,
    )
    too_bright_brightness_threshold: float = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.too_bright_brightness_threshold,
        ge=0.0,
        le=255.0,
    )

    def to_diagnostics_config(self) -> ImageDiagnosticsConfig:
        return ImageDiagnosticsConfig(
            max_file_size_bytes=self.max_file_size_bytes,
            hard_min_width_px=self.hard_min_width_px,
            hard_min_height_px=self.hard_min_height_px,
            low_resolution_min_width_px=self.low_resolution_min_width_px,
            low_resolution_min_height_px=self.low_resolution_min_height_px,
            low_contrast_threshold=self.low_contrast_threshold,
            too_dark_brightness_threshold=self.too_dark_brightness_threshold,
            too_bright_brightness_threshold=self.too_bright_brightness_threshold,
        )


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
        validate_default=True,
    )

    environment_name: str = Field(default="local", validation_alias="ENVIRONMENT")
    database_url: str = Field(
        default="sqlite+aiosqlite:///./data/app.db",
        validation_alias="DATABASE_URL",
    )
    database_echo: bool = Field(default=False, validation_alias="DATABASE_ECHO")

    storage_data_dir: Path = Field(
        default=Path("./data"),
        validation_alias="STORAGE_DATA_DIR",
    )
    storage_uploads_dir: Path = Field(
        default=Path("./data/uploads"),
        validation_alias="STORAGE_UPLOADS_DIR",
    )
    storage_results_dir: Path = Field(
        default=Path("./data/results"),
        validation_alias="STORAGE_RESULTS_DIR",
    )

    openrouter_api_key: SecretStr = Field(
        default=SecretStr("change_me"),
        validation_alias="OPENROUTER_API_KEY",
        repr=False,
    )
    openrouter_base_url: str = Field(
        default="https://openrouter.ai/api/v1",
        validation_alias="OPENROUTER_BASE_URL",
    )
    openrouter_app_title: str = Field(
        default="document-digitization-ai",
        validation_alias="OPENROUTER_APP_TITLE",
    )
    openrouter_http_referer: str | None = Field(
        default=None,
        validation_alias="OPENROUTER_HTTP_REFERER",
    )

    llm_model: str = Field(default="change_me", validation_alias="OPENROUTER_MODEL")
    llm_temperature: float = Field(default=0.1, validation_alias="LLM_TEMPERATURE")
    llm_timeout_seconds: int = Field(
        default=60,
        validation_alias="LLM_TIMEOUT_SECONDS",
    )
    llm_max_retries: int = Field(default=2, validation_alias="LLM_MAX_RETRIES")
    llm_structured_outputs_enabled: bool = Field(
        default=True,
        validation_alias="LLM_STRUCTURED_OUTPUTS_ENABLED",
    )
    llm_structured_outputs_require_parameters: bool = Field(
        default=False,
        validation_alias="LLM_STRUCTURED_OUTPUTS_REQUIRE_PARAMETERS",
    )
    llm_provider_schema_mode: ProviderSchemaMode = Field(
        default=ProviderSchemaMode.COMPACT,
        validation_alias="LLM_PROVIDER_SCHEMA_MODE",
    )

    media_staging_backend: MediaStagingBackend = Field(
        default=MediaStagingBackend.NONE,
        validation_alias="MEDIA_STAGING_BACKEND",
    )
    imgbb_api_key: SecretStr | None = Field(
        default=SecretStr("change_me"),
        validation_alias="IMGBB_API_KEY",
        repr=False,
    )
    media_staging_ttl_seconds: int = Field(
        default=3600,
        validation_alias="MEDIA_STAGING_TTL_SECONDS",
    )
    media_staging_expiry_safety_seconds: int = Field(
        default=60,
        validation_alias="MEDIA_STAGING_EXPIRY_SAFETY_SECONDS",
    )
    media_staging_verify_download: bool = Field(
        default=False,
        validation_alias="MEDIA_STAGING_VERIFY_DOWNLOAD",
    )
    media_staging_strict_verify: bool = Field(
        default=False,
        validation_alias="MEDIA_STAGING_STRICT_VERIFY",
    )

    image_diagnostics_max_file_size_bytes: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.max_file_size_bytes,
        validation_alias="IMAGE_DIAGNOSTICS_MAX_FILE_SIZE_BYTES",
    )
    image_diagnostics_hard_min_width_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.hard_min_width_px,
        validation_alias="IMAGE_DIAGNOSTICS_HARD_MIN_WIDTH_PX",
    )
    image_diagnostics_hard_min_height_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.hard_min_height_px,
        validation_alias="IMAGE_DIAGNOSTICS_HARD_MIN_HEIGHT_PX",
    )
    image_diagnostics_low_resolution_min_width_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.low_resolution_min_width_px,
        validation_alias="IMAGE_DIAGNOSTICS_LOW_RESOLUTION_MIN_WIDTH_PX",
    )
    image_diagnostics_low_resolution_min_height_px: int = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.low_resolution_min_height_px,
        validation_alias="IMAGE_DIAGNOSTICS_LOW_RESOLUTION_MIN_HEIGHT_PX",
    )
    image_diagnostics_low_contrast_threshold: float = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.low_contrast_threshold,
        validation_alias="IMAGE_DIAGNOSTICS_LOW_CONTRAST_THRESHOLD",
    )
    image_diagnostics_too_dark_brightness_threshold: float = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.too_dark_brightness_threshold,
        validation_alias="IMAGE_DIAGNOSTICS_TOO_DARK_BRIGHTNESS_THRESHOLD",
    )
    image_diagnostics_too_bright_brightness_threshold: float = Field(
        default=_DEFAULT_IMAGE_DIAGNOSTICS_CONFIG.too_bright_brightness_threshold,
        validation_alias="IMAGE_DIAGNOSTICS_TOO_BRIGHT_BRIGHTNESS_THRESHOLD",
    )

    @field_validator("openrouter_http_referer", mode="before")
    @classmethod
    def _empty_referer_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def environment(self) -> EnvironmentSettings:
        return EnvironmentSettings(name=self.environment_name)

    @property
    def database(self) -> DatabaseSettings:
        return DatabaseSettings(url=self.database_url, echo=self.database_echo)

    @property
    def storage(self) -> StorageSettings:
        return StorageSettings(
            database_url=self.database_url,
            data_dir=self.storage_data_dir,
            uploads_dir=self.storage_uploads_dir,
            results_dir=self.storage_results_dir,
        )

    @property
    def openrouter(self) -> OpenRouterSettings:
        return OpenRouterSettings(
            api_key=self.openrouter_api_key,
            base_url=self.openrouter_base_url,
            app_title=self.openrouter_app_title,
            http_referer=self.openrouter_http_referer,
        )

    @property
    def extraction(self) -> ExtractionSettings:
        return ExtractionSettings(
            model=self.llm_model,
            temperature=self.llm_temperature,
            timeout_seconds=self.llm_timeout_seconds,
            max_retries=self.llm_max_retries,
            structured_outputs_enabled=self.llm_structured_outputs_enabled,
            structured_outputs_require_parameters=(
                self.llm_structured_outputs_require_parameters
            ),
            provider_schema_mode=self.llm_provider_schema_mode,
        )

    @property
    def media_staging(self) -> MediaStagingSettings:
        return MediaStagingSettings(
            backend=self.media_staging_backend,
            imgbb_api_key=self.imgbb_api_key,
            ttl_seconds=self.media_staging_ttl_seconds,
            expiry_safety_seconds=self.media_staging_expiry_safety_seconds,
            verify_download=self.media_staging_verify_download,
            strict_verify=self.media_staging_strict_verify,
        )

    @property
    def image_diagnostics(self) -> ImageDiagnosticsSettings:
        return ImageDiagnosticsSettings(
            max_file_size_bytes=self.image_diagnostics_max_file_size_bytes,
            hard_min_width_px=self.image_diagnostics_hard_min_width_px,
            hard_min_height_px=self.image_diagnostics_hard_min_height_px,
            low_resolution_min_width_px=(
                self.image_diagnostics_low_resolution_min_width_px
            ),
            low_resolution_min_height_px=(
                self.image_diagnostics_low_resolution_min_height_px
            ),
            low_contrast_threshold=self.image_diagnostics_low_contrast_threshold,
            too_dark_brightness_threshold=(
                self.image_diagnostics_too_dark_brightness_threshold
            ),
            too_bright_brightness_threshold=(
                self.image_diagnostics_too_bright_brightness_threshold
            ),
        )


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    return AppSettings()


def clear_settings_cache() -> None:
    get_settings.cache_clear()


def _secret_to_str(secret: SecretStr | None) -> str:
    if secret is None:
        return ""
    return secret.get_secret_value().strip()


def _is_placeholder_secret(value: str) -> bool:
    return value.strip() in PLACEHOLDER_SECRET_VALUES
