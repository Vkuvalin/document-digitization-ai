# PROJECT_CONTEXT.md

## Назначение проекта

`document-digitization-ai` — backend-first MVP для оцифровки документов по изображениям. Цель проекта шире обычного OCR: система должна не только распознавать текст, но и восстанавливать цифровое представление документа.

Важный продуктовый фокус:

- распознать печатный и рукописный текст;
- понять, к каким полям, строкам, колонкам, ячейкам, блокам и секциям относится текст;
- явно показывать неопределённость, пропуски и неоднозначные сопоставления;
- отдавать проверенные структурированные данные, пригодные для дальнейшего просмотра и экспорта.

## Текущий статус репозитория

Проект находится на стадии bootstrap.

Уже есть:

- публичный репозиторий `document-digitization-ai`;
- Python/uv baseline;
- Python `3.14`;
- `pyproject.toml` с dev-инструментами `ruff`, `pyright`, `pytest`, `pytest-asyncio`;
- пустой список product dependencies;
- `.env.example` с runtime placeholders для OpenRouter/LLM и локального SQLite URL;
- начальный Python package skeleton.

Ещё не принято:

- финальная product architecture;
- provider/model/prompt/schema policy;
- Web stack и API shape;
- storage/export/rendering architecture;
- production workflow и deployment path.

## Начальный MVP-фокус

Первый MVP должен быть image-first:

- изображения документов;
- рукописные формы;
- смешанные рукописные/печатные формы;
- бизнес-формы;
- простые таблицы;
- сканы и фотографии бумажных документов.

PDF, DOCX, XLSX, batch processing и production-grade export отложены. Для PDF отдельно потребуется различать searchable PDF, scanned/image-only PDF и mixed PDF.

## Image-first и Web-first направление

Первый демонстрируемый интерфейс предполагается Web-first: простая локальная Web UI, подключённая к backend API.

Минимально ожидаемые возможности Web UI:

- загрузка изображения;
- preview исходного документа;
- статус обработки;
- отображение распознанного текста;
- отображение полей, таблиц и предупреждений;
- базовый review результата;
- будущий download/export.

Web UI должна оставаться оболочкой. Она не должна владеть workflow, provider orchestration, validation, persistence или бизнес-логикой.

## Backend-first принципы

Backend должен владеть:

- workflow и processing state;
- ingestion и image normalization;
- media/file staging через adapter;
- extraction provider orchestration;
- structure reconstruction;
- validation provider output;
- storage и lifecycle результата;
- preview/export generation.

Provider output считается недоверенным до backend validation. Silent fallback запрещён: ошибки, частичные результаты, пропуски и неопределённость должны быть явными.

Runtime configuration должна идти из environment/.env через settings layer. Нельзя закреплять скрытые runtime defaults в разных местах кода.

## Отложенные зоны

Пока не фиксируются:

- точный OpenRouter model;
- финальная extraction schema;
- финальная reconstruction schema;
- Web framework;
- backend API shape;
- template schema format;
- production storage;
- provider mix;
- экспорт в DOCX/XLSX/PDF/CSV;
- pixel-perfect reconstruction;
- batch processing;
- production deployment.

## Открытые вопросы

- Какой первый demonstrable happy path выбрать?
- Начинать только с no-template extraction или добавить optional manual template schema ранним шагом?
- Как представить confidence/uncertainty без ложной точности?
- Как разделить raw text extraction и structure reconstruction в backend contracts?
- Какой минимальный JSON result contract нужен для первого MVP?
- Как проверять результат на пользовательском ground truth?
- Какая media staging стратегия нужна для первого provider experiment?
- Какие исследования нужны перед выбором Web stack, provider и storage boundaries?
