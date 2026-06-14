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
    Path("src/document_digitization_ai/extraction/provider.py"),
    Path("src/document_digitization_ai/extraction/fake.py"),
    Path("src/document_digitization_ai/extraction/prompts.py"),
    Path("src/document_digitization_ai/extraction/schema.py"),
    Path("src/document_digitization_ai/extraction/validation.py"),
)

FORBIDDEN_NETWORK_MODULES = (
    "requests",
    "httpx",
    "aiohttp",
    "urllib",
    "socket",
    "http.client",
)


def test_stage_07_12_modules_do_not_import_network_clients() -> None:
    for module_path in STAGE_07_12_RUNTIME_MODULES:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not _matches_any_import(imported_module, FORBIDDEN_NETWORK_MODULES)


def test_extraction_modules_do_not_import_db_or_application_layers() -> None:
    for module_path in EXTRACTION_RUNTIME_MODULES:
        imported_modules = _imported_module_names(module_path)
        for imported_module in imported_modules:
            assert not imported_module.startswith("document_digitization_ai.db")
            assert not imported_module.startswith("document_digitization_ai.application")


def test_extraction_modules_do_not_import_contracts_provider_context() -> None:
    for module_path in EXTRACTION_RUNTIME_MODULES:
        tree = ast.parse(module_path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom):
                continue
            if node.module != "document_digitization_ai.contracts":
                continue
            imported_names = {alias.name for alias in node.names}
            assert "ProviderInputContext" not in imported_names


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
