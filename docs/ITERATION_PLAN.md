# ITERATION_PLAN.md

## Статус плана

Это живой практический план разработки `document-digitization-ai`.

Он не является финальной архитектурой и не заменяет `AGENTS.md`, `docs/PROJECT_CONTEXT.md` или `docs/ARCHITECTURE_DRAFT.md`.

Назначение плана:

- вести разработку маленькими approved итерациями;
- фиксировать порядок работ для Codex;
- не смешивать provider, storage, Web UI, export и schema decisions в одном diff;
- сохранять результаты, решения, сложности и validation после каждой итерации;
- помогать Command Center принимать следующий безопасный шаг.

Repo bootstrap уже выполнен:

- public repo создан;
- Python `3.14`;
- `uv`;
- `ruff`;
- `pyright`;
- `pytest`;
- `pytest-asyncio`;
- product dependencies пока не добавлены;
- private Codex overlay локальный и ignored;
- product architecture ещё не финализирована.

## Как Codex должен вести этот план

После каждой approved implementation/docs/research итерации Codex должен обновлять только релевантные части этого файла, если задача явно включает план-обновление.

Обновления должны быть короткими и полезными:

- отметить завершённый блок;
- добавить фактические результаты;
- записать принятые решения;
- записать обнаруженные сложности;
- записать validation/checks;
- записать следующий safe step.

План не должен превращаться в changelog. Для длинного аудита, review или research использовать `docs/codex/reports/`, если это явно запрошено.

### Формат записи результата итерации

Использовать такой компактный формат внутри соответствующего этапа:

```text
Status: planned / in_progress / done / blocked / deferred

Result:
- ...

Decisions:
- ...

Difficulties / risks:
- ...

Validation:
- ...

Next safe step:
- ...
```

Если в итерации не было кода, явно писать `Validation: docs-only, tests skipped` или аналогичную причину.

## Рабочие принципы

- Command Center утверждает scope перед implementation.
- Codex не коммитит.
- Перед implementation фиксировать expected artifact и validation gates.
- Не добавлять dependencies без architecture/research justification.
- Не создавать `PROJECT_MAP.md` до появления фактической architecture/code structure.
- Не создавать новые docs без explicit approval.
- Не выдавать гипотезы за принятые решения.
- Не смешивать provider, storage, Web shell и export decisions в одной задаче без approval.
- После non-trivial diff использовать review/diff-review по смыслу задачи.
- Pytest не должен вызывать реальные LLM/API/staging provider calls.
- Manual smoke scripts могут вызывать real API только при ручном запуске.

---

# Этап 0. Dry documentation baseline

Status: done

Цель: создать начальные проектные docs без реализации.

Артефакты:

- `docs/PROJECT_CONTEXT.md`;
- `docs/ARCHITECTURE_DRAFT.md`;
- `docs/ITERATION_PLAN.md`.

Результат:

- базовый контекст проекта создан;
- первый happy path описан;
- v0 architecture decisions зафиксированы;
- implementation order задан;
- product code не добавлялся;
- dependencies не добавлялись;
- `PROJECT_MAP.md` не создавался.

Validation:

- docs-only;
- code/tests не менялись.

---

# Этап 1. Happy path и backend contracts

Status: planned

Цель: перед product code уточнить минимальные контракты, вокруг которых строится первый happy path.

Approved first happy path:

```text
User uploads one image of a mixed handwritten/printed form or document through Web UI.
User may choose document mode or leave Auto.
Backend creates processing job.
Backend performs deterministic ImageDiagnostics.
Backend stages image if provider-compatible reference is needed.
Backend builds ProviderInputContext.
Extraction provider returns structured output.
Backend validates output and stores ExtractionResult.
Web UI displays source image, diagnostics, text, fields, tables, blocks/preview, warnings and JSON.
```

## 1.1 Minimal job lifecycle

Status: approved for docs, not implemented

Approved lifecycle v0:

```text
CREATED
IMAGE_UPLOADED
IMAGE_DIAGNOSTICS_READY
MEDIA_STAGED
EXTRACTION_RUNNING
EXTRACTION_SUCCEEDED
VALIDATION_SUCCEEDED
VALIDATION_PARTIAL
RESULT_READY
FAILED
CANCELLED
```

Правила:

- invalid/unreadable image может привести к hard failure;
- blur, low contrast, skew, low quality обычно становятся warnings, не automatic failure;
- provider output не считается trusted до backend validation;
- `VALIDATION_PARTIAL` означает usable partial result with explicit warnings.

Expected future artifacts:

- enum/status contract;
- transition expectations;
- tests for allowed lifecycle path;
- docs sync if lifecycle changes.

Out of scope:

- background queue;
- retries;
- multi-image jobs;
- multi-page documents;
- human review statuses;
- production workflow engine.

Validation when implemented:

- unit tests for lifecycle values and allowed basic path;
- `uv run ruff check .`;
- `uv run pyright`;
- targeted `uv run pytest ...`.

## 1.2 Document mode hints

Status: approved for docs, not implemented

Initial hints:

```text
auto
form
table
free_handwritten_text
mixed_document
plain_text
```

Rules:

- user-selected mode is a hint, not truth;
- provider/analyzer must return detected type and confidence;
- possible mismatch should become warning, not hidden override.

Expected future artifacts:

- enum/literal contract;
- validation for accepted hint values;
- tests for mismatch warning representation.

Out of scope:

- user-defined document categories;
- medical/legal/tax-specific schemas;
- template-guided mode as implemented feature.

## 1.3 ExtractionResult v0

Status: approved draft, not implemented

Conceptual structure:

```text
ExtractionResult
├── document
├── image_diagnostics
├── raw_text
├── fields[]
├── tables[]
├── blocks[]
├── warnings[]
└── metadata
```

Draft details:

```text
document:
  user_mode_hint
  detected_type
  detected_type_confidence
  language
  summary

image_diagnostics:
  mime_type
  file_size_bytes
  width
  height
  aspect_ratio
  orientation
  blur_score?
  brightness?
  contrast?
  warnings[]

raw_text:
  text
  confidence?
  warnings[]

fields[]:
  label
  value
  confidence?
  source?
  warnings[]

tables[]:
  title?
  columns[]
  rows[{ cells[], confidence?, warnings[] }]
  confidence?
  warnings[]

blocks[]:
  type
  level?
  text
  order
  confidence?
  warnings[]

warnings[]:
  code
  message
  severity
  target?

metadata:
  provider?
  model?
  schema_version
  created_at?
```

Design rules:

- one `ExtractionResult` is the base for multiple result views;
- table output must support readable grid/DataFrame-like preview;
- confidence values must not be presented as absolute truth;
- warnings/uncertainty must be explicit;
- coordinates/bbox are optional future extension, not v0 requirement.

Expected future artifacts:

- Pydantic schemas/contracts;
- schema tests;
- fixtures for mixed handwritten/printed form;
- JSON serialization tests.

Out of scope:

- bbox/page layout model;
- PDF page model;
- template mapping details;
- export artifact schema;
- human correction schema.

## 1.4 ImageDiagnostics v0

Status: approved draft, not implemented

Conceptual structure:

```text
ImageDiagnostics
├── file
├── image
├── quality
├── warnings[]
└── metadata
```

Draft details:

```text
file:
  mime_type
  file_size_bytes
  file_extension
  sha256?

image:
  width
  height
  aspect_ratio
  orientation
  exif_orientation?
  color_mode?
  format?

quality:
  blur_score?
  sharpness_score?
  brightness?
  contrast?
  is_low_resolution?
  is_probably_blurry?
  is_low_contrast?

warnings[]:
  code
  message
  severity

metadata:
  diagnostics_version
  created_at?
```

Rules:

- backend-owned, not LLM-owned;
- collected before provider call;
- used as provider context, UI metadata and result warnings;
- invalid/unreadable files may be rejected;
- low quality conditions usually become warnings.

Initial implementation preference:

- start with Pillow + Pydantic;
- do not add OpenCV/scikit-image/numpy unless separately approved.

Expected future artifacts:

- image open/metadata extraction;
- hard reject errors;
- warnings;
- tests with local tiny fixtures;
- no real external API calls.

Out of scope:

- heavy layout analysis;
- OCR preprocessing;
- advanced deskew;
- table/region detection;
- automatic enhancement pipeline.

## 1.5 ProviderInputContext v0

Status: approved draft, not implemented

Conceptual structure:

```text
ProviderInputContext
├── job
├── user_request
├── image
├── image_diagnostics
├── extraction_goal
├── expected_result
└── constraints
```

Rules:

- bridge between backend and extraction provider;
- contains user hint, provider-compatible image reference, diagnostics, goal, expected result and constraints;
- should be expressible as readable prompt context;
- should not leak provider-specific raw API details into workflow/domain contracts.

Prompt-context style:

```text
Document image context:
- user_mode_hint: auto
- processing_goal: extract_text_and_structure

Image:
- mime_type: image/jpeg
- width: ...
- height: ...
- file_size_bytes: ...
- provider_input: staged image URL

Backend image diagnostics:
- orientation: portrait
- contrast: low
- warnings: low_contrast, possible_skew
- hard_rejection: false

Expected extraction:
- detect document type;
- recognize printed and handwritten text;
- extract fields and values;
- extract tables as grid-like data where possible;
- extract blocks and reading order where useful;
- return warnings and uncertainty explicitly;
- return valid structured output matching the requested schema.
```

Expected future artifacts:

- context model/DTO;
- prompt builder;
- tests that prompt includes key diagnostics and constraints;
- no reliance on Pydantic `Field(description=...)` as the only semantic source.

Out of scope:

- template schema;
- reference image;
- OCR/layout context;
- model-specific prompt optimization.

---

# Этап 2. Settings и runtime boundaries

Status: planned

Цель: подготовить runtime configuration без hidden constants.

Accepted baseline:

- `.env` / environment is runtime source of truth;
- settings layer normalizes runtime configuration;
- OpenRouter/OpenAI model is configured through environment;
- exact model value is not hardcoded in provider/client logic;
- ImgBB is optional staging backend, not business logic;
- SQLite URL comes from settings.

Potential blocks:

## 2.1 Grouped settings

Expected artifacts:

- root settings object;
- grouped LLM/extraction settings;
- storage settings;
- media staging settings;
- Web/backend settings later if needed.

Validation:

- tests for `.env.example` placeholders/defaults;
- tests for missing required secrets where runtime path actually needs them.

## 2.2 LLM/extraction settings

Expected artifacts:

- provider base URL;
- API key;
- model name;
- timeout;
- retry policy if implemented;
- structured output settings;
- provider schema mode if needed.

Rules:

- if `max_retries` exists, retry policy must be implemented or not exposed;
- no hidden model/token defaults outside settings.

## 2.3 Storage/artifact settings

Expected artifacts:

- SQLite database URL;
- artifact root path;
- local upload/originals path;
- previews/results path.

Out of scope:

- production migrations;
- cloud storage;
- deployment config.

---

# Этап 3. SQLite + filesystem artifact skeleton

Status: planned

Цель: создать локальную MVP foundation для jobs, metadata, statuses and artifacts.

Expected artifacts:

- DB bootstrap that explicitly loads model metadata before `create_all`;
- async SQLAlchemy engine/session pattern if selected;
- minimal job model;
- uploaded image metadata model;
- image diagnostics persistence;
- extraction result persistence;
- validation status persistence;
- filesystem layout for original/derived artifacts;
- repositories as DB access boundary.

Rules:

- SQLite is local MVP baseline, not production commitment;
- repositories do CRUD/query/update/flush, not workflow decisions;
- binary image bytes should not be stored in DB;
- filesystem stores original and derived artifacts;
- DB stores metadata and paths.

Out of scope:

- full migration system;
- PostgreSQL;
- multi-user auth;
- batch jobs;
- production cleanup policies.

Validation:

- repository tests with local/in-memory SQLite;
- DB bootstrap test from clean import path;
- no real external API calls.

---

# Этап 4. Image ingestion and diagnostics implementation

Status: planned

Цель: accept image input and produce `ImageDiagnostics`.

Expected artifacts:

- image validation;
- metadata extraction with Pillow;
- initial warnings;
- hard reject for unreadable/unsupported files;
- persisted source artifact;
- tests with local fixtures.

Potential warnings:

- invalid_image;
- unsupported_format;
- too_large;
- too_small;
- low_resolution;
- blurred_image;
- low_contrast;
- too_dark;
- too_bright;
- possible_rotation;
- possible_skew;
- exif_orientation_present.

Rules:

- low quality is warning by default;
- only invalid/unreadable or hard policy violations reject;
- diagnostics are backend-owned.

Out of scope:

- OpenCV-heavy preprocessing;
- OCR engine;
- LLM provider call;
- Web UI.

Validation:

- targeted unit tests;
- `uv run ruff check .`;
- `uv run pyright`;
- targeted pytest.

---

# Этап 5. Media staging adapter

Status: planned

Цель: isolate provider-compatible image input.

Expected artifacts:

- media staging port/protocol;
- service/facade;
- staged media model/DTO;
- no-op/local/base64 path if enough for provider;
- ImgBB adapter only if public URLs are required;
- cleanup metadata if using external staging.

Rules:

- business logic must not import ImgBB;
- Web UI must not know staging backend details;
- provider adapter receives provider-compatible image reference through backend context;
- staging failures are explicit.

Out of scope:

- PDF/file staging;
- S3/R2 integration;
- production storage;
- background cleanup scheduler unless separately approved.

Validation:

- fake backend tests;
- injectable HTTP transport tests if ImgBB adapter is implemented;
- no real ImgBB calls in pytest;
- manual upload script only if separately approved.

---

# Этап 6. OpenRouter/OpenAI provider experiment

Status: planned

Цель: connect the first vision-capable extraction provider after contracts/context are ready.

Accepted baseline:

- OpenRouter;
- OpenAI vision-capable model configured through environment;
- no provider lock-in;
- provider adapter boundary.

Expected artifacts:

- provider adapter interface;
- OpenRouter adapter;
- structured-output request;
- response parsing;
- provider errors;
- response format/schema preparation if needed;
- manual smoke path if approved.

Rules:

- provider transport must not validate business semantics;
- backend validates structured output separately;
- prompt explains semantics explicitly;
- prompt-only JSON fallback is not production behavior;
- manual diagnostics are allowed only outside automated tests.

Out of scope:

- multi-provider routing;
- automatic fallback to another model;
- specialized OCR/Document AI provider;
- cost optimization;
- batch extraction.

Validation:

- offline tests with recording/fake client;
- no real LLM calls in pytest;
- optional manual smoke command documented separately.

---

# Этап 7. Structured output validation and reconstruction

Status: planned

Цель: turn untrusted provider output into trusted or partial backend result.

Expected artifacts:

- Pydantic schemas for `ExtractionResult v0`;
- validation error mapping;
- partial result/warning handling;
- detected document type/confidence/mismatch warning;
- fields/tables/blocks validation;
- JSON result contract;
- tests for valid, partial and malformed outputs.

Rules:

- provider output is untrusted;
- backend validation is mandatory;
- malformed output does not silently pass;
- partial usable output should be represented explicitly;
- no silent fallback.

Out of scope:

- human correction workflow;
- ground-truth scoring;
- advanced layout/coordinates;
- template-guided mapping implementation.

Validation:

- schema tests;
- invalid payload tests;
- warning representation tests;
- targeted pytest.

---

# Этап 8. Result views / preview

Status: planned

Цель: make one `ExtractionResult` useful for Web review.

Views:

- source image;
- diagnostics;
- raw text;
- fields;
- tables / DataFrame-like grid preview;
- blocks / structured preview;
- warnings;
- JSON.

Expected artifacts:

- backend view builders or presentation DTOs;
- HTML or Markdown preview;
- table grid representation;
- JSON serialization;
- tests for rendering/view conversion.

Rules:

- rendering/export logic must not call LLM;
- views derive from validated `ExtractionResult`;
- table-like results should be readable as grids where possible;
- JSON remains primary machine-readable output.

Out of scope:

- DOCX/XLSX/PDF/CSV export;
- pixel-perfect reconstruction;
- visual document editor;
- human correction persistence.

Validation:

- renderer/view tests;
- no real API calls.

---

# Этап 9. Backend API and Web shell

Status: planned

Цель: add simple Web carrier after backend contracts are stable.

Expected Web features:

- upload image;
- choose document mode hint;
- source image preview;
- processing status;
- diagnostics display;
- raw text display;
- fields display;
- tables/grid display;
- blocks/preview display;
- warnings display;
- JSON display;
- basic review.

Rules:

- Web UI is shell/carrier;
- Web UI does not own business logic;
- Web UI does not call LLM/provider directly;
- Web UI does not manage staging backend details;
- API should reuse backend contracts.

Open choices before implementation:

- backend framework;
- frontend framework;
- server-rendered vs SPA;
- local-only vs deployable;
- sync vs async processing.

Out of scope:

- auth/accounts;
- production deployment;
- payments;
- collaboration;
- advanced editor;
- final export UX.

Validation:

- API tests without real provider;
- UI smoke/manual check;
- no real LLM calls in automated tests.

---

# Этап 10. Manual smoke and review

Status: planned

Цель: manually validate the first happy path with real provider calls only when explicitly invoked.

Expected artifacts:

- manual smoke script or documented command if approved;
- one or two sample images;
- expected review checklist;
- non-secret debug/settings output;
- no sample secrets in repo.

Checklist:

- source image accepted;
- diagnostics produced;
- staging works if enabled;
- provider returns structured output;
- validation succeeds or partial result is explicit;
- raw text is shown;
- fields are shown;
- table/grid is shown if detected;
- blocks/preview are shown;
- warnings are shown;
- JSON is available.

Rules:

- manual smoke can call real API;
- pytest must not call real API;
- debug output must not print secrets;
- sample data must be safe to commit or kept out of repo.

---

# Этап 11. PROJECT_MAP later

Status: deferred

`PROJECT_MAP.md` should be created only after actual architecture/code structure exists.

Create it when there are factual runtime layers, entrypoints, contracts, storage, provider path and Web/API boundaries to document.

Do not create `PROJECT_MAP.md` as planning fiction.

---

# Current next safe step

Before first product implementation, Command Center should approve:

1. exact first code block;
2. whether to start with contracts-only or settings + contracts;
3. whether first implementation task should be audit-only or implementation;
4. validation commands for that task.

Recommended first code direction:

```text
Implement minimal contracts/schemas for:
- job lifecycle;
- document mode hints;
- ImageDiagnostics;
- ProviderInputContext;
- ExtractionResult v0.

No provider calls.
No Web UI.
No SQLite yet.
No external API.
```

This gives the rest of the project a stable base for small implementation tasks.
