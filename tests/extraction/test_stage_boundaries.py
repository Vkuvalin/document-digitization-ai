import ast
from pathlib import Path


STAGE_07_12_RUNTIME_MODULES = (
    Path("src/document_digitization_ai/providers/context.py"),
    Path("src/document_digitization_ai/media/base.py"),
    Path("src/document_digitization_ai/media/local.py"),
    Path("src/document_digitization_ai/extraction/provider.py"),
    Path("src/document_digitization_ai/extraction/fake.py"),
    Path("src/document_digitization_ai/extraction/prompts.py"),
    Path("src/document_digitization_ai/extraction/schema.py"),
    Path("src/document_digitization_ai/extraction/validation.py"),
    Path("src/document_digitization_ai/services/extraction_workflow.py"),
    Path("src/document_digitization_ai/application/runtime.py"),
)

EXTRACTION_RUNTIME_MODULES = (
    Path("src/document_digitization_ai/extraction/factory.py"),
    Path("src/document_digitization_ai/extraction/provider.py"),
    Path("src/document_digitization_ai/extraction/fake.py"),
    Path("src/document_digitization_ai/extraction/prompts.py"),
    Path("src/document_digitization_ai/extraction/schema.py"),
    Path("src/document_digitization_ai/extraction/validation.py"),
)

OPENROUTER_TRANSPORT_MODULES = (
    Path("src/document_digitization_ai/extraction/openrouter.py"),
)

STAGE_14_ATTEMPT_MODULES = (
    Path("src/document_digitization_ai/db/extraction_attempts.py"),
    Path("src/document_digitization_ai/db/models.py"),
    Path("src/document_digitization_ai/db/repository.py"),
    Path("src/document_digitization_ai/storage/artifacts.py"),
)

EXTRACTION_MODULES_WITH_OPENROUTER = (
    *EXTRACTION_RUNTIME_MODULES,
    *OPENROUTER_TRANSPORT_MODULES,
)

FORBIDDEN_NETWORK_MODULES = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "http.client",
)

FORBIDDEN_PROVIDER_SDK_MODULES = (
    "openai",
    "openrouter",
)

FORBIDDEN_STAGE_14_RUNTIME_MODULES = (
    *FORBIDDEN_NETWORK_MODULES,
    *FORBIDDEN_PROVIDER_SDK_MODULES,
    "document_digitization_ai.media.imgbb",
    "document_digitization_ai.extraction.openrouter",
    "document_digitization_ai.services.extraction_workflow",
)


def test_stage_07_12_modules_do_not_import_network_clients() -> None:
    for module_path in STAGE_07_12_RUNTIME_MODULES:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not _matches_any_import(imported_module, FORBIDDEN_NETWORK_MODULES)


def test_extraction_provider_foundation_does_not_import_network_clients() -> None:
    for module_path in EXTRACTION_RUNTIME_MODULES:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not _matches_any_import(imported_module, FORBIDDEN_NETWORK_MODULES)


def test_openrouter_sdk_module_does_not_import_raw_network_clients() -> None:
    for module_path in OPENROUTER_TRANSPORT_MODULES:
        imported_modules = _imported_module_names(module_path)

        for imported_module in imported_modules:
            assert not _matches_any_import(
                imported_module,
                FORBIDDEN_NETWORK_MODULES,
            )


def test_extraction_provider_foundation_does_not_import_provider_sdks() -> None:
    for module_path in EXTRACTION_RUNTIME_MODULES:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not _matches_any_import(
                imported_module,
                FORBIDDEN_PROVIDER_SDK_MODULES,
            )


def test_only_openrouter_adapter_imports_openai_sdk() -> None:
    for module_path in OPENROUTER_TRANSPORT_MODULES:
        imported_modules = _imported_module_names(module_path)
        assert "openai" in imported_modules

    for module_path in (
        Path("src/document_digitization_ai/services/extraction_workflow.py"),
        Path("src/document_digitization_ai/application/runtime.py"),
        Path("src/document_digitization_ai/db/repository.py"),
        Path("src/document_digitization_ai/db/models.py"),
        Path("src/document_digitization_ai/extraction/schema.py"),
        Path("src/document_digitization_ai/extraction/validation.py"),
        Path("src/document_digitization_ai/media/base.py"),
        Path("src/document_digitization_ai/media/local.py"),
    ):
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not _matches_any_import(imported_module, ("openai",))


def test_extraction_modules_do_not_import_db_or_application_layers() -> None:
    for module_path in EXTRACTION_MODULES_WITH_OPENROUTER:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not imported_module.startswith("document_digitization_ai.db")
            assert not imported_module.startswith("document_digitization_ai.application")


def test_extraction_workflow_and_provider_modules_do_not_import_imgbb_directly() -> None:
    module_paths = (
        Path("src/document_digitization_ai/services/extraction_workflow.py"),
        *EXTRACTION_MODULES_WITH_OPENROUTER,
    )

    for module_path in module_paths:
        imported_modules = _imported_module_names(module_path)
        assert "document_digitization_ai.media.imgbb" not in imported_modules


def test_stage_10_schema_package_does_not_import_openrouter_mapping() -> None:
    imported_modules = _imported_module_names(
        Path("src/document_digitization_ai/extraction/schema.py")
    )

    assert not any("openrouter" in imported_module for imported_module in imported_modules)


def test_extraction_modules_do_not_import_contracts_provider_context() -> None:
    for module_path in EXTRACTION_MODULES_WITH_OPENROUTER:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "document_digitization_ai.contracts":
                continue
            imported_names = {alias.name for alias in node.names}
            assert "ProviderInputContext" not in imported_names


def test_services_application_and_db_do_not_import_openrouter_adapter_directly() -> None:
    module_paths = (
        Path("src/document_digitization_ai/services/extraction_workflow.py"),
        Path("src/document_digitization_ai/application/runtime.py"),
        Path("src/document_digitization_ai/db/repository.py"),
        Path("src/document_digitization_ai/db/models.py"),
    )

    for module_path in module_paths:
        imported_modules = _imported_module_names(module_path)
        assert "document_digitization_ai.extraction.openrouter" not in imported_modules


def test_stage_14_attempt_modules_do_not_import_runtime_or_provider_boundaries() -> None:
    for module_path in STAGE_14_ATTEMPT_MODULES:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not _matches_any_import(
                imported_module,
                FORBIDDEN_STAGE_14_RUNTIME_MODULES,
            )


def _imported_module_names(module_path: Path) -> tuple[str, ...]:
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported_modules.append(node.module)
    return tuple(imported_modules)


def _matches_any_import(imported_module: str, blocked_modules: tuple[str, ...]) -> bool:
    return any(
        imported_module == blocked_module
        or imported_module.startswith(f"{blocked_module}.")
        for blocked_module in blocked_modules
    )
