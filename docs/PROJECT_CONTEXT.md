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

Проект находится на стадии раннего bootstrap / architecture planning.

Уже есть:

- публичный репозиторий `document-digitization-ai`;
- Python/uv baseline;
- Python `3.14`;
- `pyproject.toml` с dev-инструментами `ruff`, `pyright`, `pytest`, `pytest-asyncio`;
- пустой список product dependencies;
- `.env.example` с runtime placeholders для OpenRouter/LLM и локального SQLite URL;
- начальный Python package skeleton;
- локальный private Codex overlay, исключённый из Git.

Product code ещё не реализован.

## Принятые v0-решения

Для первого MVP принято:

- первый happy path обрабатывает одно изображение через Web UI;
- основной demonstrable sample — смешанная рукописная/печатная форма или документ;
- первый UI-вектор — простой локальный Web UI;
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

## Открытые вопросы перед implementation

Перед первым product code нужно уточнить:

- какие поля из `ExtractionResult v0` становятся обязательными в code schema;
- какой минимальный API shape нужен для happy path;
- какая минимальная `ImageDiagnostics` реализация достаточна без over-engineering;
- какой Web stack использовать;
- как именно хранить original/derived artifacts;
- нужен ли background processing или достаточно sync/async request flow для MVP;
- как формировать first prompt и provider response schema;
- какие sample images использовать для manual smoke/review;
- когда создавать `PROJECT_MAP.md`.
