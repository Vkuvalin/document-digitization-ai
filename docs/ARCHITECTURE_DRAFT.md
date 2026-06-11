# ARCHITECTURE_DRAFT.md

## 1. Статус документа

Это рабочий архитектурный draft для `document-digitization-ai`.

Документ фиксирует утверждённые v0-решения для первого MVP и задаёт рамку для следующих implementation-задач. Это ещё не `PROJECT_MAP.md`: фактическую карту runtime-слоёв, entrypoints и модулей нужно создать позже, когда появится реальная структура кода.

Документ не утверждает:

- production architecture;
- финальный Web stack;
- полный API shape;
- production storage;
- финальную provider/model policy;
- production deployment;
- final export/rendering architecture.

---

## 2. Архитектурная цель

Проект должен быть не OCR-wrapper, а backend-controlled document understanding pipeline.

Цель pipeline:

```text
image input
→ deterministic diagnostics
→ provider-compatible input
→ structured text/structure extraction
→ backend validation
→ persisted result
→ reviewable Web output
```

Backend должен владеть workflow, состоянием обработки, validation, persistence, provider orchestration и result lifecycle.

Web UI и extraction provider не управляют workflow state.

---

## 3. Первый happy path v0

Первый demonstrable path:

```text
Пользователь открывает Web UI
→ загружает одно изображение документа
→ выбирает document mode hint или оставляет auto
→ backend создаёт processing job
→ backend проверяет/принимает image
→ backend собирает ImageDiagnostics
→ backend stages image, если provider требует provider-compatible reference
→ backend формирует ProviderInputContext
→ extraction provider возвращает structured output
→ backend валидирует output
→ backend сохраняет ExtractionResult
→ Web UI показывает source image, diagnostics, raw text, fields, tables, blocks/preview, warnings и JSON
```

Первый демонстрационный sample:

```text
одно фото смешанного рукописно/печатного бланка, формы или документа
```

Это не ограничивает архитектуру только формами. Форма/бланк — первый сильный sample, потому что он проверяет handwriting, fields, tables, label/value links и warnings.

---

## 4. Backend-controlled job lifecycle v0

Минимальный lifecycle для первого MVP:

```text
CREATED
→ IMAGE_UPLOADED
→ IMAGE_DIAGNOSTICS_READY
→ MEDIA_STAGED
→ EXTRACTION_RUNNING
→ EXTRACTION_SUCCEEDED
→ VALIDATION_SUCCEEDED / VALIDATION_PARTIAL
→ RESULT_READY
```

Terminal states:

```text
FAILED
CANCELLED
```

### State meanings

`CREATED` — job создан.

`IMAGE_UPLOADED` — файл принят backend-ом как открываемое изображение.

`IMAGE_DIAGNOSTICS_READY` — backend собрал deterministic diagnostics.

`MEDIA_STAGED` — изображение подготовлено для provider: staged URL, base64, provider upload reference или другой provider-compatible input.

`EXTRACTION_RUNNING` — backend вызвал extraction provider adapter.

`EXTRACTION_SUCCEEDED` — provider вернул structured output, но результат ещё не считается доверенным.

`VALIDATION_SUCCEEDED` — backend validation прошла без blocking errors.

`VALIDATION_PARTIAL` — результат частично пригоден: есть usable text/fields/tables/blocks, но есть warnings, missing/unmatched/uncertain values или partial extraction.

`RESULT_READY` — результат можно показывать в Web UI.

`FAILED` — продолжить невозможно: invalid/unreadable image, unrecoverable provider error, полностью невалидный output без usable partial result.

`CANCELLED` — job остановлен пользователем или системой.

### Quality policy

Низкое качество изображения не должно автоматически переводить job в `FAILED`.

```text
invalid/unreadable image → hard reject / FAILED
blur, low contrast, skew, low-ish resolution → warnings, usually continue
```

Это важно для архивных и исторических документов, где лучшего изображения может не быть.

---

## 5. Branch-aware foundation

v0 не должен создавать отдельные pipelines под каждый будущий режим.

Нужна общая extraction/reconstruction base:

```text
ImageDiagnostics
+ RawText
+ Fields
+ Tables
+ Blocks / reading order
+ Warnings / uncertainty
```

Поверх этой базы позже строятся result modes:

- plain text mode;
- structure mode;
- form extraction mode;
- table mode;
- template-guided mode;
- document reconstruction mode.

Document mode hint влияет на context/routing, но не должен превращаться в отдельную архитектуру на каждый тип.

---

## 6. Document mode hints

Начальные user hints:

- `auto`;
- `form`;
- `table`;
- `free_handwritten_text`;
- `mixed_document`;
- `plain_text`.

User hint — подсказка, а не истина.

Provider/analyzer result должен вернуть:

- detected document type;
- confidence;
- possible mode mismatch warning.

Пример:

```text
user_mode_hint = table
detected_type = form
warning = mode_mismatch
```

Backend не должен слепо доверять ни user hint, ни provider classification. Оба значения становятся частью structured result и validation/review context.

---

## 7. ImageDiagnostics

`ImageDiagnostics` — backend-owned diagnostics, collected before provider call.

Это не LLM output.

### Draft shape

```text
ImageDiagnostics
├── file
├── image
├── quality
├── warnings[]
└── metadata
```

### `file`

- `mime_type`;
- `file_size_bytes`;
- `file_extension`;
- `sha256?`.

### `image`

- `width`;
- `height`;
- `aspect_ratio`;
- `orientation`;
- `exif_orientation?`;
- `color_mode?`;
- `format?`.

### `quality`

Initial values may be approximate:

- `blur_score?`;
- `sharpness_score?`;
- `brightness?`;
- `contrast?`;
- `is_low_resolution?`;
- `is_probably_blurry?`;
- `is_low_contrast?`.

Quality metrics are heuristic diagnostics, not final truth.

### `warnings[]`

Initial warning codes:

- `invalid_image`;
- `unsupported_format`;
- `too_large`;
- `too_small`;
- `low_resolution`;
- `blurred_image`;
- `low_contrast`;
- `too_dark`;
- `too_bright`;
- `possible_rotation`;
- `possible_skew`;
- `exif_orientation_present`.

### Implementation baseline

For v0, start simple:

- Pillow for image open/format/dimensions/EXIF/color mode;
- Pydantic models for diagnostics contracts.

Do not add heavier image-processing dependencies until a scoped architecture decision justifies them.

Future options may include OpenCV, scikit-image, OCR/layout tools or custom layout pre-analysis.

---

## 8. ProviderInputContext

`ProviderInputContext` is the bridge between backend and extraction provider.

It answers:

```text
What should the provider know besides the image itself?
```

### Draft shape

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

### `job`

Backend/logging context:

- `job_id`;
- `created_at`;
- `processing_stage`.

Not every field must be sent to the provider, but the context should be traceable.

### `user_request`

- `user_mode_hint`.

Initial values:

- `auto`;
- `form`;
- `table`;
- `free_handwritten_text`;
- `mixed_document`;
- `plain_text`.

### `image`

- `image_id`;
- `mime_type`;
- `width`;
- `height`;
- `file_size_bytes`;
- `provider_image_reference`.

`provider_image_reference` may be a staged URL, base64 input, provider file ID or future input representation.

### `image_diagnostics`

Send a compact summary to the model/provider:

```text
Image diagnostics:
- MIME: image/jpeg
- Size: 1600x2200
- Orientation: portrait
- File size: 845 KB
- Backend warnings: low_contrast, possible_skew
- Hard rejection: no
```

Do not overload provider context with irrelevant raw metadata.

### `extraction_goal`

v0 goal:

```text
extract_text_and_structure
```

Meaning:

- recognize handwritten and printed text;
- infer document type;
- extract fields and values;
- extract table-like data where visible;
- extract text blocks and reading order where useful;
- return uncertainty and warnings explicitly.

Future goals may include:

- `plain_text_only`;
- `table_extraction`;
- `form_extraction`;
- `template_guided_mapping`;
- `document_reconstruction`.

### `expected_result`

Provider should be instructed to return structured output matching the expected schema/contract:

- document;
- raw_text;
- fields[];
- tables[];
- blocks[];
- warnings[];
- metadata.

Schema defines form. Prompt/context must define semantics. Do not rely only on schema field descriptions reaching the provider.

### `constraints`

Initial constraints:

- do not invent unreadable text;
- mark uncertain values explicitly;
- preserve table-like structure where visible;
- if user mode hint seems wrong, return mode mismatch warning;
- if text is unreadable, return partial result and warnings;
- do not silently clean up uncertain handwriting;
- return valid structured output.

---

## 9. Extraction provider abstraction

Initial provider baseline:

```text
OpenRouter + OpenAI vision-capable model configured through environment
```

This is a pragmatic MVP baseline, not provider lock-in.

Provider-specific code must stay behind adapter boundaries. Backend workflow should talk to internal contracts, not raw provider response shapes.

Future provider options must remain possible:

- specialized OCR engines;
- cloud Document AI services;
- other multimodal providers;
- hybrid OCR + LLM flows.

---

## 10. Media staging

Media staging must be isolated behind a service/adapter boundary.

For image-first MVP, ImgBB may be used as the first temporary image staging backend if public image URLs are needed.

ImgBB must not leak into:

- business logic;
- workflow/domain contracts;
- Web UI;
- extraction result schema.

Possible future staging representations:

- local file;
- base64 payload;
- provider upload/file ID;
- temporary public URL;
- S3/R2-like storage;
- another temporary hosting provider.

The staging layer prepares provider-compatible input; it does not own document extraction logic.

---

## 11. ExtractionResult v0

`ExtractionResult` is the central validated output of the pipeline.

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

This is a draft contract for planning and first implementation. It is not a final universal document schema.

### `document`

- `user_mode_hint`;
- `detected_type`;
- `detected_type_confidence?`;
- `language?`;
- `summary?`.

Initial `detected_type` values:

- `unknown`;
- `plain_text`;
- `form`;
- `table`;
- `mixed_document`;
- `free_handwritten_text`;
- `label_or_plate`;
- `other`.

### `raw_text`

- `text`;
- `confidence?`;
- `warnings[]`.

### `fields[]`

- `label`;
- `value`;
- `confidence?`;
- `source?`;
- `warnings[]`.

Initial `source` values:

- `detected`;
- `inferred`;
- `template`;
- `user_hint`;
- `unknown`.

### `tables[]`

- `title?`;
- `columns[]`;
- `rows[]`;
- `confidence?`;
- `warnings[]`.

`rows[]` v0:

- `cells[]`;
- `confidence?`;
- `warnings[]`.

v0 should keep table rows simple enough for DataFrame-like Web preview. Cell-level geometry, row/col spans and coordinates are deferred.

### `blocks[]`

- `type`;
- `level?`;
- `text`;
- `order`;
- `confidence?`;
- `warnings[]`.

Initial block types:

- `heading`;
- `paragraph`;
- `list`;
- `table`;
- `field_group`;
- `signature`;
- `unknown`.

### `warnings[]`

- `code`;
- `message`;
- `severity`;
- `target?`.

Initial severity values:

- `info`;
- `warning`;
- `error`.

Initial warning codes:

- `low_quality_image`;
- `low_contrast`;
- `blurred_image`;
- `possible_rotation`;
- `possible_skew`;
- `unreadable_text`;
- `ambiguous_field`;
- `ambiguous_table`;
- `mode_mismatch`;
- `partial_extraction`;
- `provider_error`;
- `validation_error`;
- `missing_expected_field`;
- `unmatched_text`.

### `metadata`

- `provider?`;
- `model?`;
- `schema_version`;
- `created_at?`.

Future fields may include latency, token usage or provider request IDs, but they are not required for v0.

---

## 12. Result views

One `ExtractionResult` should support multiple views:

- source image;
- diagnostics;
- raw text;
- fields;
- tables / DataFrame-like table preview;
- blocks / structured preview;
- warnings;
- JSON.

Web UI should show table-like results as readable grids where possible, not only as raw JSON.

Result views are presentation over validated result data. They are not separate extraction pipelines.

---

## 13. Validation boundary

Provider output is untrusted until backend validation.

Backend validation should check:

- response is valid structured data;
- required top-level result sections exist;
- enum values are allowed;
- confidence values are in allowed range if present;
- table rows/cells are structurally usable;
- warning severities/codes are valid;
- mode mismatch is explicit when relevant;
- partial/unreadable/uncertain sections are represented as warnings, not hidden.

Silent fallback is forbidden.

If result is incomplete but usable, prefer `VALIDATION_PARTIAL` with explicit warnings over hard failure.

---

## 14. SQLite and filesystem baseline

SQLite is acceptable as local MVP storage.

Filesystem may store original and derived artifacts.

Potential SQLite data:

- jobs;
- job status;
- uploaded file metadata;
- image diagnostics;
- staged media metadata;
- provider run metadata;
- extraction result;
- validation status;
- preview/export metadata.

This is a pragmatic local MVP decision, not a production storage commitment.

DB/repository/session patterns must be designed in a separate approved implementation step.

---

## 15. Preview and export lifecycle

Reliable core output:

```text
validated structured data
```

Initial preview:

- raw text;
- fields;
- table grids;
- block/reading-order preview;
- warnings;
- JSON.

Future exports:

- DOCX;
- XLSX;
- PDF;
- CSV;
- production-grade reconstruction;
- pixel-perfect visual reconstruction.

Rendering/export logic must not depend directly on LLM calls. Provider output becomes validated result; preview/export renders from validated result.

---

## 16. Template-guided extensibility

Template-guided extraction remains an architectural direction, not v0 implementation requirement.

Levels:

```text
Level 1 — no reference:
  extraction from filled document image

Level 3 — manual structured template schema:
  backend receives known fields/tables/schema and maps extracted values

Level 2 — reference template image analysis:
  provider analyzes empty/reference template image and generates a template schema
```

Preferred path:

- v0: Level 1;
- later: optional Level 3;
- later: Level 2.

`ProviderInputContext` should leave room for optional future template context.

Template-guided extraction should remain schema-driven and backend-validated, not prompt-only reconstruction.

---

## 17. What not to implement in v0

Do not require in v0:

- PDF/DOCX/XLSX input;
- batch processing;
- final Web stack;
- production auth/deployment;
- cell-level coordinates;
- page model;
- layout tree;
- automatic template learning;
- reference image analysis;
- DOCX/XLSX/PDF export;
- visual document editor;
- pixel-perfect reconstruction.
