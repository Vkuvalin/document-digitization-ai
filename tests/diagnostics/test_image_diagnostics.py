from pathlib import Path

import pytest
from PIL import Image

from document_digitization_ai.contracts import WarningCode
from document_digitization_ai.diagnostics import (
    ImageDiagnosticsConfig,
    ImageDiagnosticsFileNotFoundError,
    ImageDiagnosticsInvalidImageError,
    ImageDiagnosticsTooLargeError,
    ImageDiagnosticsTooSmallError,
    collect_image_diagnostics,
)


def test_collect_image_diagnostics_for_valid_jpeg(tmp_path: Path) -> None:
    image_path = tmp_path / "document.jpg"
    _save_rgb_image(image_path, size=(1200, 1600), color=(128, 128, 128))

    diagnostics = collect_image_diagnostics(image_path)

    assert diagnostics.file.mime_type == "image/jpeg"
    assert diagnostics.file.file_extension == ".jpg"
    assert diagnostics.file.file_size_bytes == image_path.stat().st_size
    assert diagnostics.file.sha256 is not None
    assert len(diagnostics.file.sha256) == 64
    assert diagnostics.image.width == 1200
    assert diagnostics.image.height == 1600
    assert diagnostics.image.orientation.value == "portrait"
    assert diagnostics.image.aspect_ratio == pytest.approx(1200 / 1600)
    assert diagnostics.image.color_mode == "RGB"
    assert diagnostics.image.format == "JPEG"
    assert diagnostics.quality.brightness == pytest.approx(128.0)
    assert diagnostics.quality.contrast == pytest.approx(0.0)
    assert diagnostics.metadata["diagnostics_version"] == "deterministic_image_v0"


def test_collect_image_diagnostics_emits_quality_warnings(tmp_path: Path) -> None:
    image_path = tmp_path / "small_dark.png"
    _save_rgb_image(image_path, size=(120, 100), color=(10, 10, 10))

    diagnostics = collect_image_diagnostics(
        image_path,
        config=ImageDiagnosticsConfig(
            hard_min_width_px=32,
            hard_min_height_px=32,
            low_resolution_min_width_px=800,
            low_resolution_min_height_px=800,
            low_contrast_threshold=16.0,
            too_dark_brightness_threshold=35.0,
        ),
    )

    assert diagnostics.quality.is_low_resolution is True
    assert diagnostics.quality.is_low_contrast is True
    assert [warning.code for warning in diagnostics.warnings] == [
        WarningCode.LOW_RESOLUTION,
        WarningCode.LOW_CONTRAST,
        WarningCode.TOO_DARK,
    ]


def test_collect_image_diagnostics_emits_too_bright_warning(tmp_path: Path) -> None:
    image_path = tmp_path / "bright.png"
    _save_rgb_image(image_path, size=(900, 900), color=(250, 250, 250))

    diagnostics = collect_image_diagnostics(image_path)

    assert WarningCode.TOO_BRIGHT in {warning.code for warning in diagnostics.warnings}


def test_collect_image_diagnostics_reads_exif_orientation(tmp_path: Path) -> None:
    image_path = tmp_path / "with_exif_orientation.jpg"
    image = Image.new("RGB", (1200, 1600), color=(128, 128, 128))
    exif = Image.Exif()
    exif[274] = 6
    image.save(image_path, format="JPEG", exif=exif)

    diagnostics = collect_image_diagnostics(image_path)

    assert diagnostics.image.exif_orientation == 6
    assert WarningCode.EXIF_ORIENTATION_PRESENT in {
        warning.code for warning in diagnostics.warnings
    }


def test_collect_image_diagnostics_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ImageDiagnosticsFileNotFoundError):
        collect_image_diagnostics(tmp_path / "missing.jpg")


def test_collect_image_diagnostics_rejects_invalid_image(tmp_path: Path) -> None:
    image_path = tmp_path / "not_an_image.jpg"
    image_path.write_text("not an image", encoding="utf-8")

    with pytest.raises(ImageDiagnosticsInvalidImageError):
        collect_image_diagnostics(image_path)


def test_collect_image_diagnostics_rejects_file_above_hard_limit(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "document.png"
    _save_rgb_image(image_path, size=(100, 100), color=(128, 128, 128))

    with pytest.raises(ImageDiagnosticsTooLargeError):
        collect_image_diagnostics(
            image_path,
            config=ImageDiagnosticsConfig(max_file_size_bytes=1),
        )


def test_collect_image_diagnostics_rejects_dimensions_below_hard_minimum(
    tmp_path: Path,
) -> None:
    image_path = tmp_path / "tiny.png"
    _save_rgb_image(image_path, size=(16, 16), color=(128, 128, 128))

    with pytest.raises(ImageDiagnosticsTooSmallError):
        collect_image_diagnostics(
            image_path,
            config=ImageDiagnosticsConfig(
                hard_min_width_px=32,
                hard_min_height_px=32,
            ),
        )


def test_image_diagnostics_config_rejects_invalid_thresholds() -> None:
    with pytest.raises(ValueError, match="too_dark_brightness_threshold"):
        ImageDiagnosticsConfig(
            too_dark_brightness_threshold=240,
            too_bright_brightness_threshold=220,
        )


def _save_rgb_image(
    path: Path,
    *,
    size: tuple[int, int],
    color: tuple[int, int, int],
) -> None:
    image = Image.new("RGB", size, color=color)
    image.save(path)
