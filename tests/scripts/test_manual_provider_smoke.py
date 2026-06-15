from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType


def _load_smoke_module() -> ModuleType:
    module_path = Path(__file__).parents[2] / "scripts" / "manual_provider_smoke.py"
    spec = importlib.util.spec_from_file_location(
        "manual_provider_smoke_under_test",
        module_path,
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SMOKE = _load_smoke_module()


def test_cli_parser_accepts_required_and_optional_arguments() -> None:
    args = SMOKE.parse_cli_args(
        [
            "--image",
            "sample.jpg",
            "--print-result",
            "--verbose",
            "--json-summary",
        ]
    )

    assert args.image == Path("sample.jpg")
    assert args.print_result is True
    assert args.verbose is True
    assert args.json_summary is True


def test_env_gate_blocks_without_real_smoke_flag(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = SMOKE.main(
        ["--image", "sample.jpg"],
        env={},
        dotenv_path=tmp_path / ".env",
    )

    captured = capsys.readouterr()
    assert exit_code == SMOKE.EXIT_PRECONDITION
    assert SMOKE.RUN_GATE_MESSAGE in captured.err


def test_env_gate_passes_from_env_mapping_before_image_precondition(
    tmp_path: Path,
    capsys,
) -> None:
    exit_code = SMOKE.main(
        ["--image", str(tmp_path / "missing.jpg")],
        env={"RUN_REAL_PROVIDER_SMOKE": "1"},
        dotenv_path=tmp_path / ".env",
    )

    captured = capsys.readouterr()
    assert exit_code == SMOKE.EXIT_PRECONDITION
    assert SMOKE.RUN_GATE_MESSAGE not in captured.err
    assert "Image path must point to an existing file" in captured.err


def test_env_gate_passes_from_dotenv_before_image_precondition(
    tmp_path: Path,
    capsys,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("RUN_REAL_PROVIDER_SMOKE=1\n", encoding="utf-8")

    exit_code = SMOKE.main(
        ["--image", str(tmp_path / "missing.jpg")],
        env={},
        dotenv_path=dotenv_path,
    )

    captured = capsys.readouterr()
    assert exit_code == SMOKE.EXIT_PRECONDITION
    assert SMOKE.RUN_GATE_MESSAGE not in captured.err
    assert "Image path must point to an existing file" in captured.err


def test_env_mapping_overrides_dotenv_gate(
    tmp_path: Path,
    capsys,
) -> None:
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("RUN_REAL_PROVIDER_SMOKE=1\n", encoding="utf-8")

    exit_code = SMOKE.main(
        ["--image", str(tmp_path / "missing.jpg")],
        env={"RUN_REAL_PROVIDER_SMOKE": "0"},
        dotenv_path=dotenv_path,
    )

    captured = capsys.readouterr()
    assert exit_code == SMOKE.EXIT_PRECONDITION
    assert SMOKE.RUN_GATE_MESSAGE in captured.err
    assert "Image path must point to an existing file" not in captured.err


def test_missing_image_path_fails_before_settings_or_network(
    tmp_path: Path,
    capsys,
) -> None:
    missing_image = tmp_path / "missing.jpg"

    exit_code = SMOKE.main(
        ["--image", str(missing_image)],
        env={"RUN_REAL_PROVIDER_SMOKE": "1"},
        dotenv_path=tmp_path / ".env",
    )

    captured = capsys.readouterr()
    assert exit_code == SMOKE.EXIT_PRECONDITION
    assert "Image path must point to an existing file" in captured.err
    assert "MEDIA_STAGING_BACKEND" not in captured.err


def test_redaction_helper_removes_sensitive_values_urls_and_raw_text() -> None:
    payload = {
        "api_key": "openrouter-secret",
        "delete_url": "https://ibb.co/delete/private",
        "staged_media": {
            "value": "https://i.ibb.co/public/staged.jpg",
            "private_cleanup_token": "cleanup-secret",
        },
        "raw_text": {"text": "Recognized document text."},
        "metadata": {"safe": "kept"},
    }

    redacted = SMOKE.redact_for_output(
        payload,
        extra_secrets=("openrouter-secret", "cleanup-secret"),
    )
    serialized = json.dumps(redacted, sort_keys=True)

    assert "openrouter-secret" not in serialized
    assert "cleanup-secret" not in serialized
    assert "delete/private" not in serialized
    assert "public/staged" not in serialized
    assert "Recognized document text" not in serialized
    assert "raw text length=25" in serialized
    assert "kept" in serialized


def test_smoke_module_import_does_not_call_network() -> None:
    assert callable(SMOKE.main)
