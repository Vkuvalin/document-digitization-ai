# Document Digitization AI

## Overview

`document-digitization-ai` - приватный локальный MVP для оцифровки документов.
Он принимает загруженные изображения документов, запускает AI extraction,
сохраняет job/result state и дает поверхности для проверки структуры,
предпросмотра и экспорта результата.

Проект не является production SaaS и не документируется как публичный продукт.
README нужен владельцу проекта и future maintainer-у, чтобы локально запустить,
проверить и понять текущий MVP.

## MVP Features

Текущие возможности MVP:

- FastAPI backend с app factory `document_digitization_ai.api.http.app:create_app`;
- статический Web UI под `/app`;
- загрузка изображения документа через Web UI или `POST /documents`;
- создание job, polling статуса и история обработанных файлов;
- рабочая область результата с preview исходного файла;
- просмотр сводки, предупреждений, извлеченных значений, таблиц, текста и Markdown;
- Markdown export;
- PDF export;
- удаление job;
- retention policy с настройкой по умолчанию 7 дней;
- безопасная отдача исходного upload через backend preview endpoint, включая режим download.

Поддерживаемый input следует считать image-first: надежная текущая формулировка -
файлы изображений, которые может открыть и диагностировать Pillow. PDF input в UI
может отображаться как допустимый файл, но PDF extraction input пока не
зафиксирован как гарантированная capability.

## Not in Scope

В текущий MVP не входят:

- auth, login, accounts;
- billing, quotas, subscriptions;
- multi-user isolation или tenant model;
- production deployment;
- generic artifact explorer;
- raw/sanitized JSON UI;
- PDF viewer/editor;
- full original-layout reconstruction;
- batch processing;
- user correction workflow.

## Requirements

Практические требования для локальной работы:

- Python `>=3.14` согласно `pyproject.toml`;
- `uv` для запуска команд и управления окружением;
- локальный `.env`, созданный на основе `.env.example`;
- provider/media secrets только если включается real-provider path через
  OpenRouter и ImgBB.

Для default local flow реальные внешние провайдеры не нужны: по умолчанию
используется deterministic fake provider.

## Configuration

Начальная точка конфигурации - `.env.example`. Обычно локально создается `.env`
и редактируется под нужный режим:

```powershell
Copy-Item .env.example .env
```

Основные группы настроек:

- provider settings: выбор `fake` или `openrouter`, OpenRouter URL/model и LLM policy;
- media staging settings: `none` для локального fake flow или `imgbb` для public media URL;
- storage paths: SQLite database, upload artifacts и result artifacts;
- upload limits: максимальный размер файла и image diagnostics thresholds;
- artifact retention days: срок хранения artifacts, по умолчанию 7 дней.

Секреты должны храниться только в локальном `.env`. Нельзя коммитить реальные
API keys, local credentials или generated runtime artifacts.

## Running Locally

Локальный manual server можно запустить так:

```powershell
uv run --with uvicorn uvicorn document_digitization_ai.api.http.app:create_app --factory --host 127.0.0.1 --port 8000
```

`uvicorn` здесь предоставляется временно через `uv --with` для локального/manual
запуска. Он не является закрепленной runtime dependency проекта, пока это не
появится в dependency files или отдельном approved runner/script.

После запуска открыть:

```text
http://127.0.0.1:8000/app
```

Healthcheck:

```text
http://127.0.0.1:8000/health
```

## Using the Web UI

Базовый локальный сценарий:

1. Открыть `/app`.
2. Загрузить изображение документа.
3. Дождаться завершения анализа.
4. Проверить результат в рабочей области.
5. Использовать `Мои файлы` для истории job.
6. Открывать preview исторических файлов.
7. Скачать Markdown или PDF.
8. Удалить job, когда результат больше не нужен.

Web UI является carrier для backend capabilities. Extraction, validation,
storage, provider policy и exports остаются backend-owned.

## Exports

Markdown export - user-facing и очищенный. Он предназначен для чтения,
копирования или скачивания результата без provider/debug internals.

PDF export - user-facing файл, отдаваемый backend-ом как `application/pdf`.

Default exports включают пользовательские разделы: сводку, предупреждения,
поля/значения, таблицы и пользовательский текст. Они не должны раскрывать Extraction Metadata,
provider raw/sanitized responses, debug internals, secrets, local paths,
job/attempt IDs или image diagnostics internals.

## Storage, Preview, Delete and Retention

По умолчанию локальные данные лежат под настроенными storage roots:

- SQLite database: `./data/app.db`;
- uploads: `./data/uploads`;
- results: `./data/results`.

Uploaded files и extraction results сохраняются backend-ом. Preview исходного
файла проходит через backend endpoint `GET /jobs/{job_id}/preview`, а не через
прямую раздачу произвольных paths.

Raw/sanitized/debug provider artifacts могут существовать во внутреннем storage,
но не являются user-facing UI surface. Generic artifact download endpoint в MVP
не заявлен.

`DELETE /jobs/{job_id}` удаляет job state и выполняет safe cleanup связанных
upload/result directories. Retention setting по умолчанию равен 7 дням.
Cleanup logic callable и покрывается тестами, но автоматический scheduler,
cron, background worker, CLI или public cleanup endpoint сейчас не заявлены.

## Validation

Основные команды проверки:

```powershell
uv run pytest
uv run ruff check .
uv run pyright
git diff --check
```

Default automated validation не должна выполнять реальные внешние provider
calls. Real-provider smoke запускается отдельно и только при явном включении
соответствующих env settings.

## Manual Smoke Checklist

Короткая ручная проверка local MVP:

- запустить server;
- открыть `/app`;
- загрузить изображение;
- дождаться результата;
- проверить preview;
- проверить values, tables и text;
- скачать Markdown;
- скачать PDF;
- удалить job;
- убедиться, что job исчезла из списка.

## Known Limitations

- Качество изображения напрямую влияет на extraction result.
- Рукописный текст может распознаваться неуверенно.
- Provider classification и структура ответа могут варьироваться.
- Table-derived values помогают сгладить различия между field/table extraction,
  но не гарантируют идеальную нормализацию.
- PDF export поддерживается, но PDF extraction input не гарантирован.
- Нет auth, accounts или multi-user isolation.
- Нет scheduler/cron для автоматической retention cleanup.
- Нет production SaaS-ready deployment path.
- Нет full original-layout reconstruction.
- Нет generic artifact explorer или arbitrary artifact download.

## Project Documentation

Текущая документационная база MVP:

- [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md)
- [docs/DEVELOPMENT_CHECKLIST.md](docs/DEVELOPMENT_CHECKLIST.md)
- [docs/LLM_MODEL_POLICY.md](docs/LLM_MODEL_POLICY.md)
- [docs/PROJECT_MAP.md](docs/PROJECT_MAP.md)
