# Project Map

## 1. Purpose of This Map

Этот файл - практическая карта проекта для maintainer-а и GPT/Codex.
Она помогает быстро понять текущую структуру MVP, layer ownership и runtime
flow без чтения каждого файла перед началом работы.

Это не README, не полный API reference, не backlog, не changelog и не Codex
workflow manual. Для локального запуска сначала см. `README.md`; для принятого
контекста MVP - `docs/PROJECT_CONTEXT.md`; для provider policy -
`docs/LLM_MODEL_POLICY.md`.

## 2. Current MVP Status

Текущий проект - private/local backend-first MVP. Он содержит FastAPI backend,
статический Web UI под `/app`, загрузку image-first документа, создание job,
status/history, extraction workflow, result workspace, preview исходного файла,
Markdown/PDF exports, delete и callable retention cleanup.

Default local/runtime path использует deterministic `fake` provider. Real
provider path через OpenRouter и media staging через ImgBB существует, но
является opt-in и требует явной конфигурации и secrets. Production deployment,
auth, multi-user isolation, billing и scheduled cleanup не заявлены.

PDF export поддерживается. PDF extraction input не следует документировать как
гарантированную capability: UI принимает `.pdf`, но backend extraction path
остается image-diagnostics/Pillow based.

## 3. Runtime Entrypoints

| Entrypoint | Location | Responsibility |
| --- | --- | --- |
| FastAPI app factory | `document_digitization_ai.api.http.app:create_app` / `src/document_digitization_ai/api/http/app.py` | Создает app, lifespan, settings/facade state, routers и static Web UI mount. |
| Healthcheck | `GET /health` | Минимальная проверка, что HTTP app отвечает. |
| Web UI | `/app` -> `/app/` | Static UI из `src/document_digitization_ai/web/static/`. Root `/` не является Web UI. |
| Upload | `POST /documents` | Multipart upload, hard size guard, delegation to application facade. |
| Job/result routes | `src/document_digitization_ai/api/http/routes/jobs.py` | Status/detail/history/result/export/preview/delete/artifact metadata inventory endpoints. |
| Local manual server | `uv run --with uvicorn uvicorn document_digitization_ai.api.http.app:create_app --factory --host 127.0.0.1 --port 8000` | Manual command from README. `uvicorn` is supplied through `uv --with`, not pinned in `pyproject.toml`. |
| Manual provider smoke | `uv run python scripts/manual_provider_smoke.py --image path\to\sample.jpg` | Explicit real-provider smoke path, gated by env and not part of default validation. |

## 4. Configuration and Runtime Policy

Runtime settings live in `src/document_digitization_ai/core/config.py` and are
loaded from environment / local `.env` via pydantic-settings. `.env.example`
is committed safe template; real `.env`, API keys and local credentials must not be
committed.

Important current defaults from `.env.example`:

| Area | Current setting |
| --- | --- |
| Provider | `EXTRACTION_PROVIDER=fake` |
| OpenRouter | `OPENROUTER_API_KEY=change_me`, `OPENROUTER_MODEL=change_me` |
| Structured outputs | `LLM_STRUCTURED_OUTPUTS_ENABLED=true`, `LLM_PROVIDER_SCHEMA_MODE=compact` |
| Database | `DATABASE_URL=sqlite+aiosqlite:///./data/app.db` |
| Storage | `STORAGE_UPLOADS_DIR=./data/uploads`, `STORAGE_RESULTS_DIR=./data/results` |
| Retention | `ARTIFACT_RETENTION_DAYS=7` |
| Media staging | `MEDIA_STAGING_BACKEND=none`, `IMGBB_API_KEY=change_me` |
| Upload hard limit | `IMAGE_DIAGNOSTICS_MAX_FILE_SIZE_BYTES=20971520` |

Policy boundaries:

- Default local flow must stay offline and use `fake`.
- Real OpenRouter calls require non-placeholder OpenRouter API key and model.
- `MEDIA_STAGING_BACKEND=imgbb` requires `IMGBB_API_KEY` and uploads document
  image bytes to ImgBB.
- OpenRouter visual extraction requires provider-facing `PUBLIC_URL` media.
- Provider output is untrusted until backend validation accepts it.
- There is no hidden fallback from failed `openrouter` setup to `fake`.
- Generated runtime data belongs under ignored storage roots such as `data/`.

## 5. Architecture Layers

| Layer | Main path | Responsibility | Do not put here |
| --- | --- | --- | --- |
| Core config | `src/document_digitization_ai/core/config.py` | Typed settings, env aliases, secret placeholders, provider/media/storage/image diagnostics config. | Business workflow, HTTP behavior, provider requests. |
| Contracts / schemas | `src/document_digitization_ai/contracts/` | Stable enums, result dataclasses, schema versions and status transitions. | Runtime I/O, persistence, UI formatting. |
| Diagnostics | `src/document_digitization_ai/diagnostics/` | Deterministic Pillow image diagnostics, hard input rejection and quality warnings. | Provider policy, UI preview, export rendering. |
| DB / repositories | `src/document_digitization_ai/db/` | SQLAlchemy models, async sessions, schema bootstrap, job/attempt repositories and safe metadata. | HTTP parsing, file serving, provider transport. |
| Storage / artifacts | `src/document_digitization_ai/storage/` | Upload/result artifact layouts, safe relative paths, JSON/Markdown writes and safe tree deletion. | Provider calls, user-facing download policy, UI state. |
| Media staging | `src/document_digitization_ai/media/` | `none` local reference and ImgBB public URL staging behind a port. | Extraction prompts, validation, business fallback. |
| Provider context | `src/document_digitization_ai/providers/context.py` | Builds provider input context from backend-owned job, diagnostics and extraction settings. | HTTP request parsing, UI decisions. |
| Extraction/provider | `src/document_digitization_ai/extraction/` | Provider port, fake provider, OpenRouter adapter, prompt/schema package and validation/sanitization. | DB lifecycle ownership, user-facing export formatting. |
| Services | `src/document_digitization_ai/services/` | Intake, extraction workflow and result export orchestration. | FastAPI response models, browser UI state. |
| Application | `src/document_digitization_ai/application/` | Runtime wiring, facade, application DTO/views, result review payload and callable retention cleanup. | Raw HTTP details, provider SDK calls in facade methods. |
| Export | `src/document_digitization_ai/export/` | Export document model, Markdown/PDF renderers, reconstruction from persisted result payload. | Provider raw/sanitized payload exposure, HTTP endpoint ownership. |
| API / HTTP | `src/document_digitization_ai/api/http/` | FastAPI app, dependencies, route adapters, HTTP schemas and safe error mapping. | Business logic, DB/storage/provider ownership. |
| Web UI static | `src/document_digitization_ai/web/static/` | Browser carrier for upload, history, workspace, preview, result tabs, Markdown/PDF downloads and delete. | Extraction, validation, storage policy or provider policy. |
| Scripts | `scripts/` | Explicit/manual dev or smoke tools. | Product architecture or default automated validation. |
| Tests | `tests/` | Deterministic coverage for layers, routes, exports, providers, storage and workflow. | Runtime production code or real provider calls by default. |

## 6. Main User Flow

1. User opens `/app`.
2. User uploads an image-first document through the Web UI.
3. Backend creates a job and stores the original upload artifact.
4. Extraction workflow runs diagnostics, media staging, provider call and
   backend validation.
5. UI polls job status and refreshes history/workspace state.
6. Result appears in the workspace when the job reaches result-ready state.
7. User reviews summary, warnings, values, table-derived values, tables, text
   and Markdown.
8. User downloads Markdown or PDF generated by backend export code.
9. User previews or deletes the job from current/history views.

## 7. Backend/API Flow

`create_app()` wires settings and `DocumentProcessingFacade` into FastAPI app
state, initializes the local database during lifespan when it owns the facade,
registers document/job routers and mounts the static Web UI.

HTTP route groups:

- `GET /health` - app-level health response.
- `POST /documents` - upload guard and job submission through facade.
- `GET /jobs` - job history with limit/offset/status filter.
- `GET /jobs/{job_id}` - job detail, attempts and artifact inventory views.
- `GET /jobs/{job_id}/status` - status polling.
- `GET /jobs/{job_id}/result` - validated result payload plus review/presentation data.
- `GET /jobs/{job_id}/markdown` - render Markdown without writing artifact.
- `POST /jobs/{job_id}/markdown/export` - render and write Markdown export artifact.
- `GET /jobs/{job_id}/pdf` - return generated PDF bytes.
- `GET /jobs/{job_id}/preview` - safe original upload preview/download.
- `DELETE /jobs/{job_id}` - delete DB state and safe storage trees.
- `GET /jobs/{job_id}/artifacts` - artifact reference metadata inventory, not
  arbitrary stored artifact payload downloads.

API routes are adapters. They parse HTTP input, call the facade, convert view
objects to Pydantic response models and map backend errors to safe HTTP errors.

## 8. Extraction / Provider / Media Staging Path

Extraction workflow is backend-owned:

1. Store original upload under configured uploads root.
2. Run deterministic image diagnostics with Pillow.
3. Build provider input context from persisted job facts and settings.
4. Stage media through configured media staging port.
5. Build prompt package and schema package.
6. Call configured extraction provider.
7. Store raw/sanitized provider artifacts for internal/debug use.
8. Validate and normalize provider output into internal contracts.
9. Persist accepted extraction result and status transitions.

Provider modes:

- `fake` - deterministic local provider for default local runs and automated tests.
- `openrouter` - opt-in real provider adapter. OpenAI SDK import is isolated in
  `src/document_digitization_ai/extraction/openrouter.py`.

Media staging:

- `MEDIA_STAGING_BACKEND=none` returns a local file reference and performs no
  external upload.
- `MEDIA_STAGING_BACKEND=imgbb` uploads image bytes to ImgBB and returns a
  provider-facing public URL.

Prompt/schema contract:

- Prompt package version: `extraction_prompt_v0`.
- Target schema version: `extraction_result_v0`.
- Schema modes: `compact` and `full`.
- OpenRouter adapter requires structured outputs and builds strict JSON schema
  response format.

Provider output remains untrusted until `validate_provider_output()` accepts it.
Substantively empty provider output fails validation. Optional malformed pieces
may become validation warnings. Raw/sanitized provider artifacts are internal
and must not become normal user-facing UI/export content. Their reference
metadata may appear in API artifact inventory; that inventory is not an
arbitrary artifact payload download surface.

## 9. Storage, Preview, Delete and Retention

Default local storage roots:

- DB: `./data/app.db`;
- uploads: `./data/uploads`;
- results: `./data/results`.

`DocumentJob` and `ExtractionAttempt` persist job state, provider/model/schema
metadata, validation state, artifact references and safe error metadata.
Repositories enforce status transitions and job/attempt lookup behavior.

Artifact rules:

- Original upload is stored under a per-job upload directory.
- Provider raw/sanitized/error artifacts use validated relative result paths.
- Explicit Markdown export writes `jobs/{job_id}/exports/result.md`.
- Absolute paths, drive prefixes, parent traversal and unsafe path segments are rejected.

Preview/delete/retention:

- Preview goes through `GET /jobs/{job_id}/preview` and validates the target
  path under uploads root before serving.
- Delete goes through `DELETE /jobs/{job_id}` and attempts cleanup of related
  upload/result trees while skipping unsafe artifact layouts.
- `DocumentProcessingFacade.cleanup_expired_jobs()` exists and uses
  `ARTIFACT_RETENTION_DAYS`.
- No scheduler, cron, background worker, CLI or public cleanup endpoint is
  currently documented as accepted automatic cleanup.

## 10. Result Review and Exports

Result review is built from accepted extraction result payloads, not raw
provider responses. `application/result_review.py` derives table facts into
`review.derived_table_facts` so important values represented in tables can be
shown alongside normal fields without flattening provider output blindly.

User-facing result/export surfaces:

- Web UI workspace;
- JSON result API after backend validation;
- Markdown export;
- PDF export;
- original upload preview/download through backend endpoint.

Default Markdown/PDF export sections are user-facing: summary, warnings,
fields/values, tables and text. Internal diagnostics, extraction metadata,
provider/model/job/attempt debug data, raw provider response, sanitized provider
response, secrets, local paths and staging URLs are not default user-facing
export content.

## 11. Web UI Surface

The Web UI is static and mounted under `/app`. Current UI copy is Russian.
It uses relative backend endpoints and acts as a carrier for backend-owned
capabilities.

Current capabilities:

- upload;
- selected-file reset behavior and local image preview;
- `Мои файлы` / history list;
- workspace;
- backend preview or file download placeholder;
- values, table-derived values, tables, text and Markdown views;
- Markdown copy/download;
- PDF download;
- delete confirmation and history/current-job removal.

Main static files:

| File | Responsibility |
| --- | --- |
| `web/static/index.html` | UI shell, upload/workspace/history/result/delete modal markup and Russian copy. |
| `web/static/styles.css` | Responsive layout and visual states for upload, workspace, preview, tabs, history and modals. |
| `web/static/js/apiClient.js` | Relative API client, upload/status/result/preview/delete/Markdown/PDF calls and user-facing error mapping. |
| `web/static/js/app.js` | Browser bootstrap, info modal and module initialization. |
| `web/static/js/sampleData.js` | Static informational/sample copy for UI panels; not backend source of truth. |
| `web/static/js/uiUpload.js` | File selection, reset, local preview and upload submission flow. |
| `web/static/js/uiJobs.js` | History card rendering, status labels/classes and delete button behavior. |
| `web/static/js/uiResultDialog.js` | Workspace state, polling, result tabs, preview, Markdown/PDF downloads and delete confirmation. |

Do not put extraction, validation, provider, storage or export ownership in the
Web UI. Treat PDF input wording conservatively: PDF export exists, PDF
extraction input is not guaranteed.

## 12. Scripts and Dev Tools

- `scripts/manual_provider_smoke.py` - explicit/manual real-provider smoke
  script. It requires `RUN_REAL_PROVIDER_SMOKE=1`,
  `EXTRACTION_PROVIDER=openrouter`, `MEDIA_STAGING_BACKEND=imgbb`, structured
  outputs enabled, real OpenRouter credentials/model, real ImgBB key and an
  existing local image path. It redacts sensitive values/URLs/raw text in output.

Routine validation uses `uv`:

```powershell
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

Default automated validation must not run real external provider calls.

## 13. Tests

Tests are summarized by directory/purpose:

- `tests/api/` - HTTP adapter behavior, endpoint mapping and static UI serving.
- `tests/application/` - facade behavior, runtime wiring and result review payloads.
- `tests/contracts/` - enums, schemas and status/result contracts.
- `tests/core/` - settings parsing, defaults and config validation.
- `tests/db/` - schema bootstrap, job repository and extraction attempt lifecycle.
- `tests/diagnostics/` - deterministic image diagnostics behavior.
- `tests/export/` - Markdown/PDF export behavior and user-facing boundary.
- `tests/extraction/` - provider port, fake provider, OpenRouter adapter,
  prompt/schema package, stage boundaries and validation/sanitization.
- `tests/media/` - media staging ports and ImgBB staging with injected/fake transports.
- `tests/providers/` - provider input context construction.
- `tests/scripts/` - manual provider smoke gates, preconditions and redaction.
- `tests/services/` - intake, extraction workflow and result export orchestration.
- `tests/storage/` - artifact layout and safe path/delete behavior.

Tests should stay deterministic and offline by default.

## 14. Known Future / Deferred Zones

Deferred or future zones, not current MVP commitments:

- auth/accounts and multi-user isolation;
- billing/payment/quotas;
- production deployment and production hardening;
- scheduler/cron/background retention cleanup;
- advanced viewer/editor or correction workflow;
- generic artifact explorer / arbitrary artifact downloads;
- full original-layout reconstruction;
- full PDF extraction input pipeline.

This section is not a backlog; each item needs separate approval before
implementation.

## 15. Factual Project Tree

Generated from current repository state using `git ls-files`,
`git status --short --untracked-files=all`, `rg --files src/document_digitization_ai`,
`rg --files tests`, `rg --files scripts` and targeted file inspection.

Excluded from this factual project tree: `.git/`, virtualenv/cache/temp directories,
local `.env`, local secrets, runtime `data/`, generated artifacts, local sample
outputs, private workflow overlays `AGENTS.md`, `.agents/`, `.codex/` and
`docs/codex/`. Deleted tracked docs are not listed as current files.

```text
.
|-- .env.example - public local env template with fake provider default, storage, media staging and diagnostics settings.
|-- .gitattributes - repository text/eol normalization rules.
|-- .gitignore - excludes secrets, private workflow overlay, caches, `data/`, logs and generated DB files.
|-- .python-version - Python version marker (`3.14`).
|-- README.md - local MVP overview, run command, configuration, exports, validation and smoke checklist.
|-- pyproject.toml - package metadata, Python `>=3.14`, runtime/dev dependencies and pytest options.
|-- uv.lock - uv lockfile for resolved dependencies.
|-- docs/
|   |-- DEVELOPMENT_CHECKLIST.md - practical checklist for future changes and validation.
|   |-- LLM_MODEL_POLICY.md - provider/model/prompt/schema/media policy and external smoke boundaries.
|   |-- PROJECT_CONTEXT.md - accepted current MVP context, capabilities, boundaries and limitations.
|   `-- PROJECT_MAP.md - this orientation map.
|-- scripts/
|   |-- manual_provider_smoke.py - explicit env-gated real OpenRouter/ImgBB smoke script with redaction.
|-- src/document_digitization_ai/
|   |-- __init__.py - top-level package marker.
|   |-- api/__init__.py - API package marker.
|   |-- api/http/__init__.py - HTTP package export surface for `create_app`.
|   |-- api/http/app.py - FastAPI app factory, lifespan, routers, healthcheck and `/app` static mount.
|   |-- api/http/dependencies.py - FastAPI dependency that retrieves `DocumentProcessingFacade` from app state.
|   |-- api/http/errors.py - safe HTTP error mapping, facade-call wrapper and generic internal messages.
|   |-- api/http/routes/__init__.py - HTTP routes package marker.
|   |-- api/http/routes/documents.py - `POST /documents` upload route with size/empty guards and facade delegation.
|   |-- api/http/routes/jobs.py - job history/detail/status/result/Markdown/PDF/preview/delete/artifact routes.
|   |-- api/http/schemas.py - Pydantic HTTP response models built from application view DTOs.
|   |-- application/__init__.py - application public export surface for facade, runtime and DTO views.
|   |-- application/dtos.py - immutable application view DTOs for API/UI-facing facade responses.
|   |-- application/facade.py - application facade for submit, history, status, result, preview, delete, exports and retention cleanup.
|   |-- application/result_review.py - table-derived review facts and result review payload construction.
|   |-- application/runtime.py - local application wiring for DB engine/session, services, provider/media/export dependencies.
|   |-- contracts/__init__.py - contracts public export surface.
|   |-- contracts/enums.py - job statuses, status transitions, document modes, warning codes and provider constraints.
|   |-- contracts/schemas.py - extraction/image/provider dataclasses, schema versions and serialization contracts.
|   |-- core/__init__.py - core settings export surface.
|   |-- core/config.py - pydantic settings, env aliases, provider/media/storage/image diagnostics config and secret checks.
|   |-- db/__init__.py - DB public export surface.
|   |-- db/base.py - SQLAlchemy declarative base.
|   |-- db/bootstrap.py - async schema creation helper.
|   |-- db/extraction_attempts.py - extraction attempt lifecycle service, safe metadata builders and error sanitization.
|   |-- db/models.py - SQLAlchemy `DocumentJob` and `ExtractionAttempt` models.
|   |-- db/repository.py - job/attempt repositories, status transition enforcement and ID generation.
|   |-- db/session.py - async SQLAlchemy engine/session factory helpers and SQLite parent-dir creation.
|   |-- diagnostics/__init__.py - diagnostics public export surface.
|   |-- diagnostics/image.py - Pillow image diagnostics, hard input rejection, quality warnings and SHA-256 metadata.
|   |-- export/__init__.py - export public export surface for models, builders, Markdown/PDF and reconstruction.
|   |-- export/builder.py - builds user-facing export document sections from validated extraction result.
|   |-- export/markdown.py - Markdown renderer and reconstructed text/table formatting helpers.
|   |-- export/models.py - export document/section/row models and default user-facing export sections.
|   |-- export/pdf.py - PyMuPDF renderer for user-facing PDF output.
|   |-- export/reconstruction.py - reconstructs `ExtractionResult` contracts from persisted result payloads.
|   |-- extraction/__init__.py - extraction public export surface.
|   |-- extraction/factory.py - provider factory for `fake` and opt-in `openrouter`, with unsupported-provider rejection.
|   |-- extraction/fake.py - deterministic fake provider for default local/test extraction.
|   |-- extraction/openrouter.py - OpenRouter adapter, structured-output request building, strict JSON schema and provider error mapping.
|   |-- extraction/prompts.py - extraction prompt package builder and prompt metadata version.
|   |-- extraction/provider.py - provider request/response dataclasses, provider port and provider error hierarchy.
|   |-- extraction/schema.py - extraction schema package builder for compact/full schema modes.
|   |-- extraction/validation.py - provider payload sanitization, validation, reconstruction and warning generation.
|   |-- media/__init__.py - media staging public export surface.
|   |-- media/base.py - media staging port, input/result/reference dataclasses and staging errors.
|   |-- media/imgbb.py - ImgBB upload transport/service, public URL extraction and TTL validation.
|   |-- media/local.py - local/noop media staging and media staging service factory.
|   |-- providers/__init__.py - provider-context public export surface.
|   |-- providers/context.py - provider input context construction from job state, diagnostics and extraction settings.
|   |-- services/__init__.py - services public export surface.
|   |-- services/extraction_workflow.py - backend extraction workflow orchestration, staging, provider call, artifacts and validation.
|   |-- services/intake.py - local image intake, original upload storage and diagnostics persistence.
|   |-- services/result_export.py - Markdown/PDF export service built from persisted validated result payloads.
|   |-- storage/__init__.py - storage public export surface.
|   |-- storage/artifacts.py - safe artifact layouts, relative path validation, JSON/Markdown writes and tree deletion.
|   |-- web/__init__.py - Web UI package marker.
|   |-- web/static/index.html - static UI shell for upload, workspace, history, result tabs and delete modal.
|   |-- web/static/styles.css - static UI styling for layout, upload, preview, workspace, history and modal states.
|   |-- web/static/js/apiClient.js - browser API client using relative backend endpoints.
|   |-- web/static/js/app.js - browser bootstrap and UI module initialization.
|   |-- web/static/js/sampleData.js - static sample/info panel content for the Web UI.
|   |-- web/static/js/uiJobs.js - job/history card rendering and status display helpers.
|   |-- web/static/js/uiResultDialog.js - workspace/result/preview/Markdown/PDF/delete behavior.
|   `-- web/static/js/uiUpload.js - selected-file state, reset, local preview and upload submission behavior.
`-- tests/
    |-- api/ - HTTP adapter behavior and static UI serving tests.
    |-- application/ - facade, runtime and result-review tests.
    |-- contracts/ - enum/schema/status contract tests.
    |-- core/ - settings/config tests.
    |-- db/ - DB bootstrap, repository and extraction attempt tests.
    |-- diagnostics/ - image diagnostics tests.
    |-- export/ - Markdown/PDF export tests.
    |-- extraction/ - provider, fake/OpenRouter, prompt/schema, boundary and validation tests.
    |-- media/ - media staging and ImgBB fake-transport tests.
    |-- providers/ - provider context tests.
    |-- scripts/ - manual provider smoke gate/redaction tests.
    |-- services/ - intake, extraction workflow and result export tests.
    `-- storage/ - artifact safety tests.
```
