from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

from PIL import Image, ImageStat, UnidentifiedImageError

from document_digitization_ai.contracts import (
    IMAGE_DIAGNOSTICS_SCHEMA_VERSION,
    ImageDiagnostics,
    ImageFileMetadata,
    ImageQualityIndicators,
    ImageShape,
    Warning,
    WarningCode,
    WarningSeverity,
)


READ_CHUNK_SIZE_BYTES = 1024 * 1024
EXIF_ORIENTATION_TAG = 274


class ImageDiagnosticsError(RuntimeError):
    """Base error for hard image diagnostics rejection."""


class ImageDiagnosticsFileNotFoundError(ImageDiagnosticsError):
    """Raised when the input image path does not exist or is not a file."""


class ImageDiagnosticsInvalidImageError(ImageDiagnosticsError):
    """Raised when Pillow cannot open or decode the input as an image."""


class ImageDiagnosticsTooLargeError(ImageDiagnosticsError):
    """Raised when input file size exceeds configured hard limit."""


class ImageDiagnosticsTooSmallError(ImageDiagnosticsError):
    """Raised when decoded image dimensions are below configured hard minimum."""


@dataclass(frozen=True, slots=True)
class ImageDiagnosticsConfig:
    max_file_size_bytes: int = 20 * 1024 * 1024
    hard_min_width_px: int = 32
    hard_min_height_px: int = 32
    low_resolution_min_width_px: int = 800
    low_resolution_min_height_px: int = 800
    low_contrast_threshold: float = 16.0
    too_dark_brightness_threshold: float = 35.0
    too_bright_brightness_threshold: float = 220.0

    def __post_init__(self) -> None:
        _ensure_positive_int(self.max_file_size_bytes, "max_file_size_bytes")
        _ensure_positive_int(self.hard_min_width_px, "hard_min_width_px")
        _ensure_positive_int(self.hard_min_height_px, "hard_min_height_px")
        _ensure_positive_int(
            self.low_resolution_min_width_px,
            "low_resolution_min_width_px",
        )
        _ensure_positive_int(
            self.low_resolution_min_height_px,
            "low_resolution_min_height_px",
        )
        _ensure_brightness_metric(
            self.low_contrast_threshold,
            "low_contrast_threshold",
        )
        _ensure_brightness_metric(
            self.too_dark_brightness_threshold,
            "too_dark_brightness_threshold",
        )
        _ensure_brightness_metric(
            self.too_bright_brightness_threshold,
            "too_bright_brightness_threshold",
        )
        if self.too_dark_brightness_threshold >= self.too_bright_brightness_threshold:
            msg = (
                "too_dark_brightness_threshold must be lower than "
                "too_bright_brightness_threshold"
            )
            raise ValueError(msg)


def collect_image_diagnostics(
    image_path: str | Path,
    *,
    config: ImageDiagnosticsConfig | None = None,
) -> ImageDiagnostics:
    diagnostics_config = config or ImageDiagnosticsConfig()
    path = Path(image_path)
    if not path.is_file():
        msg = f"Image file does not exist: {path}"
        raise ImageDiagnosticsFileNotFoundError(msg)

    file_size_bytes = path.stat().st_size
    if file_size_bytes > diagnostics_config.max_file_size_bytes:
        msg = (
            f"Image file size {file_size_bytes} exceeds hard limit "
            f"{diagnostics_config.max_file_size_bytes}"
        )
        raise ImageDiagnosticsTooLargeError(msg)

    try:
        with Image.open(path) as image:
            image.load()
            width, height = image.size
            if (
                width < diagnostics_config.hard_min_width_px
                or height < diagnostics_config.hard_min_height_px
            ):
                msg = (
                    f"Image dimensions {width}x{height} are below hard minimum "
                    f"{diagnostics_config.hard_min_width_px}x"
                    f"{diagnostics_config.hard_min_height_px}"
                )
                raise ImageDiagnosticsTooSmallError(msg)

            image_format = image.format
            color_mode = image.mode
            mime_type = _mime_type_for_format(image_format)
            exif_orientation = _extract_exif_orientation(image)
            brightness, contrast = _measure_brightness_and_contrast(image)
    except ImageDiagnosticsTooSmallError:
        raise
    except (OSError, UnidentifiedImageError) as exc:
        msg = f"Image file cannot be opened as a valid image: {path}"
        raise ImageDiagnosticsInvalidImageError(msg) from exc

    is_low_resolution = (
        width < diagnostics_config.low_resolution_min_width_px
        or height < diagnostics_config.low_resolution_min_height_px
    )
    is_low_contrast = contrast < diagnostics_config.low_contrast_threshold
    warnings = _build_warnings(
        is_low_resolution=is_low_resolution,
        is_low_contrast=is_low_contrast,
        brightness=brightness,
        exif_orientation=exif_orientation,
        config=diagnostics_config,
    )

    return ImageDiagnostics(
        file=ImageFileMetadata(
            mime_type=mime_type,
            file_size_bytes=file_size_bytes,
            file_extension=path.suffix.lower() or "unknown",
            sha256=_sha256_file(path),
        ),
        image=ImageShape.from_dimensions(
            width=width,
            height=height,
            exif_orientation=exif_orientation,
            color_mode=color_mode,
            format=image_format,
        ),
        quality=ImageQualityIndicators(
            brightness=brightness,
            contrast=contrast,
            is_low_resolution=is_low_resolution,
            is_probably_blurry=None,
            is_low_contrast=is_low_contrast,
        ),
        warnings=warnings,
        metadata={
            "schema_version": IMAGE_DIAGNOSTICS_SCHEMA_VERSION,
            "diagnostics_version": "deterministic_image_v0",
        },
    )


def _build_warnings(
    *,
    is_low_resolution: bool,
    is_low_contrast: bool,
    brightness: float,
    exif_orientation: int | None,
    config: ImageDiagnosticsConfig,
) -> tuple[Warning, ...]:
    warnings: list[Warning] = []

    if is_low_resolution:
        warnings.append(
            Warning(
                code=WarningCode.LOW_RESOLUTION,
                message="Разрешение изображения ниже рекомендуемого порога.",
                target="image",
            )
        )
    if is_low_contrast:
        warnings.append(
            Warning(
                code=WarningCode.LOW_CONTRAST,
                message="Контраст изображения ниже рекомендуемого порога.",
                target="quality.contrast",
            )
        )
    if brightness < config.too_dark_brightness_threshold:
        warnings.append(
            Warning(
                code=WarningCode.TOO_DARK,
                message="Изображение выглядит слишком темным.",
                target="quality.brightness",
            )
        )
    if brightness > config.too_bright_brightness_threshold:
        warnings.append(
            Warning(
                code=WarningCode.TOO_BRIGHT,
                message="Изображение выглядит слишком светлым.",
                target="quality.brightness",
            )
        )
    if exif_orientation is not None:
        warnings.append(
            Warning(
                code=WarningCode.EXIF_ORIENTATION_PRESENT,
                message="В изображении найден EXIF orientation.",
                severity=WarningSeverity.INFO,
                target="image.exif_orientation",
            )
        )

    return tuple(warnings)


def _mime_type_for_format(image_format: str | None) -> str:
    if image_format is None:
        return "application/octet-stream"
    return Image.MIME.get(image_format, "application/octet-stream")


def _extract_exif_orientation(image: Image.Image) -> int | None:
    try:
        exif = image.getexif()
    except OSError:
        return None
    orientation = exif.get(EXIF_ORIENTATION_TAG)
    if isinstance(orientation, int):
        return orientation
    return None


def _measure_brightness_and_contrast(image: Image.Image) -> tuple[float, float]:
    grayscale = image.convert("L")
    try:
        statistics = ImageStat.Stat(grayscale)
        return statistics.mean[0], statistics.stddev[0]
    finally:
        grayscale.close()


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as image_file:
        for chunk in iter(lambda: image_file.read(READ_CHUNK_SIZE_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ensure_positive_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or value <= 0:
        msg = f"{field_name} must be a positive integer"
        raise ValueError(msg)


def _ensure_brightness_metric(value: float, field_name: str) -> None:
    if isinstance(value, bool) or value < 0 or value > 255:
        msg = f"{field_name} must be between 0 and 255"
        raise ValueError(msg)
