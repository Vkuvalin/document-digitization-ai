# PROJECT_CONTEXT.md

## Назначение проекта

`document-digitization-ai` — backend-first MVP для оцифровки документов по изображениям.

Цель проекта шире обычного OCR: система должна не только распознавать печатный и рукописный текст, но и восстанавливать полезное цифровое представление документа:

- связывать текст с полями, строками, колонками, ячейками, блоками и секциями;
- явно показывать неопределённость, пропуски, низкое качество изображения и неоднозначные сопоставления;
- хранить результат как backend-validated structured data;
- показывать результат в Web UI как reviewable views: текст, поля, таблицы, warnings, preview и JSON.

Проект не должен проектироваться как thin OCR wrapper. Базовая ценность MVP — backend-controlled document AI pipeline: ingestion, image diagnostics, media staging, provider orchestration, structured extraction, validation, storage, preview/review и future extensibility.

## Текущий статус репозитория

Проект находится на стадии раннего backend foundation.

Уже есть:

- публичный репозиторий `document-digitization-ai`;
- Python/uv baseline;
- Python `3.14`;
- `pyproject.toml` с dev-инструментами `ruff`, `pyright`, `pytest`, `pytest-asyncio`;
- local SQLite/filesystem persistence baseline;
- deterministic image diagnostics;
- provider input context boundary;
- media staging port with local/noop backend;
- extraction provider port with deterministic fake provider;
- prompt/schema package boundary;
- backend-owned provider output validation/reconstruction;
- local fake extraction workflow through `RESULT_READY` / `FAILED`;
- `.env.example` с runtime placeholders для OpenRouter/LLM и локального SQLite URL;
- начальный Python package skeleton;
- локальный private Codex overlay, исключённый из Git.

Stage 7–12 backend foundation считается принятой текущей базой. Web/UI/API, real provider transport, real media upload and deployment остаются отложенными.

## Принятые v0-решения

Для первого MVP принято:

- первый happy path обрабатывает одно изображение через Web UI;
- основной demonstrable sample — смешанная рукописная/печатная форма или документ;
- первый UI-вектор — простой локальный Web UI, но Web/UI/API не запускаются до отдельного gate после backend smoke path;
- backend остаётся UI-agnostic и должен быть переиспользуем будущими carriers;
- backend владеет processing job lifecycle, validation, storage и provider orchestration;
- пользователь может выбрать document mode hint, но этот hint не является истиной;
- backend собирает deterministic `ImageDiagnostics` до provider call;
- `ProviderInputContext` является мостом между backend и extraction provider;
- первый provider baseline — OpenRouter с OpenAI vision-capable model через environment;
- media staging должен быть adapter/service boundary; ImgBB допустим как первый temporary image backend, если provider требует public image URL;
- `ExtractionResult v0` является общей базой для result views;
- SQLite + filesystem допустимы как local MVP foundation.

Эти решения являются v0 baseline для разработки MVP. Они не являются production commitment.

## Stage 13B: решения для реальной provider-интеграции

Следующий implementation track должен добавлять реальную provider-интеграцию без нарушения Stage 7–12 boundaries.

Принятые проектные решения для следующих стадий:

- raw provider response нужно сохранять для audit/debug/history/reuse, но не на `DocumentJob`;
- для raw response и ошибок планируется минимальный `extraction_attempts` concept/table;
- `DocumentJob` остаётся владельцем lifecycle и final validated result, а не хранилищем всех provider attempts;
- raw response может содержать чувствительный документный контент;
- full prompts не сохраняются по умолчанию;
- сохраняется только минимальная request metadata: provider, model, schema mode, staged media kind/reference metadata, provider options, correlation/job id, attempt id;
- secrets никогда не сохраняются;
- текущий MVP допускает только один active extraction workflow на job;
- минимальные attempt statuses: `running`, `succeeded`, `failed`;
- real external provider call не должен выполняться внутри долгой DB transaction;
- planned transaction flow: claim job / mark extraction running → commit → provider call outside long transaction → new transaction → persist raw response, validation and final status;
- provider adapter выполняет один call attempt и поднимает typed provider errors;
- retry orchestration принадлежит workflow / attempt runner;
- default `max_retries` остаётся `2`;
- retryable errors: timeout, transient network failure, rate limit, provider 5xx / unavailable;
- non-retryable errors: auth/config, missing media, invalid lifecycle, validation failure без usable extraction content, schema/contract mismatch caused by our code.

Media strategy:

- ImgBB/public URL staging допустим как первый real media backend, потому что legacy audit нашёл reusable implementation pattern;
- ImgBB должен оставаться за `MediaStagingPort`;
- provider workflow не должен зависеть от ImgBB напрямую;
- direct URLs и delete URLs считаются sensitive;
- local filesystem path не должен попадать в provider-facing prompt/request/logs;
- normal tests не должны вызывать real ImgBB.

Provider and structured output strategy:

- real provider integration должна использовать structured output;
- Stage 10 schema package остаётся provider-neutral descriptor;
- provider-specific `response_format` mapping живёт вне Stage 10 schema package;
- OpenRouter-specific mapping не должен загрязнять provider-neutral contracts;
- provider factory/registry должен поддерживать минимум `fake` и `openrouter`;
- OpenRouter adapter конвертирует provider API response в `ExtractionProviderResponse`;
- validation layer остаётся provider-agnostic.

Error/privacy/testing policy:

- планируемые typed provider errors: `ProviderConfigurationError`, `ProviderAuthenticationError`, `ProviderRateLimitError`, `ProviderTimeoutError`, `ProviderUnavailableError`, `ProviderMalformedResponseError`, `ProviderRejectedRequestError`;
- provider adapter применяет timeout из settings, workflow решает retry;
- `VALIDATION_PARTIAL` может доходить до `RESULT_READY`;
- low confidence делает validation outcome `PARTIAL`, но missing confidence не означает low confidence автоматически;
- concurrent extraction для одного job запрещён;
- re-run / retry failed job / force reprocess отложены;
- secrets только через `.env` / settings;
- normal logs: job_id, attempt_id, provider, model, status transitions, validation outcome, retry count, duration;
- normal logs не содержат document content, full prompt, raw response, image base64 или local paths;
- normal pytest не вызывает real providers или real ImgBB;
- real provider smoke должен быть manual и env-gated.

Legacy reuse audit является reference, not source of truth. Reusable/adaptable patterns: OpenRouter/OpenAI-compatible client, response_format builder, JSON parsing/validation adapters, LLM error taxonomy, ImgBB media staging backend, media cleanup/expiry pattern, image data URL helper, smoke script pattern, PDF renderer later. Не переиспользовать напрямую: antique prompts/schemas, antique inference flow, antique workflow state machine, Telegram-specific code, antique markdown renderers.

## Начальный MVP-фокус

Первый MVP должен быть image-first.

Поддерживаемый стартовый класс входов:

- изображения документов;
- рукописные формы;
- смешанные рукописные/печатные формы;
- бизнес-формы;
- простые таблицы;
- сканы и фотографии бумажных документов.

Отложены:

- PDF;
- DOCX;
- XLSX;
- batch processing;
- production-grade export;
- pixel-perfect reconstruction.

Для будущего PDF support потребуется различать:

- digital/searchable PDF, который часто можно парсить;
- scanned/image-only PDF, который требует OCR/image processing;
- mixed PDF, который может потребовать hybrid parser + OCR approach.

## First happy path v0

Первый demonstrable happy path:

1. Пользователь открывает Web UI.
2. Пользователь загружает одно изображение документа.
3. Пользователь выбирает document mode hint или оставляет `auto`.
4. Backend создаёт processing job.
5. Backend проверяет, что файл является открываемым изображением.
6. Backend выполняет deterministic `ImageDiagnostics`.
7. Backend выполняет media staging, если provider требует provider-compatible image reference.
8. Backend формирует `ProviderInputContext`.
9. Backend вызывает extraction provider.
10. Provider возвращает structured output.
11. Backend валидирует provider output и формирует `ExtractionResult`.
12. Backend сохраняет результат и связанные metadata/artifacts.
13. Web UI показывает source image, diagnostics, raw text, fields, tables, blocks/preview, warnings и JSON.

Минимальный успешный результат не обязан быть идеальной реконструкцией документа. Он должен быть честным structured result с явными warnings/uncertainty.

## Document mode hints

Начальные user hints:

- `auto`;
- `form`;
- `table`;
- `free_handwritten_text`;
- `mixed_document`;
- `plain_text`.

Выбранный режим — подсказка, а не истина.

Analyzer/provider result должен включать:

- detected document type;
- confidence;
- possible mode mismatch warning.

Mismatch не должен автоматически блокировать workflow. В большинстве случаев он должен становиться warning, чтобы пользователь мог увидеть частичный или альтернативно интерпретированный результат.

## Minimal job lifecycle v0

Минимальный lifecycle processing job:

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

Смысл состояний:

- `CREATED` — job создан.
- `IMAGE_UPLOADED` — файл принят как изображение.
- `IMAGE_DIAGNOSTICS_READY` — backend собрал deterministic diagnostics.
- `MEDIA_STAGED` — изображение подготовлено для provider.
- `EXTRACTION_RUNNING` — backend вызвал provider adapter.
- `EXTRACTION_SUCCEEDED` — provider вернул structured output, но результат ещё не считается доверенным.
- `VALIDATION_SUCCEEDED` — backend validation прошла успешно.
- `VALIDATION_PARTIAL` — результат частично пригоден, но содержит warnings, missing/unmatched/uncertain values.
- `RESULT_READY` — result views и JSON можно показывать в Web UI.
- `FAILED` — продолжение невозможно.
- `CANCELLED` — job остановлен пользователем или системой.

Low quality image обычно не является terminal failure. Invalid/unreadable image может быть hard reject.

## Backend-first принципы

Backend должен владеть:

- processing job lifecycle;
- ingestion;
- deterministic diagnostics;
- image normalization;
- media/file staging через adapter;
- `ProviderInputContext`;
- extraction provider orchestration;
- structured output validation;
- storage;
- preview/export lifecycle.

Web UI является shell/carrier. Она не должна владеть:

- business logic;
- provider orchestration;
- workflow state;
- validation rules;
- persistence decisions;
- export/rendering lifecycle.

Provider output считается недоверенным до backend validation.

Silent fallback запрещён: ошибки, частичные результаты, пропуски и неопределённость должны быть явными.

Runtime configuration должна идти из environment/.env через settings layer. Нельзя закреплять скрытые runtime defaults в разных местах кода.

## ImageDiagnostics v0

Backend должен собрать deterministic image metadata до LLM/provider call.

Концептуальная структура:

```text
ImageDiagnostics
├── file
├── image
├── quality
├── warnings[]
└── metadata
```

Начальные file/image поля:

- mime type;
- file size;
- file extension;
- sha256, если нужен для integrity/debug;
- width;
- height;
- aspect ratio;
- orientation;
- EXIF orientation, если доступно;
- color mode;
- image format.

Начальные quality поля:

- blur/sharpness score, если реализовано;
- brightness indicator;
- contrast indicator;
- low-resolution marker;
- probable blur marker;
- low-contrast marker.

Quality metrics являются heuristics, not final truth.

Hard reject:

- файл не открывается как image;
- формат не поддержан;
- размер превышает hard limit;
- изображение слишком маленькое для обработки;
- файл повреждён.

Warnings, но не automatic rejection:

- blur;
- low contrast;
- possible skew;
- possible rotation;
- low-ish resolution;
- bad lighting;
- shadows;
- archival/historical poor quality.

Diagnostics используются как provider context, UI metadata, persisted job metadata и источник result warnings.

## ProviderInputContext v0

`ProviderInputContext` — мост между backend и extraction provider.

Он должен собрать всё, что backend знает до provider call:

- user mode hint;
- processing goal;
- provider-compatible image reference;
- image facts;
- image diagnostics summary;
- expected result contract/schema;
- explicit extraction constraints;
- optional future template context.

Концептуальная структура:

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

В prompt/provider context нужно передавать не только изображение, но и сжатую backend-derived информацию:

- image id;
- mime type;
- width/height;
- file size;
- orientation;
- diagnostics warnings;
- selected user mode hint;
- expected extraction goal;
- no-invention / uncertainty rules.

Пример цели:

```text
Recognize handwritten and printed text.
Infer document type.
Extract fields, values, tables, blocks and reading order where visible.
Return uncertainty and warnings explicitly.
Return valid structured output matching the requested schema.
```

## ExtractionResult v0

`ExtractionResult v0` — концептуальный result contract для первого MVP.

Структура:

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

### `document`

Поля:

- `user_mode_hint`;
- `detected_type`;
- `detected_type_confidence`;
- `language`;
- `summary`.

Начальные `detected_type` values:

- `unknown`;
- `plain_text`;
- `form`;
- `table`;
- `mixed_document`;
- `free_handwritten_text`;
- `label_or_plate`;
- `other`.

### `raw_text`

Поля:

- `text`;
- `confidence`, если доступно;
- `warnings[]`.

### `fields[]`

Поля:

- `label`;
- `value`;
- `confidence`, если доступно;
- `source`, если доступно;
- `warnings[]`.

Начальные `source` values:

- `detected`;
- `inferred`;
- `template`;
- `user_hint`;
- `unknown`.

### `tables[]`

Поля:

- `title`, если есть;
- `columns[]`;
- `rows[]`;
- `confidence`, если доступно;
- `warnings[]`.

`rows[]` v0:

- `cells[]`;
- `confidence`, если доступно;
- `warnings[]`.

Tables должны быть пригодны для readable grid / DataFrame-like preview.

### `blocks[]`

Поля:

- `type`;
- `level`, если применимо;
- `text`;
- `order`;
- `confidence`, если доступно;
- `warnings[]`.

Начальные block types:

- `heading`;
- `paragraph`;
- `list`;
- `table`;
- `field_group`;
- `signature`;
- `unknown`.

### `warnings[]`

Поля:

- `code`;
- `message`;
- `severity`;
- `target`, если применимо.

Severity:

- `info`;
- `warning`;
- `error`.

Примеры warning codes:

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

Поля:

- `schema_version`;
- `provider`, если применимо;
- `model`, если применимо;
- `created_at`, если применимо.

`ExtractionResult v0` не обязан включать bbox/coordinates, pages, layout tree, cell geometry, template matching details, human corrections или export artifacts.

## Result views

Один `ExtractionResult` должен поддерживать несколько views:

- source image;
- diagnostics;
- raw text;
- fields;
- tables / DataFrame-like table preview;
- blocks / structured preview;
- warnings;
- JSON.

Web UI должна показывать table-like results как читаемые grids, где это возможно, а не только raw JSON.

## Storage baseline

Для local MVP допустимо:

- SQLite для metadata, jobs, statuses, results;
- filesystem для original/derived artifacts.

Минимально на уровне job нужно хранить:

- job id;
- status;
- user mode hint;
- source image metadata;
- image diagnostics;
- staged media metadata;
- provider run metadata;
- extraction result;
- validation status;
- created/updated timestamps;
- error/warnings summary.

Это local MVP baseline, не production storage commitment.

## Provider/model baseline

Первый implementation baseline:

- OpenRouter;
- OpenAI vision-capable model;
- exact model configured via environment.

Это прагматичный default, а не provider lock-in.

Архитектура должна позволить позже добавить:

- specialized OCR;
- cloud Document AI services;
- other multimodal providers;
- hybrid OCR + LLM flows.

## Отложенные зоны

Пока не фиксируются:

- финальная code schema;
- final Web framework;
- full backend API shape;
- production storage;
- production deployment;
- PDF/DOCX/XLSX processing;
- batch processing;
- template image analysis;
- automatic template learning;
- export в DOCX/XLSX/PDF/CSV;
- pixel-perfect reconstruction;
- human correction workflow;
- ground-truth evaluation workflow.

## Открытые вопросы перед следующими implementation gates

Перед Stage 13C–13F нужно уточнить:

- какой минимальный `extraction_attempts` schema/scope нужен для raw response, request metadata, timestamps и errors;
- какой retention/redaction policy нужен для raw provider response, direct/delete URLs и staged media metadata;
- какие provider settings/env fields нужны для Stage 13C без real network calls;
- какой mocked transport shape нужен для ImgBB и OpenRouter tests;
- какие sample images допустимы для manual env-gated smoke/review без попадания user content в reports/logs;
- какой manual smoke success criterion нужен перед Web/UI/API track;
- какие artifacts/export нужны позже: JSON only, sidecar files, PDF/DOCX/XLSX/CSV или staged approach;
- какой Web stack/API shape нужен после backend smoke path;
- когда создавать `PROJECT_MAP.md`.
