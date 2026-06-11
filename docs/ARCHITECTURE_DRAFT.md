# ARCHITECTURE_DRAFT.md

## Статус документа

Это черновик архитектурного направления, а не финальный source of truth.

Документ фиксирует начальную рамку для обсуждения и следующих маленьких итераций. Он не утверждает конкретный provider, model, Web stack, storage backend, schema format или production deployment.

## Высокоуровневый pipeline

Ориентир для backend-controlled document understanding pipeline:

```text
Web UI
→ Backend API
→ Ingestion
→ Image normalization
→ Media staging
→ Extraction provider
→ Structure reconstruction
→ Validation
→ Storage
→ Preview/export
→ Web UI review
```

Backend является владельцем workflow, состояния обработки, validation, persistence, provider orchestration и generation результата.

## Web UI как shell/carrier

Web UI нужна для загрузки изображения, просмотра исходника, статуса обработки, review результата и будущего экспорта.

Web UI не должна владеть:

- бизнес-логикой;
- provider-specific logic;
- workflow state;
- validation rules;
- persistence decisions;
- export/rendering lifecycle.

Будущие carriers, например CLI, external API, Telegram или production Web App, должны иметь возможность переиспользовать backend contracts.

## Ingestion, image normalization и media staging

Начальный ingestion scope — image files.

Image normalization может постепенно включать:

- проверку формата;
- ограничения размера;
- metadata изображения;
- лёгкую подготовку к обработке;
- создание normalized artifact.

Первую версию не нужно перегружать image preprocessing.

Media staging должен быть изолирован adapter-слоем. Если provider требует публичный URL, временный backend вроде ImgBB может быть рассмотрен как MVP-прагматика, но он не должен протекать в бизнес-логику или extraction contracts.

Возможные будущие staging варианты:

- local file;
- base64 payload;
- provider file upload;
- temporary public URL;
- S3/R2-like storage;
- другой temporary hosting provider.

## Extraction provider abstraction

Первый extraction provider может быть vision-capable моделью через OpenRouter, но точная модель не выбрана и не должна фиксироваться этим документом.

Provider-specific код должен находиться за adapter boundary. Backend workflow должен работать с внутренними contracts, а не с сырым форматом конкретного provider.

Будущие provider варианты должны оставаться возможными:

- specialized OCR engines;
- cloud Document AI services;
- multimodal LLM providers;
- hybrid OCR + LLM reconstruction.

## Text extraction и structure reconstruction

Text extraction и structure reconstruction — разные concerns.

Text extraction отвечает за распознавание текста и полезных признаков из изображения.

Structure reconstruction отвечает за восстановление связей и формы документа:

- fields;
- label → value links;
- tables;
- rows;
- columns;
- cells;
- sections;
- blocks;
- reading order;
- missing values;
- unmatched values;
- uncertain values.

Система не должна сводиться к plain text OCR output.

## Validation boundary

Provider output считается недоверенным.

Backend validation должна проверять:

- соответствие ожидаемым schemas/contracts;
- malformed structured output;
- missing required fields, если такие поля заданы contract/template;
- ambiguous mappings;
- unmatched extracted text;
- uncertain values;
- provider errors;
- partial failures.

Silent fallback запрещён. Если результат неполный, неоднозначный или невалидный, это должно быть отражено в structured result и warnings.

## SQLite и local storage baseline

SQLite допустим как локальный MVP baseline, но не как production commitment.

Потенциальные данные для хранения:

- jobs;
- uploaded file metadata;
- processing status;
- staged media metadata;
- raw extraction result;
- reconstructed structure;
- validation status;
- preview/export metadata.

Filesystem может хранить оригинальные и производные artifacts. Конкретная repository/session pattern должна быть спроектирована отдельной approved итерацией.

## Preview и export lifecycle

Надёжное ядро результата — validated structured data.

Начальные outputs:

- raw recognized text;
- structured fields;
- tables/rows/columns/cells, если обнаружены;
- uncertainty markers;
- validation warnings;
- missing/unmatched values;
- machine-readable JSON;
- human-readable preview.

Для MVP preview может быть HTML или Markdown в Web UI.

Отложенные exports:

- DOCX;
- XLSX;
- PDF;
- CSV;
- production-grade document reconstruction;
- pixel-perfect visual reconstruction.

Rendering/export logic не должна зависеть напрямую от LLM calls.

## Extensibility

Архитектура должна оставить путь к template-guided extraction:

- Level 1: no reference, extraction from filled document image;
- Level 3: manual structured template schema, подготовленная заранее;
- Level 2: reference template image analysis, позже.

Ранний предпочтительный путь — начать с Level 1 и не закрывать возможность Level 3. Template-guided extraction должна оставаться schema-driven и backend-validated, а не prompt-only reconstruction.
