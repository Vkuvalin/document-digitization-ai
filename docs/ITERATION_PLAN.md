# Iteration Plan — Document Digitization AI

Status: active operational plan  
Mode: backend-first MVP planning and implementation  
Current planning phase: Codex mega-task preparation  
Web/UI track: intentionally deferred  
Reports: private/untracked unless explicitly approved otherwise

---

## 1. Purpose

This document is the operational implementation plan for the `document-digitization-ai` project.

It serves as the main product route for Codex implementation work. It should help Codex understand:

- what has already been implemented;
- what must not be reimplemented;
- what the next backend stages are;
- which gates must be passed before moving forward;
- where Codex must stop and report back to Command Center;
- which scope is explicitly forbidden for the current backend track.

This plan is not a replacement for `AGENTS.md`, local workflow files, skills, or project guardrails.

Codex must follow:

1. `AGENTS.md`;
2. approved local workflow files and skills;
3. this iteration plan;
4. the current task prompt.

When these sources conflict, Codex must stop and report the conflict instead of guessing.

---

## 2. Current Strategic Direction

The project is an image-first document digitization backend.

The MVP target is not “OCR wrapper behavior”. The backend should become a structured document AI pipeline that can:

- accept one uploaded image of a document/form;
- preserve the original image as an artifact;
- run deterministic image diagnostics before any provider call;
- persist job metadata, status, diagnostics and later extraction results;
- prepare provider-ready input through explicit boundaries;
- call a vision-capable extraction provider only after staging/provider gates are approved;
- validate untrusted provider output;
- store a structured extraction result;
- expose the result later to a Web/UI layer.

The current track intentionally excludes Web/UI work. Web design and Web architecture will be handled separately.

---

## 3. Completed Baseline

The following stages are completed and should be treated as existing project foundation.

Codex must inspect the actual repository before making changes, but should not redesign or reimplement these layers unless a later task explicitly asks for refactor.

### Stage 0 — Documentation Baseline

Completed.

Created and maintained initial source-of-truth project documents:

- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE_DRAFT.md`
- `docs/ITERATION_PLAN.md`

Purpose:

- define project intent;
- preserve backend-first architecture decisions;
- prevent premature Web/provider/UI coupling;
- keep MVP scope narrow and image-first.

### Stage 1 — Core Contracts and Schemas

Completed.

Implemented foundational contracts for:

- job lifecycle;
- job statuses;
- document mode hints;
- warnings;
- image diagnostics shape;
- extraction result v0 shape;
- fields, tables, blocks and metadata;
- lifecycle transition validation.

Expected existing package area:

- `src/document_digitization_ai/contracts/`
- `tests/contracts/`

Important decisions:

- provider output is untrusted;
- validation must be backend-owned;
- `ExtractionResult` is the shared base for later result views;
- document mode hint is user guidance, not truth;
- no silent fallback behavior.

### Stage 2 — Deterministic Image Diagnostics

Completed.

Implemented deterministic image diagnostics before any provider or LLM call.

Expected existing package area:

- `src/document_digitization_ai/diagnostics/`
- `tests/diagnostics/`

Implemented behavior includes:

- file existence / readability checks;
- MIME and image format detection via Pillow;
- image dimensions;
- file size;
- SHA-256;
- EXIF orientation signal;
- basic brightness / contrast heuristics;
- hard rejects for invalid image, too-large file, and too-small dimensions;
- warnings for low quality signals.

Important boundaries:

- no OCR;
- no layout analysis;
- no OpenCV;
- no NumPy/scikit-image;
- no blur/skew detection in the current baseline.

### Stage 3 — Runtime Settings Layer

Completed.

Implemented typed runtime settings.

Expected existing package area:

- `src/document_digitization_ai/core/`
- `tests/core/`

Implemented behavior includes:

- `AppSettings`;
- grouped settings for environment, database, storage, OpenRouter, extraction, media staging, and image diagnostics;
- `.env` / environment source of truth;
- cached `get_settings()`;
- explicit secret validation helpers;
- no real secrets required for local import/tests;
- `ImageDiagnosticsSettings.to_diagnostics_config()`;
- `ProviderSchemaMode`;
- `MediaStagingBackend`.

Important boundaries:

- settings must not create directories on import;
- settings must not connect to DB on import;
- settings must not call providers;
- placeholder secrets fail only through explicit runtime helper methods.

### Stage 4 — Local Persistence Foundation

Completed.

Implemented local persistence foundation.

Expected existing package areas:

- `src/document_digitization_ai/db/`
- `src/document_digitization_ai/storage/`
- `tests/db/`
- `tests/storage/`

Implemented behavior includes:

- async SQLAlchemy engine/session helpers;
- SQLite + `aiosqlite` support;
- self-contained DB schema bootstrap;
- `DocumentJob` persistence model;
- `DocumentJobRepository`;
- lifecycle transition validation inside repository status updates;
- filesystem artifact layout helper;
- deterministic artifact paths for uploads and results.

Important boundaries:

- repository methods flush but do not own commit/rollback lifecycle;
- artifact helpers compute paths and create directories only through explicit methods;
- no Alembic yet;
- no provider calls;
- no media staging client;
- no Web/API layer.

### Stage 5 — Local Document Intake Workflow

Completed.

Implemented first local backend workflow slice.

Expected existing package area:

- `src/document_digitization_ai/services/`
- `tests/services/`

Implemented behavior includes:

- `DocumentIntakeService`;
- pre-job validation for source image path;
- job creation;
- artifact directory creation;
- original image copy into job upload artifact path;
- deterministic image diagnostics on stored artifact;
- upload metadata persistence;
- diagnostics persistence;
- lifecycle transitions through repository;
- typed intake result.

Important behavior:

- missing, directory, or extensionless source paths fail before job creation;
- failures after job creation attempt to mark job as `FAILED`;
- provider context, media staging, prompts and extraction calls are not implemented here.

### Stage 6 — Local Application Runtime

Completed.

Implemented application-level runtime wiring for local intake.

Expected existing package area:

- `src/document_digitization_ai/application/`
- `tests/application/`

Implemented behavior includes:

- `LocalDocumentApplication`;
- engine/session factory creation from `AppSettings`;
- explicit `initialize_database()`;
- local intake entrypoint;
- commit on success;
- rollback on failure;
- explicit engine disposal through `close()`.

Important boundaries:

- no global engine/session side effects at import time;
- database initialization remains explicit;
- OpenRouter and ImgBB secrets are not required;
- Web/API/provider/media staging remain out of scope.

---

## 4. Current Repository Baseline

At the start of the next implementation planning cycle, the repository should contain a backend-only local foundation:

- contracts;
- diagnostics;
- runtime settings;
- async DB foundation;
- filesystem artifact layout;
- local document intake service;
- local application runtime.

This baseline is sufficient to run local image intake without external API calls.

The next stages should build provider/media/extraction boundaries on top of this baseline without rewriting it.

---

## 5. Temporary Planning Note

The project is currently in a temporary planning cycle.

The immediate goal is to rewrite this iteration plan into a detailed operational plan for larger Codex task execution.

After this plan is updated and approved, the project returns to the main implementation loop.

The next Codex implementation tasks should be larger than earlier micro-iterations, but still bounded by explicit stages, gates, reports and stop conditions.

---

## 6. Operating Rules for Codex

This plan is designed for larger Codex implementation tasks.

Codex should use this document as the product route, not as a replacement for local execution rules.

### 6.1 Source Priority

Codex must follow this priority order:

1. `AGENTS.md`;
2. approved local workflow files;
3. explicitly selected skills;
4. this `ITERATION_PLAN.md`;
5. the current task prompt.

If any of these conflict, Codex must stop and report the conflict.

Codex must not silently resolve major conflicts by guessing.

### 6.2 Task Size

Future implementation tasks may cover large bounded slices.

A large slice is acceptable when it remains within one coherent backend route, for example:

- provider input preparation;
- media staging boundary;
- provider adapter integration;
- extraction validation and reconstruction;
- result persistence;
- backend smoke flow.

A large slice is not acceptable when it mixes unrelated layers such as:

- Web UI;
- provider calls;
- staging;
- preview rendering;
- auth;
- multi-page/batch handling;
- deployment;
- unrelated refactors.

If a task becomes too broad during execution, Codex must stop at the nearest safe checkpoint and report.

### 6.3 Skills

Codex may use existing approved skills when they materially improve execution quality.

Codex should not duplicate skill rules inside implementation code or source-of-truth docs.

Use existing skills for their intended purpose:

- use `reasoning-patterns` when route selection is explicitly needed;
- use `subagent-routing` when independent audit coverage or bounded read-only review materially reduces risk;
- use `report-writing` when a preserved analysis/report artifact is explicitly required.

Skills do not replace `AGENTS.md`, approved scope, or this plan.

### 6.4 Subagents

Codex may use approved local subagents when they materially reduce risk, improve independent coverage, or close inspection gaps.

Subagents should not be used ritualistically.

Subagents are especially appropriate for:

- architecture boundary audit;
- test coverage audit;
- docs/source-of-truth consistency audit;
- high-risk stage review before moving across a gate.

Subagents must be bounded and read-only unless their own instructions and the current task explicitly allow otherwise.

Subagent findings are findings and recommendations only. They do not approve implementation decisions.

### 6.5 Reports

After every major stage or gate in a large Codex task, Codex must create a preserved report using the existing `report-writing` skill.

Reports must be private/untracked unless Command Center explicitly approves otherwise.

Default location:

- `docs/codex/reports/`

Reports are not source of truth.

A report may preserve:

- what was done;
- what was inspected;
- changed files;
- validation results;
- findings;
- risks;
- interpretation;
- recommendations;
- open questions.

A report must not:

- approve implementation;
- silently change architecture decisions;
- replace source-of-truth docs;
- authorize moving through a blocked gate.

Durable decisions from reports may be moved into source-of-truth docs only after explicit Command Center approval.

### 6.6 Docs Updates

Codex may update source-of-truth docs when the update is directly useful for implementation continuity, consistency, or avoiding stale guidance.

Allowed docs updates may include:

- marking completed stages;
- clarifying current stage status;
- recording approved decisions;
- updating next-stage boundaries;
- noting explicit stop conditions or open questions.

Codex must avoid noisy docs churn.

Codex must not rewrite source-of-truth docs broadly unless the task explicitly asks for it.

Reports under `docs/codex/reports/` remain private/untracked and do not count as source-of-truth docs.

### 6.7 Git / Commit Behavior

Unless explicitly instructed otherwise, Codex should not commit automatically.

For each major stage, Codex should report:

- changed files;
- dependency changes;
- validation commands and results;
- git status summary;
- risks and follow-up;
- whether the stage is ready for Command Center review.

Command Center decides when to commit and push.

### 6.8 Validation Protocol

For implementation stages, Codex must run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
````

If additional checks are relevant to the stage, Codex may run them and report why.

If a validation command cannot be run, Codex must report:

- which command failed to run;
- why;
- what was checked instead;
- residual risk.

### 6.9 Stop Conditions

Codex must stop and report to Command Center when any of the following happens:

- a scope conflict appears;
- source-of-truth docs conflict with code;
- a required secret or external account would be needed;
- a real external API call would be needed but was not explicitly approved;
- Web/UI work becomes necessary;
- provider behavior cannot be validated without a design decision;
- media staging assumptions become provider-specific;
- extraction schema design becomes uncertain;
- validation cannot be made deterministic;
- a stage requires adding unapproved dependencies;
- a migration/Alembic decision becomes necessary;
- an architectural boundary becomes unclear;
- tests would need to rely on real network/provider calls;
- the task cannot be completed without broad unrelated refactor.

When stopping, Codex should leave the repository in the cleanest safe state possible and create a preserved report describing:

- where it stopped;
- what was completed;
- what remains;
- why Command Center input is required.

---

## 7. Global Hard Constraints

These constraints apply to all future backend stages unless Command Center explicitly approves an exception.

### 7.1 Backend-First Boundary

The current implementation track is backend-only.

Allowed backend work:

- contracts;
- diagnostics;
- runtime settings;
- local persistence;
- artifact storage;
- media/provider boundaries;
- provider input context;
- extraction provider adapters;
- extraction validation;
- structured result persistence;
- backend smoke workflows;
- docs updates that preserve approved decisions.

Forbidden in the current track:

- Web UI;
- frontend routing;
- CSS/design systems;
- browser-side upload UX;
- auth/user accounts;
- deployment;
- public API productization unless explicitly approved;
- batch processing;
- multi-page document handling;
- preview rendering/export unless explicitly approved later.

If Web/UI becomes necessary to proceed, Codex must stop and report.

### 7.2 Image-First MVP Boundary

The MVP remains image-first.

Allowed:

- one local/uploaded image per job;
- mixed handwritten/printed document image;
- user-provided document mode hint;
- Auto mode;
- deterministic image diagnostics;
- provider-ready image input preparation.

Forbidden unless explicitly approved:

- PDFs;
- multi-page documents;
- batch uploads;
- document splitting;
- page ordering;
- scanner integration;
- mobile capture flow;
- advanced image preprocessing;
- OCR-only fallback.

### 7.3 Provider Boundary

Provider integration must remain isolated behind explicit boundaries.

Allowed later, after the relevant gate:

- provider input context construction;
- provider adapter interfaces;
- OpenRouter/OpenAI-compatible provider implementation;
- structured provider response capture;
- provider raw response preservation where safe;
- deterministic validation of provider output.

Forbidden before explicit provider gate approval:

- real provider calls;
- requiring real OpenRouter secrets for test suite;
- tests that depend on network/API availability;
- provider-specific assumptions leaking into contracts;
- silent provider fallback;
- hidden model switching;
- committing real secrets;
- logging secret values.

Provider output must always be treated as untrusted.

### 7.4 Media Staging Boundary

Media staging must be explicit and replaceable.

Allowed later, after the relevant gate:

- media staging interface/port;
- local/noop staging backend;
- provider-specific staging backend only when approved;
- staged media metadata;
- TTL/expiry modeling;
- verification hooks.

Forbidden before explicit media staging gate approval:

- ImgBB implementation;
- real media upload calls;
- public URL assumptions in core contracts;
- provider code directly uploading files;
- tests that call external media services.

If provider requirements force public image URLs, Codex must stop and report the design pressure before implementing provider-specific staging.

### 7.5 Storage / Database Boundary

Current storage baseline is SQLite + filesystem.

Allowed:

- extending existing DB models where needed for approved backend stages;
- adding repository methods when workflow requires them;
- storing JSON-compatible provider/extraction payloads;
- explicit schema bootstrap for local MVP/testing.

Forbidden unless explicitly approved:

- Alembic/migrations;
- replacing SQLite baseline;
- adding production database deployment assumptions;
- introducing object storage/cloud storage;
- adding queues/background workers;
- changing repository transaction ownership without explicit rationale.

Repository methods should remain persistence-focused.

Application/runtime layer owns commit/rollback boundaries.

### 7.6 Validation Boundary

Validation is backend-owned.

Allowed:

- deterministic validation of provider output;
- reconstructing `ExtractionResult`;
- warnings/errors for partial extraction;
- preserving raw/invalid provider payloads when useful and safe;
- tests with static fixture payloads.

Forbidden:

- trusting provider output directly;
- silently dropping malformed data without warnings/errors;
- returning provider raw output as final result;
- allowing invalid lifecycle transitions;
- making validation depend on real external provider calls.

### 7.7 Dependency Boundary

New dependencies must be justified by the stage.

Allowed existing major dependencies include:

- Pillow;
- pydantic / pydantic-settings;
- SQLAlchemy;
- aiosqlite;
- pytest tooling already present in the project.

Forbidden unless explicitly approved:

- Web frameworks;
- provider SDKs when HTTP standard library/client abstraction is sufficient or undecided;
- OCR engines;
- OpenCV;
- NumPy/scikit-image for diagnostics;
- task queues;
- cloud SDKs;
- auth frameworks;
- PDF libraries;
- heavy rendering/export libraries.

If Codex believes a new dependency is necessary, it must stop or report the rationale before broad implementation.

### 7.8 Testing Boundary

Tests must remain deterministic.

Allowed:

- unit tests;
- integration tests with tmp SQLite and tmp filesystem;
- static fixture provider payloads;
- fake/stub media staging;
- fake/stub provider adapter;
- local generated images.

Forbidden:

- real network calls in test suite;
- real OpenRouter calls in test suite;
- real ImgBB/media hosting calls in test suite;
- tests requiring real secrets;
- tests relying on local user `.env`;
- tests relying on persistent local data directories.

### 7.9 Secret Handling

Secrets must stay out of source control and reports.

Forbidden:

- committing `.env`;
- committing real API keys;
- printing secrets in logs/reports;
- including secrets in test snapshots;
- requiring real secrets for import, unit tests, or local deterministic validation.

Placeholder values may exist in `.env.example`.

Runtime helpers may fail explicitly when a real provider/media action requires a missing secret.

### 7.10 Documentation Boundary

Source-of-truth docs may be updated when useful and approved by task scope.

Source-of-truth docs include:

- `docs/PROJECT_CONTEXT.md`
- `docs/ARCHITECTURE_DRAFT.md`
- `docs/ITERATION_PLAN.md`

Reports are not source-of-truth docs.

Reports must remain private/untracked unless Command Center explicitly approves otherwise.

Forbidden:

- broad docs rewrites unrelated to the active stage;
- turning report recommendations into durable decisions without approval;
- changing architecture direction without explicit Command Center decision;
- creating `PROJECT_MAP.md` before the implementation structure is mature enough and Command Center requests it.

### 7.11 Failure Handling Boundary

Failures must be explicit.

Allowed:

- typed project errors;
- lifecycle-safe failed status updates;
- explicit validation errors;
- warnings for partial extraction;
- preserved reports for blocked gates.

Forbidden:

- silent fallback;
- swallowing provider/media/validation errors;
- pretending partial extraction is complete success;
- automatically moving past gates after unresolved high-risk findings.

---

## 8. Future Backend Stage Index

This section lists the future backend stages before the Web/UI track.

Each stage must be detailed separately in this plan before Codex is asked to execute it as part of a large task range.

Command Center may assign Codex one stage, several stages, or a bounded stage range.

Codex must follow the detailed stage definitions, gates, reporting requirements and stop conditions.

### 8.1 Large Task Execution Map

This section defines recommended execution ranges for large Codex tasks.

Codex must execute only the stage range explicitly assigned in the current task prompt.

Codex must not infer permission to continue into later stages.

| Run | Stage range | Purpose | Stop point |
|---|---|---|---|
| Run 1 | Stage 7 → Stage 10 | Provider-neutral preparation: provider context, media staging boundary, fake provider port, prompt/schema package | Stop after Gate 10 |
| Run 2 | Stage 11 → Stage 12 | Validation/reconstruction and deterministic backend fake extraction workflow | Stop after Gate 12 |
| Gated | Stage 13 only | Real OpenRouter provider smoke | Requires explicit Command Center approval |
| Deferred | Web/UI | Web shell, upload UX, preview/result UI | Not part of this backend track |

For each assigned stage, Codex must:

- follow the detailed stage section;
- create the required private/untracked stage report;
- run required validation;
- stop immediately if a stop condition is triggered;
- continue to the next assigned stage only if the current gate is passed and no blocker exists.

Reports remain private/untracked unless Command Center explicitly approves otherwise.

Stage 13 must not be executed unless the current task explicitly approves real provider work.

Web/UI must not be executed from this plan.

--

### Stage 7 — Provider Input Context Boundary

Goal:

Create a provider-agnostic context layer that prepares local job/artifact/diagnostics/settings state for future provider execution.

External calls:

- no provider calls;
- no media uploads;
- no Web/API.

Primary purpose:

Prevent provider adapters from directly depending on DB models, filesystem assumptions, or workflow internals.

### Stage 8 — Media Staging Port and Local/Noop Backend

Goal:

Create an explicit media staging boundary and a local/noop backend for deterministic development and tests.

External calls:

- no real media upload;
- no ImgBB call;
- no provider call;
- no Web/API.

Primary purpose:

Prevent public URL or provider-specific media assumptions from leaking into core workflow.

### Stage 9 — Extraction Provider Port and Fake Provider

Goal:

Create the provider adapter interface and deterministic fake provider.

External calls:

- no real provider calls;
- no network calls;
- no media upload;
- no Web/API.

Primary purpose:

Allow backend extraction workflow to be built and tested before real OpenRouter integration.

### Stage 10 — Extraction Prompt and Schema Package

Goal:

Create deterministic prompt/schema preparation for provider extraction.

External calls:

- no real provider calls;
- no network calls;
- no media upload;
- no Web/API.

Primary purpose:

Separate prompt/schema construction from provider transport and validation.

### Stage 11 — Provider Response Validation and Result Reconstruction

Goal:

Validate untrusted provider-like output and reconstruct internal `ExtractionResult`.

External calls:

- no real provider calls;
- no network calls;
- no Web/API.

Primary purpose:

Ensure provider output never becomes final result without backend-owned deterministic validation.

### Stage 12 — Backend Extraction Workflow Orchestration

Goal:

Create the backend extraction workflow using the existing intake/runtime plus provider context, staging port, fake provider, prompt/schema and validation.

External calls:

- fake/local provider by default;
- no real provider calls unless explicitly approved;
- no real media upload;
- no Web/API.

Primary purpose:

Reach a deterministic backend-only end-to-end extraction flow.

### Stage 13 — Real OpenRouter Provider Smoke Gate

Goal:

Implement and/or manually smoke-test real OpenRouter/OpenAI-compatible provider integration.

External calls:

- real provider calls require explicit Command Center approval;
- real media upload requires separate explicit approval if needed.

Primary purpose:

Validate real provider compatibility only after the fake backend flow is stable.

### Deferred Track — Web/UI

Web/UI is intentionally deferred.

Do not implement:

- Web shell;
- frontend upload flow;
- browser preview;
- UI result rendering;
- API productization for Web;

unless Command Center starts the Web/UI track explicitly.

---

## 9. Stage 7 — Provider Input Context Boundary

Status: planned  
Track: backend-only  
External provider calls: forbidden  
External media upload: forbidden  
Web/UI: forbidden  
Primary risk: provider-specific assumptions leaking too early into core workflow

---

### 9.1 Objective

Create a provider-agnostic input context layer that prepares local backend state for future extraction provider execution.

This stage must answer one question:

> Given an intake-completed job, what clean, typed, provider-neutral information is available for a future provider adapter?

This stage must not call OpenRouter, upload media, build prompts, validate extraction results, or implement provider transport.

---

### 9.2 Why This Stage Exists

The project already has:

- contracts;
- deterministic image diagnostics;
- runtime settings;
- local persistence;
- artifact layout;
- local intake workflow;
- local application runtime.

The next backend layers need a stable boundary before provider work begins.

Provider adapters must not directly depend on:

- raw SQLAlchemy models;
- arbitrary DB/session access;
- filesystem layout internals;
- application runtime internals;
- diagnostics JSON implementation details;
- future Web/API upload behavior.

This stage creates the intermediate object that later stages can use safely.

---

### 9.3 Entry Conditions

Before starting this stage, Codex must verify the repository already contains the completed baseline:

- `src/document_digitization_ai/contracts/`
- `src/document_digitization_ai/diagnostics/`
- `src/document_digitization_ai/core/`
- `src/document_digitization_ai/db/`
- `src/document_digitization_ai/storage/`
- `src/document_digitization_ai/services/`
- `src/document_digitization_ai/application/`

If these layers are missing or materially different from the completed baseline described above, Codex must stop and report the mismatch.

---

### 9.4 Expected Package Area

Preferred package area:

- `src/document_digitization_ai/providers/`

Expected files may include:

- `src/document_digitization_ai/providers/__init__.py`
- `src/document_digitization_ai/providers/context.py`
- `tests/providers/test_context.py`

Codex may choose a different internal file split if it is simpler, but the stage must remain focused on provider input context only.

---

### 9.5 Allowed Changes

Codex may:

- create provider context types;
- create provider context builder/service;
- add provider-context-specific errors;
- add tests for context building and missing-state failures;
- add minor exports;
- add small helper functions if needed for safe diagnostics payload reading;
- update source-of-truth docs only if needed to keep this plan/current stage accurate;
- create a private/untracked stage report under `docs/codex/reports/`.

Codex should avoid changing completed baseline layers unless the change is small, justified, and required by this stage.

---

### 9.6 Forbidden Changes

Codex must not implement:

- OpenRouter calls;
- any real provider transport;
- HTTP client code;
- ImgBB;
- media upload;
- media staging service;
- prompt construction;
- provider schema payload construction;
- extraction result validation;
- extraction workflow orchestration;
- Web/API;
- preview/export/rendering;
- auth/users;
- batch/multi-page processing.

Codex must not add new dependencies for this stage unless it stops and reports a clear rationale.

---

### 9.7 Required Concepts

The stage should introduce typed concepts equivalent to the following.

Exact names may differ.

#### ProviderInputContext

Represents provider-ready backend context before prompt/schema/provider execution.

Should include at least:

- job id;
- current job status;
- user document mode hint;
- stored original image path;
- image MIME type;
- image size bytes;
- image diagnostics summary or diagnostics payload summary;
- image warnings relevant to provider guidance;
- extraction model name or model identifier from settings;
- extraction temperature;
- extraction timeout;
- extraction retry count;
- provider schema mode.

#### ProviderImageInput

Represents the local image artifact available to the provider pipeline.

Should include at least:

- local path;
- MIME type;
- file size bytes;
- optional width/height if safely available from diagnostics payload;
- optional SHA-256 if safely available from diagnostics payload.

#### ProviderDiagnosticsSummary

Represents only the diagnostics information useful before provider execution.

Should include at least:

- whether diagnostics are present;
- warnings;
- basic image quality signals if available;
- hard diagnostic facts needed by future prompt/schema layers.

This summary must not require rerunning image diagnostics.

---

### 9.8 Builder Requirements

Codex must implement a builder or service that constructs `ProviderInputContext` from an existing intake-completed job.

Preferred shape:

- `build_provider_input_context(...)` or `ProviderInputContextBuilder(...)`

The builder should accept already-loaded backend state, for example:

* `DocumentJob`;
* extraction settings or `AppSettings`;
* optionally an explicit artifact path if that is cleaner.

The builder must not open DB sessions by itself.

The builder must not call providers.

The builder must not stage media.

The builder must not create or mutate jobs.

The builder must not update job status.

---

### 9.9 Required Validation Behavior

The builder must fail explicitly with a typed project error when required state is missing or invalid.

Required failure cases:

* job status is before `IMAGE_DIAGNOSTICS_READY`;
* source image path is missing;
* source image path does not exist;
* source image path is not a file;
* source image MIME type is missing;
* source image size bytes is missing;
* image diagnostics payload is missing;
* extraction model name is missing or still placeholder;
* provider schema mode is invalid.

The builder must not require:

* OpenRouter API key;
* ImgBB API key;
* real external secrets;
* network access.

Model name validation may use the existing explicit runtime helper behavior, but it must not require provider API key validation.

---

### 9.10 Lifecycle Rule

For this stage, provider input context may be built only for jobs that have completed image diagnostics.

Minimum required status:

* `IMAGE_DIAGNOSTICS_READY`

Codex may allow later statuses only if this is useful, explicit, and tested.

Codex must not allow provider input context construction for:

* `CREATED`;
* `IMAGE_UPLOADED`;
* `FAILED`;
* `CANCELLED`.

If lifecycle semantics are unclear, Codex must stop and report instead of weakening validation.

---

### 9.11 Diagnostics Payload Rule

The provider context builder should use the persisted diagnostics payload.

It should not rerun image diagnostics.

If the existing contracts do not provide full deserialization from JSON payloads, Codex may create a narrow provider-context summary extractor.

Codex should not broadly redesign diagnostics contracts just for this stage.

If a broader `from_dict` contract change appears necessary, Codex must stop and report the reason.

---

### 9.12 Media Staging Rule

This stage is local-image-context only.

Codex must not implement staged media references here unless it is purely an opaque optional placeholder and does not imply:

* public URL;
* ImgBB;
* upload;
* provider-specific transport;
* media TTL;
* external availability.

Preferred approach:

* keep Stage 7 focused on local artifact provider context;
* let Stage 8 extend or adapt context with staged media concepts.

---

### 9.13 Concrete Implementation Steps

Codex should proceed in this order:

1. Inspect current contracts, DB model, repository, settings and diagnostics payload shape.
2. Confirm how `DocumentJob` stores source image metadata and diagnostics payload.
3. Design minimal provider context dataclasses/models.
4. Add provider-context-specific error type.
5. Implement context builder from loaded job + settings/extraction settings.
6. Validate lifecycle status before building context.
7. Validate local image metadata and path.
8. Extract diagnostics summary from existing payload without rerunning diagnostics.
9. Include extraction runtime settings without requiring provider secrets.
10. Add deterministic tests.
11. Run validation commands.
12. Create private stage report using `report-writing`.
13. Stop at Gate 7 for Command Center review if this stage is run as part of a larger Codex task.

---

### 9.14 Test Requirements

Tests must be deterministic and local.

Required test cases:

* builds provider input context for an intake-completed job;
* built context contains job id, mode hint, image metadata, diagnostics summary and extraction settings;
* fails if job status is `CREATED`;
* fails if job status is `IMAGE_UPLOADED`;
* fails if job status is `FAILED`;
* fails if source image path is missing;
* fails if source image file does not exist;
* fails if source image path points to a directory;
* fails if source image MIME type is missing;
* fails if source image size is missing;
* fails if diagnostics payload is missing;
* fails if extraction model name is placeholder;
* does not require OpenRouter API key;
* does not require ImgBB API key;
* does not perform network calls.

Preferred test setup:

* use tmp SQLite and tmp filesystem when integration with actual intake job is useful;
* use generated image files with Pillow if using the real intake service;
* use direct `DocumentJob` construction only when testing narrow missing-state behavior.

---

### 9.15 Validation Commands

Codex must run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

If any command cannot be run, Codex must report why and stop at Gate 7.

---

### 9.16 Stage Report

After completing this stage, Codex must create a private/untracked report using the existing `report-writing` skill.

Default report path:

```text
docs/codex/reports/stage_07_provider_input_context.md
```

The report should include:

* task boundary;
* files changed;
* context types created;
* builder behavior;
* validation behavior;
* tests added;
* validation command results;
* what was intentionally not implemented;
* risks and open questions;
* whether Gate 7 is ready for Command Center review.

The report is not source of truth and must not be committed unless Command Center explicitly approves.

---

### 9.17 Gate 7 — Provider Context Review

Gate 7 is passed only if all conditions are true:

* provider input context exists and is typed;
* context can be built from an intake-completed job;
* builder does not mutate DB/application state;
* builder does not require provider/media secrets;
* builder does not call network;
* missing local state failures are explicit and tested;
* lifecycle restrictions are explicit and tested;
* diagnostics payload is summarized without rerunning diagnostics;
* no media staging/provider/prompt/validation/Web work was introduced;
* validation commands pass;
* private stage report exists.

If any condition fails, Codex must stop and report.

---

### 9.18 Stop Conditions

Codex must stop during this stage if:

* current repository baseline does not match expected completed stages;
* provider context cannot be built without redesigning core contracts;
* diagnostics payload cannot be safely summarized without broad refactor;
* lifecycle status requirements conflict with existing transition rules;
* extraction settings cannot provide model/schema information without requiring provider secrets;
* implementation would require media staging;
* implementation would require prompt/schema decisions;
* implementation would require real provider behavior;
* tests would need network or real secrets;
* a new dependency appears necessary;
* the change would require broad refactor outside provider context.

When stopping, Codex must create a private report explaining the blocker and proposed options.

---

### 9.19 Completion Checklist

Before reporting Stage 7 complete, Codex must verify:

* [ ] provider context package/types created;
* [ ] context builder implemented;
* [ ] builder validates job lifecycle;
* [ ] builder validates local image metadata;
* [ ] builder validates diagnostics payload presence;
* [ ] builder includes extraction settings without requiring API secrets;
* [ ] no provider call code exists;
* [ ] no media staging code exists;
* [ ] no prompt/schema package exists yet;
* [ ] no Web/API code exists;
* [ ] deterministic tests added;
* [ ] `uv run ruff check .` passed;
* [ ] `uv run pyright` passed;
* [ ] `uv run pytest` passed;
* [ ] private stage report created;
* [ ] Gate 7 is ready for Command Center review.

---

## 10. Stage 8 — Media Staging Port and Local/Noop Backend

Status: planned  
Track: backend-only  
Depends on: Stage 7 — Provider Input Context Boundary  
External provider calls: forbidden  
External media upload: forbidden  
Web/UI: forbidden  
Primary risk: leaking public URL / ImgBB / provider-specific media assumptions into core workflow

---

### 10.1 Objective

Create an explicit media staging boundary.

This stage must answer one question:

> How can the backend represent “media prepared for a provider” without assuming public URLs, ImgBB, OpenRouter, or any specific provider transport?

This stage must not upload files, call external services, call providers, build prompts, or validate extraction results.

---

### 10.2 Why This Stage Exists

Different vision providers may accept image input differently:

- local file path in local/fake workflows;
- base64 payload;
- uploaded file reference;
- public image URL;
- provider-hosted file id.

The backend must not hardcode any one of these into core contracts.

Media staging must become a replaceable boundary between:

- local stored artifacts;
- future provider adapters;
- provider-specific transport requirements.

---

### 10.3 Entry Conditions

Before starting this stage, Codex must verify:

- completed baseline stages exist;
- Stage 7 provider input context exists;
- provider input context does not already hardcode public URL assumptions;
- tests from previous stages pass.

If Stage 7 is missing, incomplete, or provider-specific, Codex must stop and report before implementing Stage 8.

---

### 10.4 Expected Package Area

Preferred package area:

- `src/document_digitization_ai/media/`

Expected files may include:

- `src/document_digitization_ai/media/__init__.py`
- `src/document_digitization_ai/media/base.py`
- `src/document_digitization_ai/media/local.py`
- `tests/media/test_staging.py`

Codex may choose a different file split if it remains focused and clear.

---

### 10.5 Allowed Changes

Codex may:

- create media staging port/interface;
- create typed staged media reference/result objects;
- create local/noop media staging backend;
- create media staging errors;
- add tests for local/noop staging;
- add small integration with provider input context if needed;
- add a small factory/helper based on existing media staging settings if useful;
- add minor exports;
- update source-of-truth docs only when needed for implementation continuity;
- create a private/untracked stage report.

Codex should avoid changing Stage 7 provider context broadly unless required.

---

### 10.6 Forbidden Changes

Codex must not implement:

- ImgBB real upload;
- public URL upload;
- external media hosting;
- real provider calls;
- OpenRouter integration;
- HTTP client code for staging;
- prompt construction;
- extraction validation;
- extraction workflow orchestration;
- Web/API;
- preview/export/rendering;
- auth/users;
- batch/multi-page processing.

Codex must not add new dependencies for this stage unless it stops and reports a clear rationale.

---

### 10.7 Required Concepts

The stage should introduce typed concepts equivalent to the following.

Exact names may differ.

#### MediaStagingPort

A provider-agnostic interface/protocol for staging media.

Expected behavior:

- accepts local artifact information;
- returns typed staged media reference/result;
- raises explicit errors for unsupported or invalid input;
- does not know about DB sessions or job lifecycle;
- does not call extraction providers.

#### StagedMediaReference

Represents media prepared for future provider consumption.

Should include at least:

- reference kind/type;
- local path or opaque reference value;
- MIME type;
- file size bytes;
- optional SHA-256 if available;
- optional expiry/TTL only if meaningful;
- metadata dict only if needed and controlled.

Allowed reference kinds may include:

- `local_file`;
- `none`;
- future `public_url`;
- future `provider_file_id`.

For this stage, only local/noop behavior is required.

#### MediaStagingResult

Represents the result of a staging operation.

Should include at least:

- staged media reference;
- whether external upload was performed;
- warnings if any.

For local/noop backend:

- external upload must be `False`.

#### MediaStagingError

Explicit typed error for staging failures.

---

### 10.8 Local/Noop Backend Requirements

Codex must implement a deterministic local/noop backend.

The local/noop backend should:

- accept a local image artifact path;
- verify the file exists;
- verify the path is a file;
- preserve MIME type and size metadata from provider context or explicit input;
- return a local-file staged media reference;
- perform no network calls;
- perform no upload;
- create no public URL;
- not require ImgBB API key;
- not require OpenRouter API key.

The local/noop backend may be named:

- `LocalMediaStagingService`;
- `NoopMediaStagingService`;
- `LocalFileMediaStaging`;
- or similar.

The name should make clear that it does not upload externally.

---

### 10.9 Settings Integration Rule

Existing settings already include media staging configuration.

For this stage:

- default `MEDIA_STAGING_BACKEND=none` should remain safe;
- local/noop staging should not require secrets;
- `IMGBB_API_KEY` must not be required;
- real `imgbb` behavior must not be implemented.

Codex may add a small factory/helper if useful, for example:

- `build_media_staging_service(settings.media_staging)`

But the factory must not instantiate real external clients.

If current `MediaStagingBackend` enum is insufficient, Codex may propose a minimal extension, but must avoid broad config redesign.

Preferred approach:

* treat `none` as local/noop behavior for deterministic backend development;
* do not add a new backend enum unless it materially improves clarity.

---

### 10.10 Provider Context Integration Rule

Stage 8 may integrate staged media references with Stage 7 provider input context.

Allowed integration:

* provider input context may carry optional `staged_media`;
* a helper may return a new context with staged media attached;
* no mutation of DB/application state is required;
* no provider-specific request shape is required.

Forbidden integration:

* requiring public URLs;
* assuming OpenRouter needs a URL;
* hardcoding ImgBB;
* embedding provider request payloads;
* triggering media staging automatically inside provider context builder.

Preferred approach:

* keep provider context local-first;
* let media staging be an explicit separate operation;
* allow future provider adapters to decide whether staged media is required.

---

### 10.11 Concrete Implementation Steps

Codex should proceed in this order:

1. Inspect Stage 7 provider context implementation.
2. Identify the local image artifact representation already available.
3. Design minimal media staging types and error type.
4. Implement media staging port/protocol.
5. Implement local/noop backend.
6. Add optional provider-context integration only if simple and clearly useful.
7. Add deterministic tests.
8. Verify no external calls exist.
9. Run validation commands.
10. Create private stage report using `report-writing`.
11. Stop at Gate 8 for Command Center review if this stage is run as part of a larger Codex task.

---

### 10.12 Test Requirements

Tests must be deterministic and local.

Required test cases:

* local/noop staging returns a local-file staged reference;
* staged reference includes path, MIME type and size;
* external upload flag is false;
* missing file fails explicitly;
* directory path fails explicitly;
* staging does not require OpenRouter API key;
* staging does not require ImgBB API key;
* staging does not perform network calls;
* provider context can carry staged media if integration is implemented;
* settings-driven factory returns local/noop behavior for safe default if factory is implemented.

Preferred test setup:

* use `tmp_path`;
* create small generated image files with Pillow or simple binary files where image decoding is not required;
* do not use real `.env`;
* do not use persistent local data directories.

---

### 10.13 Validation Commands

Codex must run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

If any command cannot be run, Codex must report why and stop at Gate 8.

---

### 10.14 Stage Report

After completing this stage, Codex must create a private/untracked report using the existing `report-writing` skill.

Default report path:

```text
docs/codex/reports/stage_08_media_staging_boundary.md
```

The report should include:

* task boundary;
* files changed;
* media staging types created;
* local/noop backend behavior;
* settings integration, if any;
* provider context integration, if any;
* validation command results;
* what was intentionally not implemented;
* risks and open questions;
* whether Gate 8 is ready for Command Center review.

The report is not source of truth and must not be committed unless Command Center explicitly approves.

---

### 10.15 Gate 8 — Media Staging Boundary Review

Gate 8 is passed only if all conditions are true:

* media staging port/boundary exists;
* local/noop backend exists and is tested;
* no real external upload exists;
* no ImgBB implementation exists;
* no provider call exists;
* no public URL assumption leaks into core workflow;
* local/noop staging does not require secrets;
* provider context integration, if present, remains optional and provider-neutral;
* validation commands pass;
* private stage report exists.

If any condition fails, Codex must stop and report.

---

### 10.16 Stop Conditions

Codex must stop during this stage if:

* Stage 7 provider context is missing or provider-specific;
* media staging cannot be represented without public URL assumptions;
* current settings force real ImgBB behavior;
* implementation would require external upload;
* implementation would require provider request design;
* implementation would require prompt/schema decisions;
* tests would need network or real secrets;
* a new dependency appears necessary;
* provider context requires broad redesign;
* media staging begins to own DB/session/application lifecycle.

When stopping, Codex must create a private report explaining the blocker and proposed options.

---

### 10.17 Completion Checklist

Before reporting Stage 8 complete, Codex must verify:

* [ ] media staging package/types created;
* [ ] media staging error type created;
* [ ] local/noop backend implemented;
* [ ] missing file handling tested;
* [ ] directory path handling tested;
* [ ] no real upload code exists;
* [ ] no ImgBB implementation exists;
* [ ] no provider call code exists;
* [ ] no prompt/schema package exists yet;
* [ ] no Web/API code exists;
* [ ] no real secrets required;
* [ ] deterministic tests added;
* [ ] `uv run ruff check .` passed;
* [ ] `uv run pyright` passed;
* [ ] `uv run pytest` passed;
* [ ] private stage report created;
* [ ] Gate 8 is ready for Command Center review.

---

## 11. Stage 9 — Extraction Provider Port and Fake Provider

Status: planned  
Track: backend-only  
Depends on: Stage 7 — Provider Input Context Boundary; Stage 8 — Media Staging Port and Local/Noop Backend  
External provider calls: forbidden  
External media upload: forbidden  
Web/UI: forbidden  
Primary risk: real provider transport or provider-specific request assumptions leaking before prompt/schema/validation gates

---

### 11.1 Objective

Create the extraction provider boundary and a deterministic fake provider.

This stage must answer one question:

> How will backend workflow code call “an extraction provider” without knowing whether it is fake, OpenRouter, or another future provider?

This stage must not implement real OpenRouter calls, HTTP transport, prompt construction, schema payload construction, extraction validation, result reconstruction, Web/API, or media upload.

---

### 11.2 Why This Stage Exists

The backend needs a clean seam between:

- provider-independent workflow orchestration;
- provider input context;
- media staging;
- prompt/schema preparation;
- real provider transport;
- provider output validation.

Without this stage, later workflow code may accidentally hardcode OpenRouter behavior or directly depend on fake payloads.

The provider port allows the backend to build and test the extraction workflow with a deterministic fake provider before any real external model call is approved.

---

### 11.3 Entry Conditions

Before starting this stage, Codex must verify:

- completed baseline stages exist;
- Stage 7 provider input context exists;
- Stage 8 media staging boundary exists or the current task explicitly allows Stage 9 to proceed without media staging integration;
- tests from previous stages pass.

If provider input context is missing or provider-specific, Codex must stop and report.

If media staging is missing and provider request design would require staged media, Codex must stop and report.

---

### 11.4 Expected Package Area

Preferred package area:

- `src/document_digitization_ai/extraction/`

Expected files may include:

- `src/document_digitization_ai/extraction/__init__.py`
- `src/document_digitization_ai/extraction/provider.py`
- `src/document_digitization_ai/extraction/fake.py`
- `tests/extraction/test_provider.py`
- `tests/extraction/test_fake_provider.py`

Codex may choose a different file split if it remains focused and clear.

---

### 11.5 Allowed Changes

Codex may:

- create extraction provider port/interface;
- create typed provider request object;
- create typed provider response object;
- create provider error types;
- create deterministic fake provider;
- create static fake provider payload fixtures in tests or code if small and justified;
- add tests for fake provider and provider error behavior;
- add minor exports;
- update source-of-truth docs only when needed for implementation continuity;
- create a private/untracked stage report.

Codex should avoid changing provider input context or media staging broadly unless required by this stage.

---

### 11.6 Forbidden Changes

Codex must not implement:

- real OpenRouter client;
- real HTTP calls;
- provider SDK integration;
- real network transport;
- real media upload;
- ImgBB;
- prompt construction;
- schema payload construction;
- extraction result validation;
- `ExtractionResult` reconstruction;
- extraction workflow orchestration;
- DB persistence changes;
- job lifecycle updates;
- Web/API;
- preview/export/rendering;
- auth/users;
- batch/multi-page processing.

Codex must not add new dependencies for this stage unless it stops and reports a clear rationale.

---

### 11.7 Required Concepts

The stage should introduce typed concepts equivalent to the following.

Exact names may differ.

#### ExtractionProviderPort

A provider-agnostic async interface/protocol for extraction providers.

Expected behavior:

- accepts a typed provider request;
- returns a typed provider response;
- raises explicit provider errors;
- performs no persistence;
- performs no job status updates;
- does not own validation/reconstruction into `ExtractionResult`.

Preferred shape:

```md
class ExtractionProviderPort(Protocol):
    async def extract(self, request: ExtractionProviderRequest) -> ExtractionProviderResponse:
        ...
```

#### ExtractionProviderRequest

Represents the provider call request at the boundary level.

For this stage, it should include only information already available without prompt/schema construction.

Should include at least:

* provider input context from Stage 7;
* optional staged media reference from Stage 8;
* optional provider options object if needed;
* correlation/job id for traceability.

It must not require:

* actual prompt text;
* final schema payload;
* OpenRouter API key;
* network transport;
* Web request context.

If prompt/schema placeholders are needed for interface shape, they must be optional and opaque, not constructed in this stage.

#### ExtractionProviderResponse

Represents raw or semi-structured provider output before backend validation.

Should include at least:

* provider name;
* model name or model identifier used by the provider/fake provider;
* raw payload as JSON-compatible data;
* optional raw text;
* finish/status metadata if useful;
* warnings if any;
* provider timing/token metadata only if deterministic or optional.

This response is not a final `ExtractionResult`.

#### ExtractionProviderError

Typed error for provider boundary failures.

Should be used for:

* fake provider configured failure;
* unsupported request shape;
* missing required provider-boundary data;
* future provider transport errors.

---

### 11.8 Fake Provider Requirements

Codex must implement a deterministic fake provider.

The fake provider should:

* implement the provider port;
* perform no network calls;
* require no secrets;
* return a stable provider response;
* optionally support a configured failure mode for tests;
* not simulate real LLM reasoning;
* not validate final extraction result;
* not persist anything;
* not mutate job lifecycle.

The fake provider may be named:

* `FakeExtractionProvider`;
* `StaticExtractionProvider`;
* `FixtureExtractionProvider`;
* or similar.

The fake provider response should be simple and JSON-compatible.

It may return a provider-like payload that later Stage 11 validation can consume, but it must not require Stage 11 validation to already exist.

---

### 11.9 Prompt/Schema Boundary Rule

This stage must not build extraction prompts or provider schema payloads.

Allowed:

* request object may have optional opaque prompt/schema fields for future compatibility;
* fake provider may ignore prompt/schema fields;
* tests may pass simple placeholder values only if needed for interface stability.

Forbidden:

* designing full prompt text;
* building schema from `ExtractionResult`;
* provider-specific structured output payload;
* OpenRouter response-format logic.

Prompt and schema preparation belongs to Stage 10.

---

### 11.10 Validation Boundary Rule

This stage must not validate provider output into `ExtractionResult`.

Allowed:

* provider response object may guarantee that its payload is JSON-compatible;
* fake provider may return a known payload;
* provider error handling may check boundary-level request validity.

Forbidden:

* reconstructing `ExtractionResult`;
* table normalization;
* partial validation;
* result warnings based on provider payload correctness.

Provider output validation belongs to Stage 11.

---

### 11.11 Persistence and Lifecycle Rule

The provider layer must not import or depend on DB/session/application runtime unless there is an explicit, narrow and justified reason.

Forbidden in provider port/fake provider:

* creating jobs;
* loading jobs;
* updating job status;
* committing/rolling back transactions;
* writing extraction results to DB;
* writing artifact files.

Workflow orchestration and persistence belong to later application/service stages.

---

### 11.12 Concrete Implementation Steps

Codex should proceed in this order:

1. Inspect Stage 7 provider context and Stage 8 media staging types.
2. Design minimal provider request and response types.
3. Define provider port/protocol.
4. Define provider error types.
5. Implement deterministic fake provider.
6. Add tests for success path.
7. Add tests for fake failure path.
8. Add tests proving no secrets/network are required.
9. Check that provider layer does not import DB/session/application runtime.
10. Run validation commands.
11. Create private stage report using `report-writing`.
12. Stop at Gate 9 for Command Center review if this stage is run as part of a larger Codex task.

---

### 11.13 Test Requirements

Tests must be deterministic and local.

Required test cases:

* fake provider returns deterministic response;
* provider response includes provider name, model name and raw JSON-compatible payload;
* fake provider can be configured to raise typed provider error;
* provider request can reference provider input context;
* provider request can optionally reference staged media if Stage 8 integration exists;
* fake provider does not require OpenRouter API key;
* fake provider does not require ImgBB API key;
* fake provider performs no network calls;
* provider layer does not require DB/session/application runtime;
* provider response is not treated as final `ExtractionResult`.

Preferred test setup:

* use simple constructed provider context objects where possible;
* avoid full DB/application integration unless needed;
* do not use real `.env`;
* do not use persistent local data directories;
* do not use network mocking unless necessary to prove no network path exists.

---

### 11.14 Validation Commands

Codex must run:

```bash id="1f86kz"
uv run ruff check .
uv run pyright
uv run pytest
```

If any command cannot be run, Codex must report why and stop at Gate 9.

---

### 11.15 Stage Report

After completing this stage, Codex must create a private/untracked report using the existing `report-writing` skill.

Default report path:

```text id="qzu5kx"
docs/codex/reports/stage_09_extraction_provider_port.md
```

The report should include:

* task boundary;
* files changed;
* provider request/response types created;
* provider port behavior;
* fake provider behavior;
* validation command results;
* what was intentionally not implemented;
* risks and open questions;
* whether Gate 9 is ready for Command Center review.

The report is not source of truth and must not be committed unless Command Center explicitly approves.

---

### 11.16 Gate 9 — Provider Port Review

Gate 9 is passed only if all conditions are true:

* extraction provider port exists;
* typed request and response objects exist;
* fake provider exists and is deterministic;
* provider errors are explicit;
* no real provider transport exists;
* no HTTP/network code exists;
* no provider SDK dependency exists;
* no prompt/schema construction exists;
* no extraction validation/reconstruction exists;
* provider layer does not own persistence or lifecycle;
* no real secrets are required;
* validation commands pass;
* private stage report exists.

If any condition fails, Codex must stop and report.

---

### 11.17 Stop Conditions

Codex must stop during this stage if:

* provider input context is missing or provider-specific;
* media staging boundary is missing and provider request design requires staged media;
* request design requires prompt/schema decisions;
* fake provider cannot be represented without validation logic;
* implementation would require real network transport;
* implementation would require provider SDK dependency;
* implementation would require OpenRouter-specific request shape;
* implementation would require DB/session/application lifecycle ownership;
* tests would need network or real secrets;
* a new dependency appears necessary;
* stage scope starts drifting into extraction workflow orchestration.

When stopping, Codex must create a private report explaining the blocker and proposed options.

---

### 11.18 Completion Checklist

Before reporting Stage 9 complete, Codex must verify:

* [ ] extraction provider package/types created;
* [ ] provider port/protocol implemented;
* [ ] provider request type implemented;
* [ ] provider response type implemented;
* [ ] provider error type implemented;
* [ ] deterministic fake provider implemented;
* [ ] fake success path tested;
* [ ] fake failure path tested;
* [ ] no real provider call code exists;
* [ ] no HTTP/network code exists;
* [ ] no provider SDK dependency added;
* [ ] no prompt/schema package exists yet;
* [ ] no validation/reconstruction code exists yet;
* [ ] no DB/session/application lifecycle ownership in provider layer;
* [ ] no Web/API code exists;
* [ ] deterministic tests added;
* [ ] `uv run ruff check .` passed;
* [ ] `uv run pyright` passed;
* [ ] `uv run pytest` passed;
* [ ] private stage report created;
* [ ] Gate 9 is ready for Command Center review.

---

## 12. Stage 10 — Extraction Prompt and Schema Package

Status: planned  
Track: backend-only  
Depends on: Stage 7 — Provider Input Context Boundary; Stage 9 — Extraction Provider Port and Fake Provider  
External provider calls: forbidden  
External media upload: forbidden  
Web/UI: forbidden  
Primary risk: prompt/schema design becoming provider-specific too early or silently changing the internal `ExtractionResult` contract

---

### 12.1 Objective

Create deterministic prompt and schema preparation for document extraction.

This stage must answer one question:

> How should the backend package extraction instructions and expected structured output shape before a provider adapter sends a request?

This stage must not call OpenRouter, perform HTTP transport, upload media, validate provider output, persist extraction results, or orchestrate the extraction workflow.

---

### 12.2 Why This Stage Exists

Prompt/schema preparation is a separate responsibility from:

- provider transport;
- media staging;
- provider output validation;
- DB persistence;
- application workflow orchestration.

The backend needs a stable prompt/schema package so future real provider adapters can be implemented without inventing extraction instructions inside transport code.

This stage should make provider-facing instructions deterministic, testable, and aligned with the internal `ExtractionResult` v0 shape.

---

### 12.3 Entry Conditions

Before starting this stage, Codex must verify:

- completed baseline stages exist;
- Stage 7 provider input context exists;
- Stage 9 provider port exists;
- core `ExtractionResult` contracts exist;
- provider schema mode settings exist;
- tests from previous stages pass.

If provider input context or core extraction result contracts are missing or unstable, Codex must stop and report.

---

### 12.4 Expected Package Area

Preferred package area:

- `src/document_digitization_ai/extraction/`

Expected files may include:

- `src/document_digitization_ai/extraction/prompts.py`
- `src/document_digitization_ai/extraction/schema.py`
- `tests/extraction/test_prompts.py`
- `tests/extraction/test_schema.py`

Codex may choose a different file split if it remains focused and clear.

---

### 12.5 Allowed Changes

Codex may:

- create prompt package types;
- create schema package types;
- create deterministic prompt builder;
- create deterministic schema payload builder;
- add prompt/schema-specific errors if needed;
- add tests for prompt/schema determinism;
- add minor exports;
- update fake provider request types only if needed to carry prompt/schema packages;
- update source-of-truth docs only when needed for implementation continuity;
- create a private/untracked stage report.

Codex should avoid modifying core `ExtractionResult` contracts unless the current contract is clearly insufficient and Command Center approval is required.

---

### 12.6 Forbidden Changes

Codex must not implement:

- real OpenRouter client;
- HTTP/network calls;
- provider SDK integration;
- real media upload;
- ImgBB;
- provider output validation;
- `ExtractionResult` reconstruction from provider output;
- extraction workflow orchestration;
- DB persistence changes;
- job lifecycle updates;
- Web/API;
- preview/export/rendering;
- auth/users;
- batch/multi-page processing.

Codex must not add new dependencies for this stage unless it stops and reports a clear rationale.

---

### 12.7 Required Concepts

The stage should introduce typed concepts equivalent to the following.

Exact names may differ.

#### ExtractionPromptPackage

Represents the provider-facing instruction package before transport.

Should include at least:

- system/developer-style instruction text if applicable;
- user/task instruction text if applicable;
- document mode hint guidance;
- diagnostics-aware guidance;
- output requirements;
- uncertainty handling instructions;
- hallucination avoidance instructions;
- optional prompt metadata.

The prompt package must be deterministic for the same input context.

#### ExtractionSchemaPackage

Represents the structured output expectation for provider response.

Should include at least:

- schema mode;
- JSON-compatible schema payload or schema descriptor;
- target internal result version;
- required top-level sections;
- constraints relevant to fields/tables/blocks/warnings/metadata.

The schema package must align with the current internal `ExtractionResult` v0 contract.

#### ExtractionRequestPackage

Optional combined object that contains:

- provider input context;
- prompt package;
- schema package.

This is optional. Codex may instead keep prompt and schema packages separate if that is cleaner.

---

### 12.8 Prompt Requirements

The prompt builder must produce deterministic instructions.

The prompt should instruct the provider to:

- extract structured information from the document image;
- preserve uncertainty;
- avoid inventing missing information;
- distinguish printed text, handwriting and uncertain marks where possible;
- preserve field labels and values where possible;
- represent tables structurally when visible;
- include warnings when content is unclear;
- not treat the user document mode hint as guaranteed truth;
- use diagnostics warnings as guidance, not as final judgment.

The prompt must not:

- claim image quality facts not present in diagnostics/context;
- ask for unsupported output sections;
- depend on Web/UI behavior;
- include provider secrets;
- include local filesystem details that are not needed by the provider;
- include internal DB implementation details.

---

### 12.9 Document Mode Hint Rule

Document mode hint is guidance, not truth.

The prompt builder must handle at least the existing mode hints:

- `auto`;
- `form`;
- `table`;
- `free_handwritten_text`;
- `mixed_document`;
- `plain_text`.

Required behavior:

- `auto` should ask the provider to infer structure carefully;
- `form` should bias toward label/value extraction;
- `table` should bias toward tabular extraction;
- `free_handwritten_text` should bias toward preserving reading order and uncertainty;
- `mixed_document` should allow fields, tables and free-text blocks;
- `plain_text` should bias toward raw text/blocks.

The prompt must not force the output to match the hint when the image contradicts it.

---

### 12.10 Diagnostics Guidance Rule

Diagnostics may influence provider guidance.

Allowed diagnostics guidance:

- low resolution warning may ask provider to preserve uncertainty;
- low contrast warning may ask provider to mark unclear text;
- too dark / too bright warning may ask provider to avoid overconfident extraction;
- EXIF orientation signal may be mentioned only if useful and safe.

Forbidden diagnostics behavior:

- rerunning diagnostics;
- treating diagnostics warnings as extraction results;
- hiding diagnostics warnings from later validation;
- making prompt behavior depend on untested heuristics.

---

### 12.11 Schema Requirements

The schema package should target the internal `ExtractionResult` v0 shape.

It should represent expected output sections equivalent to:

- document-level information;
- raw text;
- fields;
- tables;
- blocks;
- warnings;
- metadata.

The schema must preserve the principle:

> Provider output is untrusted and must be validated later.

The schema package may be provider-neutral or provider-adaptable, but it must not hardcode OpenRouter transport behavior.

---

### 12.12 Provider Schema Mode Rule

Existing settings include `ProviderSchemaMode`.

The schema builder must support approved schema modes.

Expected modes:

- `compact`;
- `full`.

Required behavior:

- `compact` should produce a smaller/minimal schema descriptor suitable for simpler provider payloads;
- `full` should produce a more explicit schema descriptor with stronger structure and descriptions;
- both modes must target the same internal `ExtractionResult` v0 concept;
- invalid schema modes should fail before this stage or through typed validation.

Codex must not add new schema modes unless it stops and reports the rationale.

---

### 12.13 Provider Boundary Rule

This stage prepares prompt/schema packages only.

Allowed:

- provider request type from Stage 9 may be extended to carry prompt/schema package;
- fake provider tests may verify request contains prompt/schema package;
- prompt/schema packages may be JSON-compatible.

Forbidden:

- sending requests;
- implementing OpenRouter response format;
- adding HTTP clients;
- requiring provider API key;
- requiring media staging upload;
- choosing a real model-specific prompt workaround without reporting.

---

### 12.14 Concrete Implementation Steps

Codex should proceed in this order:

1. Inspect `ExtractionResult` contracts.
2. Inspect `DocumentModeHint`.
3. Inspect `ProviderSchemaMode`.
4. Inspect Stage 7 provider input context.
5. Design minimal prompt package type.
6. Design minimal schema package type.
7. Implement deterministic prompt builder.
8. Implement deterministic schema builder.
9. Add optional combined extraction request package only if useful.
10. Add tests for all document mode hints.
11. Add tests for diagnostics guidance.
12. Add tests for compact/full schema modes.
13. Add tests proving no provider/network/secrets are required.
14. Run validation commands.
15. Create private stage report using `report-writing`.
16. Stop at Gate 10 for Command Center review if this stage is run as part of a larger Codex task.

---

### 12.15 Test Requirements

Tests must be deterministic and local.

Required test cases:

- prompt package builds deterministically for the same provider input context;
- prompt includes output requirements aligned with `ExtractionResult` v0;
- prompt handles `auto` mode as guidance, not truth;
- prompt handles each document mode hint;
- diagnostics warnings influence instructions without becoming extraction facts;
- schema package builds deterministically in `compact` mode;
- schema package builds deterministically in `full` mode;
- compact and full modes are different only in approved schema detail level;
- schema package includes fields/tables/blocks/warnings/metadata concepts;
- no OpenRouter API key is required;
- no ImgBB API key is required;
- no network calls happen;
- no provider output validation is performed.

Preferred test setup:

- construct provider input context directly when possible;
- do not use DB/application runtime unless needed;
- do not use real `.env`;
- do not use network mocking unless necessary to prove no network path exists.

---

### 12.16 Validation Commands

Codex must run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
````

If any command cannot be run, Codex must report why and stop at Gate 10.

---

### 12.17 Stage Report

After completing this stage, Codex must create a private/untracked report using the existing `report-writing` skill.

Default report path:

```text
docs/codex/reports/stage_10_extraction_prompt_schema.md
```

The report should include:

* task boundary;
* files changed;
* prompt package behavior;
* schema package behavior;
* document mode hint handling;
* diagnostics guidance behavior;
* schema mode behavior;
* validation command results;
* what was intentionally not implemented;
* risks and open questions;
* whether Gate 10 is ready for Command Center review.

The report is not source of truth and must not be committed unless Command Center explicitly approves.

---

### 12.18 Gate 10 — Prompt and Schema Review

Gate 10 is passed only if all conditions are true:

* prompt package builder exists and is deterministic;
* schema package builder exists and is deterministic;
* all document mode hints are handled;
* diagnostics warnings are used only as guidance;
* compact/full schema modes are tested;
* schema package aligns with `ExtractionResult` v0;
* provider output is still treated as untrusted;
* no real provider transport exists;
* no HTTP/network code exists;
* no media upload exists;
* no extraction validation/reconstruction exists;
* no persistence/lifecycle changes exist in prompt/schema layer;
* no real secrets are required;
* validation commands pass;
* private stage report exists.

If any condition fails, Codex must stop and report.

---

### 12.19 Stop Conditions

Codex must stop during this stage if:

* prompt/schema design requires changing core `ExtractionResult` in a non-backward-compatible way;
* current contracts cannot represent fields/tables/blocks/warnings sufficiently;
* document mode hint semantics are unclear;
* schema mode requirements conflict with provider-neutral design;
* implementation would require OpenRouter-specific response format decisions;
* implementation would require real provider behavior;
* implementation would require media upload;
* tests would need network or real secrets;
* a new dependency appears necessary;
* stage scope starts drifting into provider transport or validation.

When stopping, Codex must create a private report explaining the blocker and proposed options.

---

### 12.20 Completion Checklist

Before reporting Stage 10 complete, Codex must verify:

* [ ] prompt package type created;
* [ ] schema package type created;
* [ ] prompt builder implemented;
* [ ] schema builder implemented;
* [ ] document mode hint handling tested;
* [ ] diagnostics guidance tested;
* [ ] compact schema mode tested;
* [ ] full schema mode tested;
* [ ] schema aligns with `ExtractionResult` v0;
* [ ] provider output remains untrusted;
* [ ] no real provider call code exists;
* [ ] no HTTP/network code exists;
* [ ] no media upload code exists;
* [ ] no validation/reconstruction code exists yet;
* [ ] no DB/session/application lifecycle ownership in prompt/schema layer;
* [ ] no Web/API code exists;
* [ ] deterministic tests added;
* [ ] `uv run ruff check .` passed;
* [ ] `uv run pyright` passed;
* [ ] `uv run pytest` passed;
* [ ] private stage report created;
* [ ] Gate 10 is ready for Command Center review.

---

## 13. Stage 11 — Provider Response Validation and Result Reconstruction

Status: planned  
Track: backend-only  
Depends on: Stage 9 — Extraction Provider Port and Fake Provider; Stage 10 — Extraction Prompt and Schema Package  
External provider calls: forbidden  
External media upload: forbidden  
Web/UI: forbidden  
Primary risk: treating provider output as trusted final application data

---

### 13.1 Objective

Implement backend-owned validation of untrusted provider-like output and deterministic reconstruction into the internal `ExtractionResult` v0 shape.

This stage must answer one question:

> Given a provider response payload, how does the backend validate, normalize, warn, fail, or reconstruct a safe internal extraction result?

This stage must not call providers, upload media, perform HTTP transport, persist results, update job lifecycle, or implement Web/API behavior.

---

### 13.2 Why This Stage Exists

Provider output is untrusted.

Even if a prompt/schema package asks for a specific shape, a model may return:

- missing sections;
- malformed JSON-like structure;
- incorrect field types;
- inconsistent tables;
- hallucinated certainty;
- extra unknown fields;
- partial extraction;
- unusable output.

The backend must not pass provider output directly to final result views.

This stage creates the deterministic validation and reconstruction layer that later workflows can use safely.

---

### 13.3 Entry Conditions

Before starting this stage, Codex must verify:

- completed baseline stages exist;
- Stage 9 provider response type exists;
- Stage 10 prompt/schema package exists;
- core `ExtractionResult` v0 contracts exist;
- warning/error contracts exist;
- tests from previous stages pass.

If provider response shape or `ExtractionResult` contracts are missing or unstable, Codex must stop and report.

---

### 13.4 Expected Package Area

Preferred package area:

- `src/document_digitization_ai/extraction/`

Expected files may include:

- `src/document_digitization_ai/extraction/validation.py`
- `src/document_digitization_ai/extraction/results.py`
- `tests/extraction/test_validation.py`
- `tests/extraction/test_result_reconstruction.py`

Codex may choose a different file split if it remains focused and clear.

---

### 13.5 Allowed Changes

Codex may:

- create provider output validation types;
- create validation error/warning types;
- implement validation of provider response payloads;
- implement reconstruction into `ExtractionResult`;
- implement deterministic normalization helpers;
- add static fixture payloads for tests;
- add minor exports;
- add small helper methods to contracts only if clearly necessary and backward-compatible;
- update source-of-truth docs only when needed for implementation continuity;
- create a private/untracked stage report.

Codex should avoid broad redesign of `ExtractionResult`.

If broad contract redesign appears necessary, Codex must stop and report.

---

### 13.6 Forbidden Changes

Codex must not implement:

- real OpenRouter client;
- HTTP/network calls;
- provider SDK integration;
- real media upload;
- ImgBB;
- prompt construction changes unless strictly needed to align with already-approved schema;
- extraction workflow orchestration;
- DB persistence changes;
- job lifecycle updates;
- application runtime extraction entrypoint;
- Web/API;
- preview/export/rendering;
- auth/users;
- batch/multi-page processing.

Codex must not add new dependencies for this stage unless it stops and reports a clear rationale.

---

### 13.7 Required Concepts

The stage should introduce typed concepts equivalent to the following.

Exact names may differ.

#### ProviderOutputValidationResult

Represents the result of validating a provider response.

Should include at least:

- validation outcome;
- reconstructed `ExtractionResult` when usable;
- validation warnings;
- validation errors;
- normalized provider payload if useful;
- original provider response reference if useful and safe.

Suggested validation outcomes:

- `succeeded`;
- `partial`;
- `failed`.

This should not be a job status. Later workflow code may map validation outcome to job lifecycle status.

#### ExtractionValidationError

Typed error for unusable provider output.

Should be used when the payload cannot be safely reconstructed into `ExtractionResult`.

#### ExtractionValidationWarning

Typed warning or existing warning-compatible object for partial/malformed/non-fatal provider output issues.

Should be used when the payload can still produce a partial or normalized result.

#### ExtractionResultReconstructor

Function or service that converts validated provider-like payload into the internal `ExtractionResult` v0 structure.

Preferred shapes:

```md
validate_provider_output(...)
````

or

```md
reconstruct_extraction_result(...)
```

or a small class if state/config is useful.

---

### 13.8 Provider Payload Assumptions

This stage may define the expected provider-like payload shape used by validation.

The expected shape should align with Stage 10 schema package and the internal `ExtractionResult` v0 contract.

Expected top-level concepts:

* document;
* raw text;
* fields;
* tables;
* blocks;
* warnings;
* metadata.

Validation must not assume the provider always follows the schema.

Validation must handle:

* missing optional sections;
* malformed required sections;
* wrong primitive types;
* extra unknown keys;
* null values;
* partial lists;
* table row/column mismatch.

---

### 13.9 Reconstruction Rules

The reconstructed object must be an internal `ExtractionResult`.

Reconstruction should follow these principles:

* preserve useful provider output only after shape validation;
* normalize simple type mismatches only when safe;
* add warnings for normalization;
* fail explicitly for unusable payloads;
* avoid hallucinated certainty;
* preserve partial extraction as partial, not full success;
* keep raw provider response separate from final result when needed.

The final `ExtractionResult` must not be a raw provider payload.

---

### 13.10 Required Field Handling

Validation should distinguish between:

* required top-level shape needed to reconstruct anything;
* optional sections that may be missing;
* malformed sections that can be skipped with warnings;
* malformed sections that make the whole payload unusable.

Suggested behavior:

* missing `document` may be allowed if the rest of the result is usable, but should produce a warning;
* missing `raw_text` may be allowed, but should produce a warning if no fields/tables/blocks exist;
* missing `fields`, `tables`, or `blocks` should default to empty lists with warnings only when appropriate;
* completely empty result should fail unless explicitly represented as no extractable content with warnings.

Codex may choose exact validation strictness, but it must be deterministic and tested.

---

### 13.11 Table Normalization Rule

Tables require special handling.

Preferred behavior:

* enforce row cell count equal to column count in reconstructed internal table rows;
* if a provider row has fewer cells than columns, pad missing cells with empty strings and add a validation warning;
* if a provider row has more cells than columns, either:

  * truncate extra cells and add a validation warning; or
  * preserve extras only if existing contracts provide a clear place for them.

Codex must test this behavior.

If existing table contracts make this impossible without a broader redesign, Codex must stop and report.

---

### 13.12 Warning Handling Rule

Provider-provided warnings may be useful, but they are also untrusted.

Validation should:

* preserve provider warnings only after validating shape/type;
* add backend validation warnings for normalization and partial extraction;
* distinguish provider-origin warnings from backend validation warnings if the existing warning contract allows it;
* avoid treating provider warnings as proof of correctness.

If the existing warning contract cannot represent origin/severity cleanly, Codex may use the existing warning shape conservatively and report the limitation.

---

### 13.13 Metadata Handling Rule

Metadata may include provider-side information, but it must not become trusted application truth.

Allowed:

* preserve safe metadata such as provider name/model id if already available;
* include validation summary metadata;
* include schema/result version metadata.

Forbidden:

* storing secrets;
* storing raw prompt text if it contains sensitive/local details;
* storing local filesystem internals unless already part of internal artifact records;
* trusting provider-supplied metadata as backend fact.

---

### 13.14 Validation Boundary Rule

This stage validates provider output only.

It must not:

* call extraction provider port;
* call fake provider as part of normal validation code;
* open DB sessions;
* update job lifecycle;
* write files;
* commit transactions;
* stage media;
* build prompts.

Tests may use fake/static provider responses as fixtures.

---

### 13.15 Concrete Implementation Steps

Codex should proceed in this order:

1. Inspect current `ExtractionResult` contracts.
2. Inspect current warning and table contracts.
3. Inspect Stage 9 provider response type.
4. Inspect Stage 10 schema package expectations.
5. Design validation outcome types.
6. Design validation error/warning behavior.
7. Implement validation of top-level payload.
8. Implement field reconstruction.
9. Implement table reconstruction and normalization.
10. Implement block/raw text reconstruction.
11. Implement warning/metadata handling.
12. Add deterministic valid payload tests.
13. Add partial payload tests.
14. Add malformed/unusable payload tests.
15. Add table mismatch tests.
16. Run validation commands.
17. Create private stage report using `report-writing`.
18. Stop at Gate 11 for Command Center review if this stage is run as part of a larger Codex task.

---

### 13.16 Test Requirements

Tests must be deterministic and local.

Required test cases:

* valid provider-like payload reconstructs `ExtractionResult`;
* reconstructed result is not raw provider payload;
* missing optional sections are handled deterministically;
* partial payload produces validation warnings;
* unusable payload fails explicitly;
* wrong top-level type fails explicitly;
* malformed fields are skipped or fail according to deterministic rules;
* malformed table rows produce warnings;
* fewer table cells than columns are padded and warned;
* extra table cells are handled deterministically and warned;
* provider warnings are validated before preservation;
* unknown extra keys do not silently become internal result fields;
* validation does not require OpenRouter API key;
* validation does not require ImgBB API key;
* validation performs no network calls;
* validation does not open DB sessions;
* validation does not update job lifecycle.

Preferred test setup:

* use static JSON-compatible payload fixtures;
* avoid full DB/application integration;
* do not use real `.env`;
* do not use network mocking unless necessary to prove no network path exists.

---

### 13.17 Validation Commands

Codex must run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

If any command cannot be run, Codex must report why and stop at Gate 11.

---

### 13.18 Stage Report

After completing this stage, Codex must create a private/untracked report using the existing `report-writing` skill.

Default report path:

```text
docs/codex/reports/stage_11_provider_output_validation.md
```

The report should include:

* task boundary;
* files changed;
* validation outcome types;
* reconstruction behavior;
* partial-result behavior;
* table normalization behavior;
* warning/metadata behavior;
* validation command results;
* what was intentionally not implemented;
* risks and open questions;
* whether Gate 11 is ready for Command Center review.

The report is not source of truth and must not be committed unless Command Center explicitly approves.

---

### 13.19 Gate 11 — Validation and Reconstruction Review

Gate 11 is passed only if all conditions are true:

* provider output validation exists;
* reconstruction into `ExtractionResult` exists;
* provider output remains untrusted;
* valid payload reconstruction is tested;
* partial payload behavior is tested;
* unusable payload failure is tested;
* table mismatch normalization is tested;
* warnings are explicit;
* validation layer does not own provider calls;
* validation layer does not own DB/session/application lifecycle;
* validation layer does not update job statuses;
* no real secrets are required;
* no network calls exist;
* validation commands pass;
* private stage report exists.

If any condition fails, Codex must stop and report.

---

### 13.20 Stop Conditions

Codex must stop during this stage if:

* `ExtractionResult` cannot represent necessary validated data without broad redesign;
* table normalization cannot be implemented safely with current contracts;
* warning contract cannot represent required validation warnings even conservatively;
* schema package and validation expectations conflict;
* provider response type from Stage 9 is too vague for safe validation;
* implementation would require real provider behavior;
* implementation would require DB/session/application lifecycle;
* tests would need network or real secrets;
* a new dependency appears necessary;
* stage scope starts drifting into extraction workflow orchestration.

When stopping, Codex must create a private report explaining the blocker and proposed options.

---

### 13.21 Completion Checklist

Before reporting Stage 11 complete, Codex must verify:

* [ ] validation outcome type created;
* [ ] validation error type created;
* [ ] validation warning behavior implemented;
* [ ] provider payload validation implemented;
* [ ] reconstruction into `ExtractionResult` implemented;
* [ ] valid payload test added;
* [ ] partial payload test added;
* [ ] unusable payload test added;
* [ ] table row/column mismatch tests added;
* [ ] provider warnings handling tested;
* [ ] unknown keys handling tested;
* [ ] no real provider call code added;
* [ ] no HTTP/network code added;
* [ ] no media upload code added;
* [ ] no DB/session/application lifecycle ownership added;
* [ ] no Web/API code added;
* [ ] deterministic tests added;
* [ ] `uv run ruff check .` passed;
* [ ] `uv run pyright` passed;
* [ ] `uv run pytest` passed;
* [ ] private stage report created;
* [ ] Gate 11 is ready for Command Center review.

---

## 14. Stage 12 — Backend Extraction Workflow Orchestration

Status: planned  
Track: backend-only  
Depends on: Stage 7 — Provider Input Context Boundary; Stage 8 — Media Staging Port and Local/Noop Backend; Stage 9 — Extraction Provider Port and Fake Provider; Stage 10 — Extraction Prompt and Schema Package; Stage 11 — Provider Response Validation and Result Reconstruction  
External provider calls: forbidden by default  
External media upload: forbidden by default  
Web/UI: forbidden  
Primary risk: mixing workflow orchestration with provider transport, validation internals, persistence internals, or future Web/API concerns

---

### 14.1 Objective

Create the backend extraction workflow that connects the already approved backend boundaries into a deterministic local/fake end-to-end extraction path.

This stage must answer one question:

> Starting from an intake-completed job, can the backend run the extraction pipeline through provider context, optional local/noop media staging, prompt/schema packaging, fake provider response, validation, result persistence and lifecycle completion?

Default provider for this stage:

- fake/local extraction provider only.

This stage must not call real OpenRouter, perform real media upload, implement Web/API, or add UI behavior.

---

### 14.2 Why This Stage Exists

Previous stages create isolated pieces:

- provider input context;
- media staging boundary;
- extraction provider port;
- fake provider;
- prompt/schema package;
- provider response validation;
- result reconstruction.

This stage verifies that these pieces work together as one backend workflow.

The goal is to reach a deterministic backend-only flow before introducing real external provider behavior.

---

### 14.3 Entry Conditions

Before starting this stage, Codex must verify:

- completed baseline stages exist;
- Stage 7 provider input context exists and passes tests;
- Stage 8 media staging port/local backend exists and passes tests;
- Stage 9 extraction provider port/fake provider exists and passes tests;
- Stage 10 prompt/schema package exists and passes tests;
- Stage 11 validation/reconstruction exists and passes tests;
- `DocumentJobRepository` can persist extraction result payloads;
- lifecycle transitions can represent the intended extraction path.

If any required layer is missing, incomplete, or provider-specific too early, Codex must stop and report.

---

### 14.4 Expected Package Area

Preferred package areas:

- `src/document_digitization_ai/services/`
- `src/document_digitization_ai/application/`

Expected files may include:

- `src/document_digitization_ai/services/extraction_workflow.py`
- `src/document_digitization_ai/application/runtime.py` updates
- `tests/services/test_extraction_workflow.py`
- `tests/application/test_runtime_extraction.py`

Codex may choose a different file split if it preserves layer boundaries.

---

### 14.5 Allowed Changes

Codex may:

- create extraction workflow service;
- create typed workflow result object;
- create workflow-specific errors;
- integrate provider input context builder;
- integrate local/noop media staging;
- integrate prompt/schema package builder;
- integrate fake extraction provider;
- integrate provider output validation;
- persist extraction result payload through repository;
- update lifecycle status through repository only;
- extend application runtime with a local/fake extraction entrypoint;
- add repository methods only if required and persistence-focused;
- add deterministic integration tests;
- update source-of-truth docs only when needed for implementation continuity;
- create a private/untracked stage report.

Codex should avoid broad refactors of completed layers.

---

### 14.6 Forbidden Changes

Codex must not implement:

- real OpenRouter calls;
- HTTP/network transport;
- provider SDK integration;
- real media upload;
- ImgBB implementation;
- Web/API;
- preview/export/rendering;
- auth/users;
- batch/multi-page processing;
- deployment;
- background workers/queues.

Codex must not make pytest require:

- real secrets;
- real `.env`;
- external network;
- persistent local data directories.

Codex must not add new dependencies unless it stops and reports a clear rationale.

---

### 14.7 Required Workflow

The extraction workflow should start from an existing job that has completed local intake.

Expected initial job status:

- `IMAGE_DIAGNOSTICS_READY`

Expected high-level flow:

1. load or receive the target job;
2. verify job is ready for extraction;
3. build provider input context;
4. stage media through local/noop media staging if the workflow design requires staged reference;
5. build prompt/schema package;
6. build extraction provider request;
7. move status to `EXTRACTION_RUNNING`;
8. call fake extraction provider;
9. capture provider response;
10. move status to `EXTRACTION_SUCCEEDED`;
11. validate provider output;
12. reconstruct `ExtractionResult`;
13. persist extraction result payload;
14. move status to:
    - `VALIDATION_SUCCEEDED` for successful validation;
    - `VALIDATION_PARTIAL` for partial validation;
15. move status to `RESULT_READY` when result is ready for later presentation;
16. return typed workflow result.

If the existing lifecycle requires `MEDIA_STAGED`, the workflow should use it only when actual staging operation exists and is represented clearly.

Codex must not bypass lifecycle transition validation.

---

### 14.8 Lifecycle Requirements

All status transitions must go through existing repository/lifecycle logic.

Codex must not set job status directly from workflow code.

Expected transitions may include:

- `IMAGE_DIAGNOSTICS_READY` → `MEDIA_STAGED` if local/noop staging is represented as a lifecycle step;
- `IMAGE_DIAGNOSTICS_READY` or `MEDIA_STAGED` → `EXTRACTION_RUNNING`;
- `EXTRACTION_RUNNING` → `EXTRACTION_SUCCEEDED`;
- `EXTRACTION_SUCCEEDED` → `VALIDATION_SUCCEEDED`;
- `EXTRACTION_SUCCEEDED` → `VALIDATION_PARTIAL`;
- `VALIDATION_SUCCEEDED` → `RESULT_READY`;
- `VALIDATION_PARTIAL` → `RESULT_READY` only if existing lifecycle allows partial-ready result.

If existing lifecycle does not allow the required path, Codex must stop and report instead of weakening lifecycle validation silently.

---

### 14.9 Transaction Boundary Rule

Repository methods should continue to flush but not commit/rollback.

The extraction workflow service should not own global application transaction policy unless the current architecture already places that responsibility there.

Preferred design:

- service orchestrates workflow;
- repository persists and flushes;
- application runtime owns session open/commit/rollback.

Application runtime may expose a method similar to:

```md
run_fake_extraction(job_id)
````

or

```md
extract_document_with_fake_provider(job_id)
```

The name should clearly communicate that this is local/fake provider behavior.

---

### 14.10 Provider Rule

The default provider for this stage must be fake/deterministic.

Allowed:

* inject fake provider into workflow service;
* configure fake provider response in tests;
* use static provider-like payloads;
* return deterministic provider responses.

Forbidden:

* OpenRouter API calls;
* HTTP clients;
* provider SDK dependencies;
* real model names requiring real provider availability;
* tests that call real provider.

Real provider integration belongs to a later explicit gate.

---

### 14.11 Media Staging Rule

The workflow may use Stage 8 local/noop staging.

Allowed:

* local/noop staging of stored original image artifact;
* attaching staged reference to provider request/context if implemented;
* moving through `MEDIA_STAGED` only if lifecycle supports it and the staging operation is explicit.

Forbidden:

* real upload;
* public URL requirement;
* ImgBB;
* provider-specific media transformation;
* assuming staged media is externally reachable.

If provider request design requires public URL, Codex must stop and report.

---

### 14.12 Prompt/Schema Rule

The workflow should use Stage 10 prompt/schema package.

Allowed:

* build prompt/schema package from provider input context;
* pass prompt/schema package into provider request if provider port supports it;
* keep prompt/schema deterministic.

Forbidden:

* rewriting prompt/schema design broadly inside workflow stage;
* provider-specific prompt hacks;
* changing `ExtractionResult` contract without approval.

If prompt/schema package cannot be integrated cleanly with provider request, Codex must stop and report.

---

### 14.13 Validation Rule

The workflow must use Stage 11 validation/reconstruction.

Allowed:

* map validation outcome to lifecycle status;
* persist reconstructed `ExtractionResult`;
* preserve validation warnings/errors in workflow result if useful.

Forbidden:

* treating fake provider raw payload as final result;
* bypassing validation;
* silently converting failed validation to success;
* hiding partial validation status.

If validation outcome cannot map cleanly to lifecycle statuses, Codex must stop and report.

---

### 14.14 Persistence Rule

The workflow should persist:

* extraction result payload;
* validation status or equivalent already supported field;
* error message on failed workflow when transaction semantics allow;
* status transitions.

Codex may add narrow repository methods if needed, for example:

* attach provider response metadata;
* attach validation result summary;
* load extraction-ready job.

But repository must remain persistence-focused and must not own provider calls, validation, or workflow decisions.

---

### 14.15 Error Handling Rule

Failures must be explicit.

Expected behavior:

* provider context failure → typed workflow error;
* media staging failure → typed workflow error;
* fake provider failure → typed workflow error;
* validation failed/unusable payload → typed workflow error or failed validation outcome according to Stage 11 design;
* invalid lifecycle transition → explicit error;
* missing job → explicit error.

On failure after workflow starts, the service may attempt to mark the job as `FAILED` only if this is consistent with current transaction policy and lifecycle rules.

If application runtime rolls back the whole transaction on failure, Codex must document this behavior in the stage report.

---

### 14.16 Required Concepts

The stage should introduce typed concepts equivalent to the following.

Exact names may differ.

#### DocumentExtractionWorkflowService

Coordinates the backend extraction path.

Expected dependencies:

* repository;
* provider input context builder;
* media staging service;
* prompt/schema builder;
* extraction provider;
* provider output validator.

The service must not create DB sessions by itself.

#### DocumentExtractionWorkflowResult

Represents the result of workflow execution.

Should include at least:

* job id;
* final job status;
* validation outcome;
* extraction result when available;
* warnings;
* provider name/model metadata if available;
* staged media reference if used.

#### DocumentExtractionWorkflowError

Typed workflow error for orchestration failures.

---

### 14.17 Concrete Implementation Steps

Codex should proceed in this order:

1. Inspect lifecycle transitions.
2. Inspect repository extraction result persistence capability.
3. Inspect Stage 7–11 APIs.
4. Design minimal workflow service dependencies.
5. Design typed workflow result/error.
6. Implement workflow for fake provider success.
7. Implement validation outcome mapping.
8. Implement result persistence.
9. Add application runtime entrypoint for local/fake extraction.
10. Add deterministic service tests.
11. Add deterministic application runtime tests.
12. Add failure-path tests.
13. Verify no network/provider/media external calls exist.
14. Run validation commands.
15. Create private stage report using `report-writing`.
16. Stop at Gate 12 for Command Center review if this stage is run as part of a larger Codex task.

---

### 14.18 Test Requirements

Tests must be deterministic and local.

Required service-level test cases:

* workflow runs from `IMAGE_DIAGNOSTICS_READY` to `RESULT_READY` with fake provider;
* provider input context is built during workflow;
* local/noop staging is used if workflow design includes staging;
* prompt/schema package is used;
* fake provider response is validated;
* extraction result is persisted;
* final job can be reloaded with result payload;
* lifecycle transitions are enforced;
* invalid initial job status fails explicitly;
* provider failure fails explicitly;
* validation partial outcome maps to approved partial lifecycle status;
* unusable provider output fails explicitly;
* no real provider/network call happens.

Required application-level test cases:

* application runtime can initialize DB;
* application runtime can perform intake and fake extraction in local tmp environment;
* successful workflow commits persisted result;
* failed workflow rolls back or persists failed-job state according to documented transaction design;
* no real secrets are required.

Preferred test setup:

* use `tmp_path`;
* use tmp SQLite database;
* generate local image files with Pillow where intake is included;
* use fake provider/static payloads;
* do not use real `.env`;
* do not use network mocking unless necessary to prove no network path exists.

---

### 14.19 Validation Commands

Codex must run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
```

If any command cannot be run, Codex must report why and stop at Gate 12.

---

### 14.20 Stage Report

After completing this stage, Codex must create a private/untracked report using the existing `report-writing` skill.

Default report path:

```text
docs/codex/reports/stage_12_backend_extraction_workflow.md
```

The report should include:

* task boundary;
* files changed;
* workflow design;
* lifecycle transition path;
* transaction behavior;
* fake provider integration;
* media staging behavior;
* prompt/schema integration;
* validation/result persistence behavior;
* validation command results;
* what was intentionally not implemented;
* risks and open questions;
* whether Gate 12 is ready for Command Center review.

The report is not source of truth and must not be committed unless Command Center explicitly approves.

---

### 14.21 Gate 12 — Backend Extraction Workflow Review

Gate 12 is passed only if all conditions are true:

* backend extraction workflow service exists;
* local/fake provider flow reaches `RESULT_READY` or stops with documented lifecycle limitation;
* provider output is validated before result persistence;
* extraction result is persisted;
* lifecycle transitions are enforced through repository logic;
* application runtime entrypoint exists if included in stage scope;
* no real provider calls exist;
* no HTTP/network code exists;
* no real media upload exists;
* no Web/API code exists;
* no real secrets are required;
* deterministic tests cover success and failure paths;
* validation commands pass;
* private stage report exists.

If any condition fails, Codex must stop and report.

---

### 14.22 Stop Conditions

Codex must stop during this stage if:

* lifecycle transitions cannot represent the fake extraction flow cleanly;
* validation outcome cannot map to job statuses safely;
* repository cannot persist result without broad redesign;
* provider input context, media staging, prompt/schema, provider port or validation APIs conflict;
* workflow would require real provider behavior;
* workflow would require public URL/media upload;
* workflow would require Web/API behavior;
* tests would need network or real secrets;
* a new dependency appears necessary;
* stage scope starts drifting into real OpenRouter implementation.

When stopping, Codex must create a private report explaining the blocker and proposed options.

---

### 14.23 Completion Checklist

Before reporting Stage 12 complete, Codex must verify:

* [ ] extraction workflow service created;
* [ ] workflow result type created;
* [ ] workflow error type created;
* [ ] provider input context integrated;
* [ ] local/noop media staging integrated or intentionally not used with rationale;
* [ ] prompt/schema package integrated;
* [ ] fake provider integrated;
* [ ] provider output validation integrated;
* [ ] extraction result persistence implemented;
* [ ] lifecycle transition path tested;
* [ ] successful fake extraction test added;
* [ ] provider failure test added;
* [ ] validation failure/partial tests added;
* [ ] application runtime entrypoint added if in scope;
* [ ] no real provider call code added;
* [ ] no HTTP/network code added;
* [ ] no real media upload code added;
* [ ] no Web/API code added;
* [ ] deterministic tests added;
* [ ] `uv run ruff check .` passed;
* [ ] `uv run pyright` passed;
* [ ] `uv run pytest` passed;
* [ ] private stage report created;
* [ ] Gate 12 is ready for Command Center review.

---

## 15. Stage 13 — Real OpenRouter Provider Smoke Gate

Status: planned / gated  
Track: backend-only  
Depends on: Stage 12 — Backend Extraction Workflow Orchestration  
External provider calls: requires explicit Command Center approval  
External media upload: requires separate explicit Command Center approval if needed  
Web/UI: forbidden  
Primary risk: real provider behavior forcing premature architecture shortcuts

---

### 15.1 Objective

Implement and/or manually smoke-test a real OpenRouter/OpenAI-compatible extraction provider path only after the deterministic fake backend extraction workflow is stable.

This stage must answer one question:

> Can the existing backend extraction boundaries support a real vision-capable provider without breaking architecture, validation, lifecycle, secrets, tests, or media boundaries?

This stage is not automatically executable.

Codex may start this stage only when the current task explicitly approves real provider integration or real provider smoke.

---

### 15.2 Why This Stage Exists

Stages 7–12 should already prove that the backend pipeline works with deterministic local/fake components.

Only after that is stable should the project test real provider behavior.

Real provider integration may reveal:

- request shape mismatch;
- prompt/schema incompatibility;
- structured output limitations;
- media input requirements;
- public URL requirement;
- model-specific behavior;
- validation gaps;
- timeout/retry concerns;
- raw response shape differences.

These findings should be handled through explicit gates, not hidden inside workflow code.

---

### 15.3 Entry Conditions

Before starting this stage, Codex must verify:

- Stage 7 provider input context exists and passes tests;
- Stage 8 media staging boundary exists and passes tests;
- Stage 9 extraction provider port exists and passes tests;
- Stage 10 prompt/schema package exists and passes tests;
- Stage 11 validation/reconstruction exists and passes tests;
- Stage 12 fake backend extraction workflow exists and passes tests;
- application runtime can run local intake and fake extraction;
- settings layer supports OpenRouter provider values;
- tests do not require real secrets;
- Command Center explicitly approved this stage.

If explicit approval is missing, Codex must stop.

---

### 15.4 Expected Package Area

Preferred package area:

- `src/document_digitization_ai/extraction/`

Expected files may include:

- `src/document_digitization_ai/extraction/openrouter.py`
- `src/document_digitization_ai/extraction/transport.py` if a small transport abstraction is useful
- `tests/extraction/test_openrouter_provider.py`
- `tests/extraction/test_openrouter_request_mapping.py`

Optional manual smoke area, only if approved:

- `scripts/`
- or `docs/codex/manual_smoke/`

Codex may choose different names if they preserve the same boundaries.

---

### 15.5 Allowed Changes

Codex may:

- implement OpenRouter-compatible provider adapter behind the existing provider port;
- add provider-specific request mapping;
- add provider-specific response parsing into existing provider response object;
- add typed provider errors for transport/API failures;
- add no-secret import behavior;
- add deterministic unit tests with mocked/fake transport;
- add static fixture response tests;
- add optional manual smoke helper only if explicitly approved;
- update source-of-truth docs only when needed for implementation continuity;
- create a private/untracked stage report.

Codex may add a lightweight HTTP dependency only if explicitly approved by Command Center or already present in the project.

If no HTTP dependency is approved, Codex must either use existing capabilities or stop and report options.

---

### 15.6 Forbidden Changes

Codex must not:

- make pytest call real OpenRouter;
- require real API keys for import or unit tests;
- commit secrets;
- print secrets in logs/reports;
- implement hidden model fallback;
- silently change provider/model when a request fails;
- bypass validation/reconstruction;
- return raw provider output as final result;
- make provider adapter own DB/session/lifecycle;
- implement Web/API;
- implement real media upload unless separately approved;
- implement ImgBB unless separately approved;
- introduce broad retry/background worker infrastructure;
- add deployment assumptions.

---

### 15.7 Required Concepts

The stage should introduce typed concepts equivalent to the following.

Exact names may differ.

#### OpenRouterExtractionProvider

Provider adapter implementing the existing extraction provider port.

Expected behavior:

- accepts existing provider request type;
- builds OpenRouter-compatible request payload;
- sends request only through explicit runtime/manual path;
- parses provider response into existing `ExtractionProviderResponse`;
- raises typed provider errors on failure;
- does not validate final extraction result itself;
- does not persist anything;
- does not update job lifecycle.

#### Provider Transport Boundary

If transport abstraction is useful, it should be narrow.

Allowed:

- small async transport protocol;
- fake/mock transport for tests;
- real transport implementation for manual/runtime use only.

Forbidden:

- broad HTTP framework;
- hidden global client;
- import-time network setup;
- test-time network calls.

#### OpenRouter Provider Error Types

Errors should distinguish where possible:

- missing API key for real provider action;
- request construction error;
- transport/network error;
- provider HTTP/API error;
- response parsing error;
- unsupported provider response shape.

---

### 15.8 Settings and Secrets Rule

Real provider actions may require:

- OpenRouter API key;
- model name;
- base URL;
- optional app title / referer metadata.

Rules:

- imports must not require secrets;
- unit tests must not require secrets;
- fake provider path must not require secrets;
- real provider adapter may call explicit helper methods that fail if key/model is missing;
- secret values must never appear in repr/logs/reports;
- `.env.example` may contain placeholders only.

If model name is placeholder, real provider action must fail explicitly before network call.

If API key is missing/placeholder, real provider action must fail explicitly before network call.

---

### 15.9 Media Requirement Rule

Codex must inspect whether the real provider request path can use the current media representation.

Allowed possibilities:

- provider accepts image as base64/data URL;
- provider accepts public URL;
- provider accepts provider-hosted file reference;
- provider accepts another supported image representation.

Codex must not assume public URL.

If real provider path requires public URL and Stage 8 only has local/noop staging, Codex must stop and report.

Codex must not implement ImgBB or public upload in this stage unless separately approved.

---

### 15.10 Prompt/Schema Rule

The real provider adapter must use the Stage 10 prompt/schema package.

Allowed:

- map prompt package into provider request messages;
- map schema package into provider request payload if supported;
- include provider schema mode behavior from settings.

Forbidden:

- rewriting prompt/schema package inside provider adapter;
- hardcoding a new schema unrelated to Stage 10;
- silently dropping schema requirements;
- weakening output requirements without reporting.

If provider structured output behavior conflicts with Stage 10 schema package, Codex must stop and report options.

---

### 15.11 Response Handling Rule

The provider adapter must parse real provider response into the Stage 9 provider response object.

It must not:

- reconstruct `ExtractionResult`;
- validate final result;
- persist result;
- update job status;
- treat response as trusted final data.

Stage 11 validation remains the only layer that reconstructs internal extraction result.

---

### 15.12 Automated Test Rule

Automated tests must be deterministic.

Required automated test behavior:

- no real network calls;
- no real API keys;
- mocked/fake transport;
- static response fixtures;
- request payload mapping checks;
- response parsing checks;
- error mapping checks;
- no secret leakage checks where practical.

Automated tests must pass without `.env`.

---

### 15.13 Manual Smoke Rule

Manual smoke is optional and must be explicitly approved.

If manual smoke is approved, it must be:

- opt-in;
- clearly separated from pytest;
- documented as local/manual only;
- safe with missing secrets;
- explicit about environment variables required;
- explicit about expected cost/risk;
- explicit about output artifacts/logs;
- careful not to commit raw sensitive outputs.

Manual smoke may produce a private/untracked report.

Manual smoke must not become required for CI/unit validation.

---

### 15.14 Concrete Implementation Steps

Codex should proceed in this order:

1. Confirm Command Center approval for real provider stage.
2. Inspect existing provider port/request/response types.
3. Inspect prompt/schema package.
4. Inspect validation layer.
5. Inspect settings secret helper behavior.
6. Decide whether a small transport abstraction is needed.
7. Implement OpenRouter provider adapter behind existing provider port.
8. Implement request mapping from existing prompt/schema/context objects.
9. Implement response parsing into existing provider response type.
10. Implement typed provider error mapping.
11. Add deterministic tests with fake/mocked transport.
12. Add no-secret import tests.
13. Add no-network pytest protection if practical.
14. Run validation commands.
15. Create private stage report using `report-writing`.
16. Stop at Gate 13 for Command Center review.
17. Perform manual smoke only if separately approved.

---

### 15.15 Test Requirements

Required test cases:

- OpenRouter provider can be instantiated/imported without real secrets when no real call is made;
- real-call execution path fails before network when API key is missing/placeholder;
- real-call execution path fails before network when model is missing/placeholder;
- request mapping includes prompt package;
- request mapping includes schema package where applicable;
- request mapping includes image/media reference in supported form;
- request mapping does not include secrets in payload/loggable repr;
- mocked successful response parses into provider response object;
- mocked provider error maps to typed provider error;
- malformed provider response fails explicitly;
- provider adapter does not persist data;
- provider adapter does not update job lifecycle;
- pytest does not perform network calls.

Preferred test setup:

- fake transport object;
- static response payload fixtures;
- no real `.env`;
- no real local persistent data directories.

---

### 15.16 Validation Commands

Codex must run:

```bash
uv run ruff check .
uv run pyright
uv run pytest
````

If any command cannot be run, Codex must report why and stop at Gate 13.

---

### 15.17 Stage Report

After completing this stage, Codex must create a private/untracked report using the existing `report-writing` skill.

Default report path:

```text
docs/codex/reports/stage_13_real_openrouter_provider.md
```

The report should include:

* task boundary;
* approval status for real provider work;
* files changed;
* provider adapter design;
* transport design;
* request mapping behavior;
* media input assumption;
* prompt/schema integration;
* response parsing behavior;
* automated validation command results;
* whether manual smoke was run;
* what was intentionally not implemented;
* risks and open questions;
* whether Gate 13 is ready for Command Center review.

The report is not source of truth and must not be committed unless Command Center explicitly approves.

---

### 15.18 Gate 13 — Real Provider Review

Gate 13 is passed only if all conditions are true:

* Command Center explicitly approved this stage;
* OpenRouter-compatible adapter implements existing provider port;
* adapter does not own DB/session/lifecycle;
* adapter does not bypass validation layer;
* adapter imports without real secrets;
* automated tests do not call network;
* missing secret/model failures happen before network;
* request mapping is tested;
* response parsing is tested;
* provider errors are explicit;
* no real media upload exists unless separately approved;
* no Web/API code exists;
* validation commands pass;
* private stage report exists.

Manual smoke success is not required unless Command Center explicitly made it part of this gate.

---

### 15.19 Stop Conditions

Codex must stop during this stage if:

* Command Center approval for real provider work is absent;
* provider request requires public URL but no approved staging backend exists;
* provider requires unsupported image representation;
* provider schema mode conflicts with prompt/schema package;
* response shape cannot be parsed into existing provider response object;
* validation layer cannot consume provider response safely;
* implementation would require Web/API behavior;
* implementation would require real media upload without approval;
* automated tests would need real network or real secrets;
* a new dependency appears necessary without approval;
* real provider behavior forces architecture decision outside current scope.

When stopping, Codex must create a private report explaining the blocker and proposed options.

---

### 15.20 Completion Checklist

Before reporting Stage 13 complete, Codex must verify:

* [ ] explicit Command Center approval exists;
* [ ] OpenRouter-compatible provider adapter created;
* [ ] adapter implements existing provider port;
* [ ] request mapping implemented;
* [ ] response parsing implemented;
* [ ] provider errors implemented;
* [ ] missing API key fails before network;
* [ ] missing model fails before network;
* [ ] no pytest network calls exist;
* [ ] no pytest real secrets required;
* [ ] provider adapter does not persist data;
* [ ] provider adapter does not update lifecycle;
* [ ] provider adapter does not validate final `ExtractionResult`;
* [ ] media requirement is documented;
* [ ] no Web/API code added;
* [ ] deterministic tests added;
* [ ] `uv run ruff check .` passed;
* [ ] `uv run pyright` passed;
* [ ] `uv run pytest` passed;
* [ ] private stage report created;
* [ ] Gate 13 is ready for Command Center review.

