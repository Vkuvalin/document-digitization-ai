# Manual Provider Smoke

Stage 13F manual smoke проверяет компонентный путь `ImgBB -> OpenRouter -> Stage 11 validation` без подключения к `LocalDocumentApplication` или `DocumentExtractionWorkflowService`.

Скрипт предназначен только для ручного локального запуска. Обычный `pytest` не запускает реальные ImgBB/OpenRouter запросы.

OpenRouter adapter использует OpenAI-compatible SDK transport (`AsyncOpenAI`) с `OPENROUTER_BASE_URL`.

## Требования

Перед запуском должны быть заданы реальные env vars:

- `RUN_REAL_PROVIDER_SMOKE=1`
- `MEDIA_STAGING_BACKEND=imgbb`
- `EXTRACTION_PROVIDER=openrouter`
- `IMGBB_API_KEY`
- `OPENROUTER_API_KEY`
- `OPENROUTER_MODEL`

`OPENROUTER_MODEL` не должен оставаться `change_me`.

## Пример запуска

```bash
RUN_REAL_PROVIDER_SMOKE=1 \
MEDIA_STAGING_BACKEND=imgbb \
EXTRACTION_PROVIDER=openrouter \
MEDIA_STAGING_TTL_SECONDS=600 \
IMGBB_API_KEY=<imgbb-api-key> \
OPENROUTER_API_KEY=<openrouter-api-key> \
OPENROUTER_MODEL=<openrouter-vision-model> \
uv run python scripts/manual_provider_smoke.py --image path/to/sample.jpg
```

PowerShell-вариант:

```powershell
$env:RUN_REAL_PROVIDER_SMOKE = "1"
$env:MEDIA_STAGING_BACKEND = "imgbb"
$env:EXTRACTION_PROVIDER = "openrouter"
$env:MEDIA_STAGING_TTL_SECONDS = "600"
$env:IMGBB_API_KEY = "<imgbb-api-key>"
$env:OPENROUTER_API_KEY = "<openrouter-api-key>"
$env:OPENROUTER_MODEL = "<openrouter-vision-model>"
uv run python scripts/manual_provider_smoke.py --image path/to/sample.jpg
```

Не коммитьте реальные secrets, sample images или результат smoke.

## Что проверяет скрипт

Скрипт выполняет один проход:

1. Проверяет env gate `RUN_REAL_PROVIDER_SMOKE=1`.
2. Проверяет settings и локальный image path до сетевых вызовов.
3. Собирает deterministic image diagnostics.
4. Строит in-memory `ProviderInputContext`.
5. Загружает image через существующий `MediaStagingPort` / ImgBB backend.
6. Строит prompt package и schema package.
7. Строит `ExtractionProviderRequest`.
8. Создает OpenRouter provider через существующий factory.
9. Делает один provider call без retry-loop.
10. Валидирует результат через `validate_provider_output()`.
11. Печатает safe summary.

По умолчанию output не содержит API keys, ImgBB `delete_url`, staged public URL, full raw provider response или full document text.

## Опции CLI

- `--image PATH` — обязательный путь к локальному image file.
- `--json-summary` — печатает summary как JSON.
- `--verbose` — добавляет non-sensitive diagnostics counts/codes.
- `--print-result` — печатает sanitized structured validation result; secrets, URLs, cleanup/delete данные и `raw_text.text` редактируются.

## Exit codes

- `0` — provider call успешен и Stage 11 validation приняла результат.
- `2` — env/config/precondition failure.
- `3` — media staging failure.
- `4` — provider failure.
- `5` — validation failed/no usable content.
- `1` — unexpected failure.
