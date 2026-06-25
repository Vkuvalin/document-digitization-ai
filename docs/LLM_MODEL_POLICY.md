# LLM Model Policy

## 1. Purpose

This document governs the LLM/provider layer for the private/local MVP.

Its goals are:

- protect correctness by keeping provider output behind backend validation;
- protect privacy by making external provider/media use explicit;
- preserve reproducibility for local development and tests;
- keep prompt, schema, model and media-staging changes reviewable;
- prevent provider/debug data from becoming normal user-facing output.

This is not a prompt reference, API reference, marketing document or workflow
replacement.

## 2. Provider Modes

Current provider modes are defined by `ExtractionProviderName`:

- `fake`: deterministic local provider for default local runs and automated tests;
- `openrouter`: real provider adapter using the OpenRouter-compatible OpenAI SDK path.

Safe default behavior:

- `.env.example` sets `EXTRACTION_PROVIDER=fake`;
- `fake` does not require OpenRouter or ImgBB secrets;
- default automated tests should not call real external providers;
- failed real-provider setup must fail explicitly.

Provider construction is owned by `src/document_digitization_ai/extraction/factory.py`.
Unsupported provider names are rejected. There must be no hidden fallback from a
failed `openrouter` path to `fake`.

## 3. Configuration and Secrets

Configuration starts from `.env.example`; real values belong in local `.env`.

Provider settings:

- `EXTRACTION_PROVIDER`
- `OPENROUTER_API_KEY`
- `OPENROUTER_BASE_URL`
- `OPENROUTER_MODEL`
- `OPENROUTER_APP_TITLE`
- `OPENROUTER_HTTP_REFERER`
- `LLM_TEMPERATURE`
- `LLM_TIMEOUT_SECONDS`
- `LLM_MAX_RETRIES`
- `LLM_STRUCTURED_OUTPUTS_ENABLED`
- `LLM_STRUCTURED_OUTPUTS_REQUIRE_PARAMETERS`
- `LLM_PROVIDER_SCHEMA_MODE`

Media staging settings:

- `MEDIA_STAGING_BACKEND`
- `IMGBB_API_KEY`
- `MEDIA_STAGING_TTL_SECONDS`
- `MEDIA_STAGING_EXPIRY_SAFETY_SECONDS`
- `MEDIA_STAGING_VERIFY_DOWNLOAD`
- `MEDIA_STAGING_STRICT_VERIFY`

Upload/storage settings relevant to provider flow:

- `IMAGE_DIAGNOSTICS_MAX_FILE_SIZE_BYTES`
- `STORAGE_UPLOADS_DIR`
- `STORAGE_RESULTS_DIR`
- `ARTIFACT_RETENTION_DAYS`

Rules:

- keep real secrets only in `.env`;
- never commit `.env`, API keys, tokens or local credentials;
- never copy secret values into reports, docs, tests, screenshots or fixtures;
- placeholder values such as `change_me` may load for safe default local mode,
  but real provider calls require non-placeholder OpenRouter and ImgBB settings;
- update `.env.example` when adding or renaming provider/media config variables.

## 4. Media Staging Boundary

Current media staging modes are defined by `MediaStagingBackend`:

- `none`: local/noop staging; returns a local file reference and performs no
  external upload;
- `imgbb`: uploads image bytes to ImgBB and returns a provider-facing public URL.

OpenRouter visual extraction requires `PUBLIC_URL` staged media. A local file
reference from `MEDIA_STAGING_BACKEND=none` is not valid for OpenRouter calls.

When `MEDIA_STAGING_BACKEND=imgbb` is used:

- `IMGBB_API_KEY` is required;
- uploaded document image bytes are sent to ImgBB;
- the resulting public image URL can be sent to OpenRouter;
- private cleanup/delete URLs must not be exposed as user-facing output;
- staging URLs must not be copied into Markdown/PDF exports, tracked project docs or normal UI output.

Web UI must not expose direct provider/media staging internals. Generated or
staged artifacts must not be committed.

## 5. Prompt and Schema Contract

Prompt and schema builders are part of the provider contract:

- `src/document_digitization_ai/extraction/prompts.py`
- `src/document_digitization_ai/extraction/schema.py`
- `src/document_digitization_ai/extraction/openrouter.py`

Current contract facts:

- prompt package version is `extraction_prompt_v0`;
- target result schema is `extraction_result_v0`;
- schema modes are `compact` and `full`;
- structured output is expected for OpenRouter;
- OpenRouter response format uses JSON schema with `strict: True`;
- prompt and schema packages are deterministic and should not require secrets.

Prompt/schema policy:

- keep prompts narrow and aligned with the result schema;
- do not casually broaden extraction scope;
- preserve document-mode guidance as guidance, not truth;
- preserve image diagnostics as quality guidance, not extracted content;
- preserve field/table classification policy;
- update targeted tests when prompt, schema or model behavior changes.

## 6. Validation and Reconstruction

Provider output is untrusted until backend validation succeeds.

Validation and reconstruction live in:

- `src/document_digitization_ai/extraction/validation.py`;
- `src/document_digitization_ai/services/extraction_workflow.py`;
- `src/document_digitization_ai/export/reconstruction.py`.

Rules:

- parse provider response through provider boundary types;
- validate and normalize provider payload before treating it as accepted result;
- failed validation must be explicit;
- partial/malformed optional data may produce warnings;
- substantively empty provider output must fail validation;
- user-facing exports must be built from accepted/cleaned result, not raw
  provider data.

Raw and sanitized provider artifacts may exist for internal/debug workflows, but
they are not normal user-facing output.

## 7. Model Variability

Real model extraction is not deterministic product truth.

Expected variability:

- document classification may vary between runs or models;
- values may appear as standalone fields or as table rows depending on provider
  interpretation;
- handwriting, noisy scans, low contrast and small text may remain uncertain;
- confidence and warnings are guidance, not proof.

The project uses table-derived review values to reduce user-facing inconsistency
when important values are represented inside tables. This must not be removed
casually when changing result review, field/table extraction or Web UI rendering.

Do not document extraction as guaranteed deterministic except for the local
`fake` provider path.

## 8. User-Facing Output Boundary

User-facing surfaces:

- Web UI under `/app`;
- JSON result API after backend validation;
- Markdown export;
- PDF export;
- original upload preview/download through backend preview endpoint.

Internal/debug-only surfaces:

- raw provider response artifacts;
- sanitized provider response artifacts;
- provider request/debug payloads;
- prompt packages and schema packages;
- extraction attempts and internal job/attempt metadata;
- external media staging details and cleanup URLs.

Default Markdown/PDF exports must not include:

- `Extraction Metadata`;
- provider/model/job/attempt debug metadata;
- raw or sanitized provider payloads;
- secrets, authorization headers or API key names with values;
- local filesystem paths;
- external media staging URLs.

## 9. External Smoke Policy

Real provider smoke is explicit and manual only.

Current script:

```powershell
uv run python scripts/manual_provider_smoke.py --image path\to\sample.jpg
```

Required gate and preconditions:

- `RUN_REAL_PROVIDER_SMOKE=1`;
- `EXTRACTION_PROVIDER=openrouter`;
- `MEDIA_STAGING_BACKEND=imgbb`;
- `LLM_STRUCTURED_OUTPUTS_ENABLED=true`;
- real `OPENROUTER_API_KEY`;
- non-placeholder `OPENROUTER_MODEL`;
- real `IMGBB_API_KEY`;
- local image path that points to an existing file.

Rules:

- do not run paid/network provider calls casually;
- do not include real-provider smoke in default automated validation;
- fake-provider tests are necessary but not a substitute for explicit real
  provider smoke when changing provider/media behavior;
- smoke output must remain redacted when printed or summarized.

## 10. Sensitive Data Rules

Uploaded documents may contain sensitive information.

External exposure must be intentional:

- ImgBB receives uploaded image bytes when `MEDIA_STAGING_BACKEND=imgbb`;
- OpenRouter receives the public image URL plus prompt/schema instructions and
  provider context needed for extraction;
- extracted text and structured payloads may contain document content.

Rules:

- do not log full secrets;
- do not paste raw provider payloads into docs or reports;
- do not expose raw/sanitized artifacts in UI;
- do not share external media/provider URLs as user-facing outputs;
- do not expose local absolute paths in API responses, exports or UI;
- redact secrets, URLs and raw document text in manual smoke summaries.

## 11. Change Control

Extra care is required for changes to:

- provider adapter construction or error mapping;
- model name, provider selection or OpenRouter settings;
- prompt text or prompt package metadata;
- schema modes, required sections or JSON schema generation;
- validation/reconstruction behavior;
- media staging backend, TTL or public URL handling;
- export boundary and user-facing output sections;
- table-derived values and result review payloads.

For these changes:

- add or update targeted tests;
- run relevant validation commands;
- run manual browser/export checks when UI or export surfaces change;
- run manual real-provider smoke only when explicitly intended and safe;
- update `README.md`, `docs/PROJECT_CONTEXT.md`,
  `docs/DEVELOPMENT_CHECKLIST.md`, this policy or `docs/PROJECT_MAP.md` when
  behavior or boundaries change.

## 12. Known Limitations

- Extraction quality depends on source image quality.
- Handwriting and noisy scans may remain uncertain.
- Provider classification and field/table grouping can vary.
- PDF export exists, but PDF extraction input is not guaranteed.
- There is no production privacy/security hardening.
- There is no auth, account model or multi-user isolation.
- There is no automatic provider quality monitoring.
- There is no automatic scheduled provider smoke.
- Default automated tests rely on fakes, injected transports and env gates
  rather than a global no-network blocker.
