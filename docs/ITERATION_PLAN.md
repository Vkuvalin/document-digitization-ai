# ITERATION_PLAN.md

## Статус плана

Это практический стартовый план, а не обещание финальной архитектуры. Он задаёт порядок маленьких проверяемых шагов после repo bootstrap.

Repo bootstrap уже выполнен: Python/uv baseline есть, product dependencies пока не добавлены, product architecture ещё не утверждена.

## Рабочие принципы

- Двигаться маленькими approved задачами.
- Перед implementation фиксировать scope и validation gates.
- Не добавлять dependencies до architecture/research justification.
- Не создавать source-of-truth docs сверх явно запрошенных.
- Не начинать product implementation из одного только brief.
- Не выдавать гипотезы за принятые решения.
- Использовать audit/report checkpoints перед рискованными изменениями.

## Этап 0. Dry documentation baseline

Цель: создать начальный контекст без реализации.

Артефакты:

- `docs/PROJECT_CONTEXT.md`;
- `docs/ARCHITECTURE_DRAFT.md`;
- `docs/ITERATION_PLAN.md`.

Проверка:

- документы не утверждают финальную architecture;
- нет новых dependencies;
- нет product code changes;
- `PROJECT_MAP.md` не создаётся.

## Этап 1. Research и architecture checkpoints

Цель: снизить риск перед первой реализацией.

Возможные отдельные задачи:

- выбрать первый demonstrable happy path;
- сравнить варианты extraction result contract;
- исследовать provider input/output constraints;
- определить минимальный validation boundary;
- уточнить media staging requirements;
- выбрать минимальный Web/backend API interaction только после отдельного approval.

Результатом должны быть findings или короткие docs updates, но не implementation by default.

## Этап 2. Минимальные backend contracts

Цель: определить минимальные внутренние структуры до provider integration.

Возможные blocks:

- job state contract;
- uploaded image metadata contract;
- raw extraction result contract;
- reconstructed structure contract;
- validation warnings/errors contract.

Каждый block должен быть отдельной задачей с тестами, если появляется код.

## Этап 3. Settings и runtime boundaries

Цель: подготовить runtime configuration без hidden constants.

Возможные blocks:

- grouped settings;
- LLM/extraction settings;
- storage settings;
- retry policy, если она действительно нужна;
- явная ошибка при отсутствующей обязательной конфигурации.

На этом этапе не нужно выбирать production provider или добавлять лишние adapters.

## Этап 4. Ingestion и local artifact handling

Цель: принять image input и подготовить его для backend workflow.

Возможные blocks:

- image file validation;
- normalized artifact metadata;
- filesystem artifact layout;
- clean import path для backend modules;
- тесты без real external API calls.

PDF, DOCX, XLSX и batch остаются вне scope.

## Этап 5. Extraction provider experiment

Цель: подключить первый provider только после approved contract и staging plan.

Возможные blocks:

- provider adapter interface;
- OpenRouter adapter experiment;
- structured-output request/response handling;
- schema preparation/sanitization, если требуется;
- explicit provider error handling.

Manual smoke scripts могут вызывать real API только явно, вне automated tests.

## Этап 6. Validation и reconstruction loop

Цель: отделить provider output от доверенного backend result.

Возможные blocks:

- validation of extraction result;
- explicit partial/uncertain/missing/unmatched markers;
- reconstruction rules for fields/tables/blocks;
- JSON result contract;
- test fixtures и test doubles только в tests.

## Этап 7. Local storage baseline

Цель: сохранить processing state и результаты локально.

Возможные blocks:

- SQLite job repository;
- artifact metadata storage;
- status transitions;
- validation status persistence;
- preview/export metadata lifecycle.

SQLite остаётся local MVP baseline, не production architecture decision.

## Этап 8. Web shell

Цель: добавить простой Web carrier после backend contracts.

Возможные blocks:

- upload screen;
- document preview;
- processing status;
- text/structure/warnings display;
- basic review;
- download/export placeholder только после отдельного approval.

Web UI не должна владеть business logic или provider orchestration.

## Этап 9. Preview/export

Цель: показать validated structured result человеку и машине.

Возможные blocks:

- JSON output;
- HTML или Markdown preview;
- export metadata lifecycle;
- отложенная оценка DOCX/XLSX/PDF/CSV.

Pixel-perfect reconstruction откладывается.

## Checkpoints

Перед каждой implementation итерацией:

- подтвердить scope;
- проверить, не требуется ли audit-only, docs-update, diff-review или subagent-routing;
- определить validation commands;
- не смешивать provider, storage, UI и export decisions в одной задаче без approval.

После non-trivial diff:

- выполнить релевантную validation;
- проверить `git status`;
- кратко зафиксировать risks, assumptions и next safe step.

`PROJECT_MAP.md` стоит создавать позже, только когда появится реальная architecture/code structure, которую можно описывать фактологически.
