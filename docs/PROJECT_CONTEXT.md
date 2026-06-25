# Project Context

## 1. Purpose

`document-digitization-ai` — backend-first MVP для оцифровки документов:
приема изображения документа, извлечения текста, восстановления полей/таблиц,
валидации результата и выдачи результата через API, Web UI, Markdown и PDF.

Документ фиксирует текущий принятый контекст MVP для владельца проекта и
будущего maintainer-а. Это не публичный marketing README, не roadmap и не
Codex workflow document.

## 2. MVP Scope

В scope текущего MVP входят:

- локальная backend-first обработка одного загруженного документа за раз;
- HTTP API на FastAPI;
- статический Web UI, смонтированный backend-ом под `/app`;
- локальное хранение job state в SQLite и файловых artifacts в `./data`;
- deterministic fake provider как provider по умолчанию для локальной работы и
  автоматических тестов;
- opt-in real-provider path через OpenRouter;
- opt-in media staging через ImgBB для provider-facing public image URL;
- backend validation/sanitization внешнего provider output;
- просмотр статуса, истории, результата, preview исходного файла и удаление job;
- backend-owned Markdown и PDF exports.

Принятые architectural boundaries для MVP:

- UI, API routes и scripts являются carriers/adapters, а не владельцами
  business logic.
- Runtime configuration идет через settings/environment.
- Provider/model output считается untrusted до backend validation.
- Provider transport изолирован в provider/media adapters.
- Export rendering принадлежит backend-слою.

## 3. Main User Flow

1. Пользователь открывает Web UI под `/app` или вызывает HTTP API.
2. Пользователь загружает файл через `POST /documents`.
3. Backend проверяет размер upload, безопасное имя файла и локально сохраняет
   исходный файл в upload artifacts.
4. Backend запускает image diagnostics, создает job и extraction attempt.
5. Для fake provider workflow результат создается детерминированно локально.
6. Для OpenRouter workflow backend подготавливает provider context, staging
   media reference, prompt/schema package и structured output request.
7. Provider response сохраняется как raw/sanitized attempt artifacts, затем
   валидируется backend-ом.
8. Нормализованный extraction result сохраняется в DB.
9. Пользователь получает статус, preview, результат, Markdown/PDF export или
   удаляет job.

## 4. Current Capabilities

HTTP API:

- `GET /health`;
- `POST /documents`;
- `GET /jobs`;
- `GET /jobs/{job_id}`;
- `GET /jobs/{job_id}/preview`;
- `DELETE /jobs/{job_id}`;
- `GET /jobs/{job_id}/status`;
- `GET /jobs/{job_id}/result`;
- `GET /jobs/{job_id}/markdown`;
- `POST /jobs/{job_id}/markdown/export`;
- `GET /jobs/{job_id}/pdf`;
- `GET /jobs/{job_id}/artifacts`.

Runtime capabilities:

- upload size limit is configured by image diagnostics settings;
- empty and oversized uploads are rejected before facade processing;
- unsafe submission filenames are rejected;
- job history supports limit/offset/status filtering;
- original upload preview supports selected inline content types;
- delete removes DB job/attempt state and attempts safe artifact cleanup;
- result export can render Markdown without writing an artifact;
- explicit Markdown export writes `jobs/{job_id}/exports/result.md`;
- PDF export returns generated PDF bytes.

Input/output capabilities:

- Safe supported input claim: image files that Pillow can open and diagnose.
- UI currently accepts image files and `.pdf`, but PDF input processing is not
  a settled capability because extraction still depends on image diagnostics.
- Supported outputs: JSON API result, Web UI presentation, Markdown, PDF, and
  original upload preview.

## 5. Architecture Overview

Current source layers:

- `core`: typed settings and runtime configuration validation.
- `contracts`: enums, schemas, status transitions and result contracts.
- `diagnostics`: deterministic image diagnostics.
- `db`: SQLAlchemy models, repositories and schema bootstrap.
- `storage`: artifact path layouts, safe relative path validation and deletion.
- `providers`: provider input context construction from backend-owned facts.
- `media`: media staging port plus local/noop and ImgBB implementations.
- `extraction`: provider interface, fake provider, OpenRouter adapter, prompts,
  schema package and validation/sanitization.
- `services`: intake, extraction workflow and result export orchestration.
- `application`: runtime wiring, facade methods for API/UI, result review facts.
- `api/http`: FastAPI app, HTTP schemas and routes.
- `web/static`: static browser UI.
- `export`: Markdown/PDF export document model, builder and renderers.
- `scripts`: manual operational scripts.
- `tests`: deterministic automated tests.

Runtime ownership:

- FastAPI app factory: `document_digitization_ai.api.http.app:create_app`.
- HTTP routes delegate to `DocumentProcessingFacade`.
- `LocalDocumentApplication` owns local DB/session/service wiring.
- Services orchestrate intake, extraction, validation and export workflows.
- Repositories persist state and enforce valid job status transitions.
- OpenAI SDK usage is isolated to the OpenRouter adapter.
- ImgBB transport is isolated to the ImgBB media staging implementation.

There is no declared project script or committed ASGI server command yet.
`pyproject.toml` declares FastAPI but does not declare `uvicorn` as a direct
dependency.

## 6. Data, Storage and Retention

Default local storage:

- database: `sqlite+aiosqlite:///./data/app.db`;
- uploads root: `./data/uploads`;
- results root: `./data/results`;
- default retention setting: `ARTIFACT_RETENTION_DAYS=7`.

Persisted data:

- `DocumentJob` stores job status, source image metadata, diagnostics payload,
  extraction result payload, validation status, error message and timestamps.
- `ExtractionAttempt` stores attempt status, provider/model/schema metadata,
  timing, request/response metadata, artifact paths/sizes and error metadata.

Artifacts:

- original upload is stored under a per-job upload directory;
- provider raw/sanitized/error responses are stored under validated relative
  attempt artifact paths;
- Markdown export artifact path is `jobs/{job_id}/exports/result.md`;
- artifact path helpers reject absolute paths, parent traversal, drive prefixes
  and unsafe path segments.

Delete and retention:

- `DELETE /jobs/{job_id}` deletes DB state and attempts safe cleanup of related
  upload/result artifact trees.
- `cleanup_expired_jobs` exists on the application facade.
- No scheduler, background worker, CLI or public cleanup endpoint is currently
  accepted for automatic retention cleanup.

## 7. Exports

Exports are backend-owned.

Markdown:

- `GET /jobs/{job_id}/markdown` returns Markdown without writing an artifact.
- `POST /jobs/{job_id}/markdown/export` writes a Markdown artifact and returns
  artifact metadata.

PDF:

- `GET /jobs/{job_id}/pdf` returns generated PDF bytes with
  `application/pdf`.
- PDF rendering uses backend export models and PyMuPDF.

Stable export sections:

- summary;
- warnings;
- fields;
- tables;
- user-facing text.

Internal diagnostics, extraction metadata, provider request details, raw
provider response, provider sanitized response, secrets, local paths and
provider debug data are not part of the default user-facing exports.

There is no artifact download endpoint for arbitrary stored artifact payloads.
Artifact reference metadata inventory may be API-visible through current job
routes; it is not a generic artifact explorer or arbitrary payload download
surface.

## 8. LLM / Provider Behavior

Provider options:

- `fake`: default deterministic local provider;
- `openrouter`: opt-in real provider adapter.

Default local behavior:

- `EXTRACTION_PROVIDER=fake`;
- placeholder OpenRouter/ImgBB secrets may exist in `.env.example`;
- default automated tests use fakes/injected transports and should not call
  real external providers.

OpenRouter behavior:

- real OpenRouter calls require non-placeholder `OPENROUTER_API_KEY`;
- provider context requires non-placeholder `OPENROUTER_MODEL`;
- structured outputs are enabled by default;
- schema mode defaults to `compact`;
- OpenRouter requests require `PUBLIC_URL` staged media, not local file paths.

Media staging:

- `MEDIA_STAGING_BACKEND=none` returns a local file reference and performs no
  external upload;
- `MEDIA_STAGING_BACKEND=imgbb` requires `IMGBB_API_KEY` and uploads media to
  ImgBB for a provider-facing public URL.

Validation and safety:

- provider output is untrusted;
- backend validation normalizes result payload into internal contracts;
- partial/malformed optional data can produce warnings;
- substantively empty provider output fails validation;
- provider errors are mapped and sanitized before surfacing.

Manual real-provider smoke is available through `scripts/manual_provider_smoke.py`
and is gated by `RUN_REAL_PROVIDER_SMOKE=1`. It is not part of default pytest
or routine local validation.

## 9. Web UI

The current Web UI is a static browser UI mounted by FastAPI under `/app`.

Observed UI capabilities:

- file upload surface;
- local image preview for selected files;
- backend preview after job creation when available;
- job history/files panel;
- status polling;
- result tabs for summary, warnings, values, tables, user-facing text and Markdown;
- Markdown copy/download;
- PDF download;
- delete confirmation.

The UI is a carrier for backend capabilities. It should not own extraction,
validation, storage, provider policy or export decisions.

Known UI caveat:

- upload input currently accepts `.pdf`, but accepted MVP input should be
  documented conservatively as image-first until PDF input behavior is approved
  and tested as a supported capability.

## 10. Safety Boundaries

Non-negotiable runtime boundaries:

- no real provider calls in default automated tests;
- no external provider call without explicit provider/media settings and
  required secrets;
- no hidden fallback from failed real provider to fake provider;
- no secrets, local credentials or generated runtime artifacts in git;
- provider outputs are untrusted until validated by backend;
- UI and HTTP routes do not own business logic;
- scripts do not define product architecture;
- artifact paths must stay inside configured storage roots.

Documentation boundaries:

- deleted early planning docs are not current source of truth;
- preserved reports under `docs/codex/reports/` are analysis inputs, not durable
  product docs;
- final internal project docs must be updated in separate approved Stage 26 steps.

## 11. Known Limitations

- No committed ASGI server runner command or project script exists yet.
- PDF export exists, but PDF upload/input is not a settled supported capability.
- No auth, users, tenants or permission model.
- No production deployment architecture.
- No migration framework beyond schema bootstrap.
- No scheduled retention cleanup.
- No generic artifact explorer or arbitrary artifact payload download surface.
  Artifact reference metadata inventory may be API-visible through current job
  routes.
- No batch processing.
- No user correction/review workflow.
- No DOCX, XLSX or CSV export.
- No global pytest network blocker; tests rely on fakes, injection and env
  gates to avoid real provider calls.
- Some media verification/strict settings are parsed but not treated as accepted
  user-facing runtime behavior.

## 12. Explicit Non-Goals

The current MVP does not try to solve:

- production hosting/deployment;
- multi-user access control;
- billing, quotas or tenant isolation;
- long-term object storage strategy;
- final provider/model selection policy;
- prompt/schema experimentation UI;
- general OCR engine implementation from scratch;
- multi-page PDF extraction pipeline;
- arbitrary artifact browsing/downloading;
- public API contract stabilization;
- broad frontend product polish beyond the current local Web UI carrier.

## 13. Post-MVP Directions

Current documentation baseline:

- `README.md`;
- `docs/PROJECT_CONTEXT.md`;
- `docs/DEVELOPMENT_CHECKLIST.md`;
- `docs/LLM_MODEL_POLICY.md`;
- `docs/PROJECT_MAP.md`.

Likely follow-up decisions:

- approve and document a concrete app run command or ASGI server dependency;
- settle PDF input behavior: reject, hide from UI, or implement supported
  PDF-to-image extraction path;
- decide whether retention cleanup should be manual, scheduled, CLI-driven or
  API-driven;
- decide whether media verification/strict settings should be implemented,
  reserved or removed;
- decide whether CI needs a hard no-network guard for pytest;
- decide whether sanitized provider artifacts should become user-visible
  inventory while raw provider artifacts remain internal;
- decide whether artifact metadata inventory is accepted public API metadata,
  internal diagnostic metadata or temporary MVP surface.
