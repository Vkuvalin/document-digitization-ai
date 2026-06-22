(function () {
  const POLL_INTERVAL_MS = 1500;
  const POLL_TIMEOUT_MS = 120000;

  const STATUS_LABELS = {
    CANCELLED: "Отменён",
    COMPLETE: "Готово",
    CREATED: "Создан",
    ERROR: "Ошибка",
    EXTRACTION_RUNNING: "Идёт анализ",
    EXTRACTION_SUCCEEDED: "Анализ завершён",
    FAILED: "Ошибка",
    IMAGE_DIAGNOSTICS_READY: "Проверка изображения готова",
    IMAGE_UPLOADED: "Файл загружен",
    MEDIA_STAGED: "Медиа подготовлено",
    NEEDS_REVIEW: "Требует проверки",
    RESULT_READY: "Готово",
    VALIDATION_ERROR: "Ошибка проверки",
    VALIDATION_FAILED: "Проверка не пройдена",
    VALIDATION_PARTIAL: "Частичная проверка",
    VALIDATION_SUCCEEDED: "Проверка пройдена",
  };

  const DOCUMENT_TYPE_LABELS = {
    form: "Форма",
    free_handwritten_text: "Рукописный текст",
    label_or_plate: "Этикетка или табличка",
    mixed_document: "Смешанный документ",
    other: "Другой документ",
    plain_text: "Обычный текст",
    table: "Таблица",
    unknown: "Тип не определён",
  };

  const LANGUAGE_LABELS = {
    en: "Английский",
    ru: "Русский",
  };

  const SEVERITY_LABELS = {
    error: "Ошибка",
    info: "Информация",
    warning: "Предупреждение",
  };

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function parseInlineMarkdown(value) {
    return escapeHtml(value).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  }

  function parseMarkdownTable(lines) {
    const rows = lines
      .map((line) =>
        line
          .trim()
          .replace(/^\|/, "")
          .replace(/\|$/, "")
          .split("|")
          .map((cell) => cell.trim()),
      )
      .filter((row) => !row.every((cell) => /^:?-{3,}:?$/.test(cell)));

    if (!rows.length) {
      return "";
    }

    const [head, ...body] = rows;
    const headers = head.map((cell) => `<th>${parseInlineMarkdown(cell)}</th>`).join("");
    const bodyRows = body
      .map((row) => `<tr>${row.map((cell) => `<td>${parseInlineMarkdown(cell)}</td>`).join("")}</tr>`)
      .join("");

    return `
      <div class="table-wrap">
        <table class="markdown-table">
          <thead><tr>${headers}</tr></thead>
          <tbody>${bodyRows}</tbody>
        </table>
      </div>
    `;
  }

  function renderMarkdown(markdown) {
    const lines = String(markdown || "").split(/\r?\n/);
    const output = [];
    let index = 0;

    while (index < lines.length) {
      const line = lines[index].trimEnd();

      if (!line.trim()) {
        index += 1;
        continue;
      }

      if (line.startsWith("|")) {
        const tableLines = [];

        while (index < lines.length && lines[index].trim().startsWith("|")) {
          tableLines.push(lines[index]);
          index += 1;
        }

        output.push(parseMarkdownTable(tableLines));
        continue;
      }

      if (line.startsWith("- ")) {
        const listItems = [];

        while (index < lines.length && lines[index].trim().startsWith("- ")) {
          listItems.push(`<li>${parseInlineMarkdown(lines[index].trim().slice(2))}</li>`);
          index += 1;
        }

        output.push(`<ul>${listItems.join("")}</ul>`);
        continue;
      }

      if (line.startsWith("### ")) {
        output.push(`<h3>${parseInlineMarkdown(line.slice(4))}</h3>`);
      } else if (line.startsWith("## ")) {
        output.push(`<h2>${parseInlineMarkdown(line.slice(3))}</h2>`);
      } else if (line.startsWith("# ")) {
        output.push(`<h1>${parseInlineMarkdown(line.slice(2))}</h1>`);
      } else {
        output.push(`<p>${parseInlineMarkdown(line)}</p>`);
      }

      index += 1;
    }

    if (!output.length) {
      return "<div class=\"empty-state\"><strong>Markdown пока недоступен</strong></div>";
    }

    return `<article class="markdown-preview">${output.join("")}</article>`;
  }

  function isObject(value) {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  function asArray(value) {
    return Array.isArray(value) ? value : [];
  }

  function textOrFallback(value, fallback) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }

    if (typeof value === "number" || typeof value === "boolean") {
      return String(value);
    }

    return fallback;
  }

  function readableFallback(value, fallback) {
    const text = textOrFallback(value, fallback);
    if (!text || text === fallback) {
      return fallback;
    }

    const normalized = text.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
    if (!normalized) {
      return fallback;
    }

    if (normalized === normalized.toUpperCase()) {
      return normalized.toLocaleLowerCase("ru-RU");
    }

    return normalized;
  }

  function normalizeStatus(status) {
    return String(status || "").trim().toUpperCase();
  }

  function statusLabel(status, resultAvailable) {
    const normalized = normalizeStatus(status);

    if (resultAvailable && !normalized) {
      return "Готово";
    }

    return STATUS_LABELS[normalized] || readableFallback(status, "Статус неизвестен");
  }

  function isTerminalStatus(status) {
    const normalized = normalizeStatus(status);
    return normalized === "RESULT_READY" || normalized === "FAILED" || normalized === "CANCELLED" || normalized === "COMPLETE";
  }

  function isFailedStatus(status) {
    const normalized = normalizeStatus(status);
    return normalized === "FAILED" || normalized === "CANCELLED" || normalized === "ERROR";
  }

  function formatFileSize(size) {
    if (!Number.isFinite(size) || size <= 0) {
      return "";
    }

    const units = ["B", "KB", "MB", "GB"];
    let value = size;
    let index = 0;

    while (value >= 1024 && index < units.length - 1) {
      value /= 1024;
      index += 1;
    }

    return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
  }

  function formatDate(value) {
    if (!value) {
      return "Дата неизвестна";
    }

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }

    return new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      month: "2-digit",
      year: "numeric",
    }).format(date);
  }

  function formatConfidence(value) {
    if (typeof value === "number" && Number.isFinite(value)) {
      if (value >= 0 && value <= 1) {
        return `${Math.round(value * 100)}%`;
      }

      return `${Math.round(value)}%`;
    }

    if (typeof value === "string" && value.trim()) {
      return value;
    }

    return "Не указана";
  }

  function shortId(jobId) {
    return String(jobId || "").slice(0, 8) || "без id";
  }

  function fileNameFromArtifacts(artifacts) {
    const artifact = asArray(artifacts).find((item) => item && item.relative_path);
    if (!artifact) {
      return "";
    }

    const parts = String(artifact.relative_path).split("/");
    return parts[parts.length - 1] || "";
  }

  function documentTypeLabel(value) {
    const key = String(value || "unknown").trim();
    return DOCUMENT_TYPE_LABELS[key] || readableFallback(key, "Тип не определён");
  }

  function languageLabel(value) {
    const key = String(value || "").trim().toLowerCase();
    return LANGUAGE_LABELS[key] || readableFallback(value, "Не указан");
  }

  function validationLabel(value, fallbackStatus, resultAvailable) {
    const normalized = normalizeStatus(value);
    if (normalized) {
      return STATUS_LABELS[normalized] || readableFallback(value, "Проверка не указана");
    }

    return statusLabel(fallbackStatus, resultAvailable);
  }

  function warningFromPayload(payload, defaultTarget) {
    if (!isObject(payload)) {
      return null;
    }

    return {
      code: readableFallback(payload.code, "Предупреждение"),
      message: textOrFallback(payload.message, "Предупреждение без описания."),
      severity: SEVERITY_LABELS[payload.severity] || textOrFallback(payload.severity, "Предупреждение"),
      target: textOrFallback(payload.target, defaultTarget),
    };
  }

  function warningNotes(warnings) {
    return asArray(warnings)
      .map((warning) => textOrFallback(warning.message, ""))
      .filter(Boolean)
      .join("; ");
  }

  function normalizeFields(result) {
    return asArray(result.fields).map((field, index) => {
      const payload = isObject(field) ? field : {};
      const source = textOrFallback(payload.source, "Источник не указан");
      return {
        confidence: formatConfidence(payload.confidence),
        label: textOrFallback(payload.label, `Поле ${index + 1}`),
        notes: warningNotes(payload.warnings) || source,
        value: textOrFallback(payload.value, ""),
      };
    });
  }

  function normalizeTables(result) {
    return asArray(result.tables).map((table, index) => {
      const payload = isObject(table) ? table : {};
      const columns = asArray(payload.columns).map((column) => textOrFallback(column, ""));
      const rows = asArray(payload.rows).map((row) => {
        if (Array.isArray(row)) {
          return row.map((cell) => textOrFallback(cell, ""));
        }

        if (isObject(row)) {
          return asArray(row.cells).map((cell) => textOrFallback(cell, ""));
        }

        return [textOrFallback(row, "")];
      });

      return {
        columns: columns.length ? columns : ["Значение"],
        name: textOrFallback(payload.title, `Таблица ${index + 1}`),
        rows,
      };
    });
  }

  function normalizeWarnings(result) {
    const warnings = [];

    asArray(result.warnings).forEach((warning) => {
      const normalized = warningFromPayload(warning, "Результат");
      if (normalized) {
        warnings.push(normalized);
      }
    });

    if (isObject(result.raw_text)) {
      asArray(result.raw_text.warnings).forEach((warning) => {
        const normalized = warningFromPayload(warning, "Текст");
        if (normalized) {
          warnings.push(normalized);
        }
      });
    }

    asArray(result.fields).forEach((field) => {
      const payload = isObject(field) ? field : {};
      const target = textOrFallback(payload.label, "Поле");
      asArray(payload.warnings).forEach((warning) => {
        const normalized = warningFromPayload(warning, target);
        if (normalized) {
          warnings.push(normalized);
        }
      });
    });

    asArray(result.tables).forEach((table, index) => {
      const payload = isObject(table) ? table : {};
      const target = textOrFallback(payload.title, `Таблица ${index + 1}`);
      asArray(payload.warnings).forEach((warning) => {
        const normalized = warningFromPayload(warning, target);
        if (normalized) {
          warnings.push(normalized);
        }
      });
    });

    return warnings;
  }

  function renderFields(fields) {
    if (!fields.length) {
      return "<div class=\"empty-state\"><strong>Поля вне таблиц не найдены</strong></div>";
    }

    const rows = fields
      .map(
        (field) => `
          <tr>
            <td>${escapeHtml(field.label)}</td>
            <td>${escapeHtml(field.value)}</td>
            <td>${escapeHtml(field.confidence)}</td>
            <td>${escapeHtml(field.notes)}</td>
          </tr>
        `,
      )
      .join("");

    return `
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Поле</th>
              <th>Значение</th>
              <th>Уверенность</th>
              <th>Примечание</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  }

  function renderTables(tables) {
    if (!tables.length) {
      return "<div class=\"empty-state\"><strong>Таблицы не найдены</strong></div>";
    }

    return tables
      .map((table) => {
        const headers = table.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
        const rows = table.rows
          .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
          .join("");

        return `
          <section class="table-section">
            <h3>${escapeHtml(table.name)}</h3>
            <div class="table-wrap">
              <table>
                <thead><tr>${headers}</tr></thead>
                <tbody>${rows}</tbody>
              </table>
            </div>
          </section>
        `;
      })
      .join("");
  }

  function renderProcessingState(job) {
    return `
      <div class="loading-state processing-state">
        <span class="loading-spinner" aria-hidden="true"></span>
        <div>
          <strong>${escapeHtml(job.statusLabel || "Обрабатываем документ")}</strong>
          <p>${escapeHtml(job.loadingMessage || "Ожидаем результат от сервера.")}</p>
        </div>
      </div>
    `;
  }

  function renderErrorState(message) {
    return `
      <div class="error-state">
        <div>
          <strong>Не удалось показать результат</strong>
          <p>${escapeHtml(message || "Повторите запрос позже.")}</p>
        </div>
      </div>
    `;
  }

  function delay(ms, signal) {
    return new Promise((resolve, reject) => {
      if (signal.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }

      const timeoutId = window.setTimeout(resolve, ms);
      const abortHandler = () => {
        window.clearTimeout(timeoutId);
        reject(new DOMException("Aborted", "AbortError"));
      };
      signal.addEventListener("abort", abortHandler, { once: true });
    });
  }

  function initWorkspace(options) {
    const apiClient = options.apiClient;
    const overlay = document.getElementById("workspaceOverlay");
    const backdrop = document.getElementById("workspaceBackdrop");
    const closeButton = document.getElementById("closeWorkspaceButton");
    const openJobsButton = document.getElementById("openJobsButton");
    const previewStatus = document.getElementById("previewStatus");
    const previewPanel = document.querySelector(".workspace-preview-panel");
    const workspaceGrid = document.querySelector(".workspace-grid");
    const preview = document.getElementById("workspacePreview");
    const meta = document.getElementById("workspaceMeta");
    const resultTitle = document.getElementById("resultTitle");
    const empty = document.getElementById("workspaceEmpty");
    const content = document.getElementById("workspaceResultContent");
    const tabPanel = document.getElementById("resultTabPanel");
    const tabButtons = Array.from(document.querySelectorAll("[data-result-tab]"));
    const copyButton = document.getElementById("copyMarkdownButton");
    const downloadButton = document.getElementById("downloadMarkdownButton");
    const jobList = document.getElementById("workspaceJobList");
    const toast = document.getElementById("toast");
    let jobs = [];
    let activeJob = null;
    let activeTab = "summary";
    let toastTimer = null;
    let jobsState = "idle";
    let jobListError = "";
    let selectionToken = 0;
    let pollingController = null;
    let historyController = null;

    function showToast(message) {
      window.clearTimeout(toastTimer);
      toast.textContent = message;
      toast.classList.remove("is-hidden");
      toastTimer = window.setTimeout(() => {
        toast.classList.add("is-hidden");
      }, 2200);
    }

    function createHistoryJob(summary) {
      const status = summary.status || "";
      const resultAvailable = Boolean(summary.result_available);

      return {
        completedAt: formatDate(summary.completed_at),
        createdAt: formatDate(summary.created_at),
        documentType: documentTypeLabel(summary.document_type),
        errorMessage: "",
        fields: [],
        fileName: `Задание ${shortId(summary.job_id)}`,
        id: summary.job_id,
        isHistorical: true,
        isLoadingResult: false,
        isProcessing: !resultAvailable && !isTerminalStatus(status),
        loadingMessage: "Ожидаем результат обработки.",
        markdown: "",
        markdownError: "",
        metadata: {
          confidence: "Не указана",
          fieldCount: summary.field_count || 0,
          language: "Не указан",
          tableCount: summary.table_count || 0,
          validationStatus: statusLabel(status, resultAvailable),
        },
        previewKind: "placeholder",
        previewUrl: "",
        rawText: "",
        resultAvailable,
        status,
        statusLabel: statusLabel(status, resultAvailable),
        tables: [],
        warningCount: summary.warning_count || 0,
        warnings: [],
      };
    }

    function createUploadJob(payload) {
      const status = payload.submit.status || "CREATED";
      const resultAvailable = Boolean(payload.submit.result_available);

      return {
        completedAt: "",
        createdAt: "Текущая сессия",
        documentType: "Загруженный документ",
        errorMessage: "",
        fields: [],
        fileName: payload.upload.fileName,
        id: payload.submit.job_id,
        isHistorical: false,
        isLoadingResult: resultAvailable,
        isProcessing: !resultAvailable,
        loadingMessage: resultAvailable ? "Готовим отображение результата." : "Ожидаем результат обработки.",
        markdown: "",
        markdownError: "",
        metadata: {
          confidence: "Не указана",
          fieldCount: 0,
          fileSize: payload.upload.fileSize,
          language: "Не указан",
          mimeType: payload.upload.mimeType,
          sourceFile: payload.upload.fileName,
          tableCount: 0,
          validationStatus: statusLabel(status, resultAvailable),
        },
        ownsPreviewUrl: payload.upload.ownsPreviewUrl,
        previewKind: payload.upload.previewKind,
        previewUrl: payload.upload.previewUrl,
        rawText: "",
        resultAvailable,
        status,
        statusLabel: statusLabel(status, resultAvailable),
        tables: [],
        warningCount: 0,
        warnings: [],
      };
    }

    function beginSelection() {
      selectionToken += 1;
      if (pollingController) {
        pollingController.abort();
      }
      pollingController = new AbortController();
      return selectionToken;
    }

    function isCurrentToken(token) {
      return token === selectionToken && pollingController && !pollingController.signal.aborted;
    }

    function mergeJob(jobId, patch) {
      jobs = jobs.map((job) => (job.id === jobId ? { ...job, ...patch } : job));
      if (activeJob && activeJob.id === jobId) {
        activeJob = { ...activeJob, ...patch };
      }
    }

    function applyStatus(jobId, statusResponse) {
      if (!statusResponse) {
        return;
      }

      const status = statusResponse.status || "";
      const resultAvailable = Boolean(statusResponse.result_available);
      mergeJob(jobId, {
        completedAt: formatDate(statusResponse.completed_at),
        errorMessage: isFailedStatus(status) ? statusResponse.error_message || "Задание завершилось ошибкой." : "",
        isProcessing: !resultAvailable && !isTerminalStatus(status),
        loadingMessage: resultAvailable ? "Готовим отображение результата." : "Ожидаем результат обработки.",
        resultAvailable,
        status,
        statusLabel: statusLabel(status, resultAvailable),
      });
    }

    function applyDetail(jobId, detailResponse) {
      const summary = detailResponse.summary || {};
      const statusView = detailResponse.status || {};
      const metadata = detailResponse.metadata || {};
      const fileName = fileNameFromArtifacts(detailResponse.input_artifacts);
      const sourceSize = Number(metadata.source_image_size_bytes);

      applyStatus(jobId, statusView);
      mergeJob(jobId, {
        documentType: documentTypeLabel(summary.document_type),
        fileName: fileName || (activeJob && activeJob.fileName) || `Задание ${shortId(jobId)}`,
        metadata: {
          ...((activeJob && activeJob.metadata) || {}),
          fileSize: formatFileSize(sourceSize) || ((activeJob && activeJob.metadata.fileSize) || ""),
          fieldCount: summary.field_count || 0,
          tableCount: summary.table_count || 0,
          validationStatus: validationLabel(
            statusView.validation_status,
            statusView.status,
            statusView.result_available,
          ),
        },
        warningCount: summary.warning_count || 0,
      });
    }

    function applyResult(jobId, resultResponse, markdownResponse) {
      const result = isObject(resultResponse.result) ? resultResponse.result : {};
      const document = isObject(result.document) ? result.document : {};
      const rawText = isObject(result.raw_text) ? result.raw_text : {};
      const fields = normalizeFields(result);
      const tables = normalizeTables(result);
      const warnings = normalizeWarnings(result);
      const markdown =
        markdownResponse && markdownResponse.result_available && typeof markdownResponse.markdown === "string"
          ? markdownResponse.markdown
          : "";

      mergeJob(jobId, {
        documentType: documentTypeLabel(document.detected_type || (activeJob && activeJob.documentType)),
        errorMessage: "",
        fields,
        isLoadingResult: false,
        isProcessing: false,
        markdown,
        markdownError: markdown ? "" : "Markdown пока недоступен.",
        metadata: {
          ...((activeJob && activeJob.metadata) || {}),
          confidence: formatConfidence(document.detected_type_confidence || rawText.confidence),
          fieldCount: fields.length,
          language: languageLabel(document.language),
          tableCount: tables.length,
        },
        rawText: textOrFallback(rawText.text, ""),
        resultAvailable: Boolean(resultResponse.result_available),
        status: "RESULT_READY",
        statusLabel: "Готово",
        tables,
        warningCount: warnings.length,
        warnings,
      });
    }

    function renderPreview() {
      if (!activeJob) {
        previewPanel.classList.add("is-hidden");
        previewStatus.className = "status-pill status-pill-neutral";
        previewStatus.textContent = "Не выбран";
        preview.innerHTML = "<span>Выберите файл для просмотра</span>";
        meta.replaceChildren();
        return;
      }

      previewPanel.classList.remove("is-hidden");
      previewStatus.className = `status-pill ${window.Stage19AJobs.getStatusClass(activeJob.status)}`;
      previewStatus.textContent = activeJob.statusLabel;

      if (activeJob.previewUrl && activeJob.previewKind === "image") {
        const image = document.createElement("img");
        image.src = activeJob.previewUrl;
        image.alt = `Локальный предпросмотр файла ${activeJob.fileName}`;
        preview.replaceChildren(image);
      } else {
        preview.innerHTML = `
          <div class="preview-placeholder">
            <strong>${escapeHtml(activeJob.documentType)}</strong>
            <span>${escapeHtml(activeJob.fileName)}</span>
            <small>Исторический предпросмотр будет доступен после безопасного viewer/download слоя.</small>
          </div>
        `;
      }

      const rows = [
        ["Файл", activeJob.fileName],
        ["Тип", activeJob.documentType],
        ["Создан", activeJob.createdAt],
        ["Статус", activeJob.statusLabel],
        ["Размер", activeJob.metadata.fileSize],
      ].filter((row) => row[1]);

      meta.innerHTML = rows
        .map(
          ([label, value]) => `
            <div class="meta-row"><span>${escapeHtml(label)}</span><strong>${escapeHtml(value)}</strong></div>
          `,
        )
        .join("");
    }

    function renderSummary() {
      const metadata = activeJob.metadata;

      return `
        <div class="summary-card-grid">
          <div class="summary-card"><span>Тип документа</span><strong>${escapeHtml(activeJob.documentType)}</strong></div>
          <div class="summary-card"><span>Язык</span><strong>${escapeHtml(metadata.language)}</strong></div>
          <div class="summary-card"><span>Проверка</span><strong>${escapeHtml(metadata.validationStatus)}</strong></div>
          <div class="summary-card"><span>Поля вне таблиц</span><strong>${escapeHtml(metadata.fieldCount)}</strong></div>
          <div class="summary-card"><span>Таблицы</span><strong>${escapeHtml(metadata.tableCount)}</strong></div>
          <div class="summary-card"><span>Предупреждения</span><strong>${escapeHtml(activeJob.warningCount)}</strong></div>
        </div>
      `;
    }

    function renderWarnings() {
      if (!activeJob.warnings.length) {
        return "<div class=\"empty-state\"><strong>Предупреждений нет</strong></div>";
      }

      return `
        <div class="warning-list">
          ${activeJob.warnings
            .map(
              (warning) => `
                <article class="warning-card">
                  <strong>${escapeHtml(warning.severity)} · ${escapeHtml(warning.code)}</strong>
                  <p><b>${escapeHtml(warning.target)}:</b> ${escapeHtml(warning.message)}</p>
                </article>
              `,
            )
            .join("")}
        </div>
      `;
    }

    function renderActiveTab() {
      tabButtons.forEach((button) => {
        const isActive = button.dataset.resultTab === activeTab;
        button.classList.toggle("is-active", isActive);
        button.setAttribute("aria-selected", String(isActive));
      });

      copyButton.disabled = !activeJob || !activeJob.markdown;
      downloadButton.disabled = !activeJob || !activeJob.markdown;

      if (!activeJob) {
        tabPanel.replaceChildren();
        return;
      }

      if (activeJob.isProcessing || activeJob.isLoadingResult) {
        tabPanel.innerHTML = renderProcessingState(activeJob);
        return;
      }

      if (activeJob.errorMessage) {
        tabPanel.innerHTML = renderErrorState(activeJob.errorMessage);
        return;
      }

      if (!activeJob.resultAvailable) {
        tabPanel.innerHTML = "<div class=\"empty-state\"><strong>Результат пока недоступен</strong></div>";
        return;
      }

      if (activeTab === "warnings") {
        tabPanel.innerHTML = renderWarnings();
      } else if (activeTab === "fields") {
        tabPanel.innerHTML = renderFields(activeJob.fields);
      } else if (activeTab === "tables") {
        tabPanel.innerHTML = renderTables(activeJob.tables);
      } else if (activeTab === "raw") {
        tabPanel.innerHTML = `<pre class="raw-text-block">${escapeHtml(activeJob.rawText)}</pre>`;
      } else if (activeTab === "markdown") {
        tabPanel.innerHTML = activeJob.markdown
          ? renderMarkdown(activeJob.markdown)
          : renderErrorState(activeJob.markdownError);
      } else {
        tabPanel.innerHTML = renderSummary();
      }
    }

    function renderJobList() {
      if (jobsState === "loading") {
        jobList.innerHTML = `
          <div class="loading-state">
            <span class="loading-spinner" aria-hidden="true"></span>
            <strong>Загружаем файлы</strong>
          </div>
        `;
        return;
      }

      if (jobsState === "error") {
        jobList.innerHTML = renderErrorState(jobListError);
        return;
      }

      window.Stage19AJobs.renderJobList(jobList, jobs, activeJob && activeJob.id, selectJob);
    }

    function renderWorkspace() {
      renderPreview();
      renderJobList();
      workspaceGrid.classList.toggle("is-empty", !activeJob);

      if (!activeJob) {
        resultTitle.textContent = "Выберите файл";
        empty.classList.remove("is-hidden");
        content.classList.add("is-hidden");
        return;
      }

      resultTitle.textContent = `Результат · ${activeJob.fileName}`;
      empty.classList.add("is-hidden");
      content.classList.remove("is-hidden");
      renderActiveTab();
    }

    async function loadJobPayload(jobId, token, signal, detailResponse) {
      if (!isCurrentToken(token)) {
        return;
      }

      mergeJob(jobId, {
        isLoadingResult: true,
        isProcessing: false,
        loadingMessage: "Готовим отображение результата.",
      });
      renderWorkspace();

      const detail = detailResponse || (await apiClient.getJobDetail(jobId, { signal }));
      if (!isCurrentToken(token)) {
        return;
      }

      applyDetail(jobId, detail);

      const resultResponse = await apiClient.getJobResult(jobId, { signal });
      if (!isCurrentToken(token)) {
        return;
      }

      if (!resultResponse.result_available) {
        mergeJob(jobId, {
          errorMessage:
            resultResponse.error && resultResponse.error.error_message
              ? apiClient.messageForError(resultResponse.error.error_type, resultResponse.error.error_message)
              : "Результат пока недоступен.",
          isLoadingResult: false,
          isProcessing: false,
          resultAvailable: false,
        });
        renderWorkspace();
        return;
      }

      let markdownResponse = null;
      try {
        markdownResponse = await apiClient.getJobMarkdown(jobId, { signal });
      } catch (error) {
        markdownResponse = {
          markdown: "",
          result_available: false,
        };
      }

      if (!isCurrentToken(token)) {
        return;
      }

      applyResult(jobId, resultResponse, markdownResponse);
      renderWorkspace();
    }

    async function pollJob(jobId, token, signal) {
      const startedAt = Date.now();

      while (isCurrentToken(token)) {
        const statusResponse = await apiClient.getJobStatus(jobId, { signal });
        if (!isCurrentToken(token)) {
          return;
        }

        applyStatus(jobId, statusResponse);
        renderWorkspace();

        if (statusResponse.result_available || normalizeStatus(statusResponse.status) === "RESULT_READY") {
          await loadJobPayload(jobId, token, signal);
          return;
        }

        if (isFailedStatus(statusResponse.status)) {
          mergeJob(jobId, {
            errorMessage: statusResponse.error_message || "Задание завершилось ошибкой.",
            isLoadingResult: false,
            isProcessing: false,
          });
          renderWorkspace();
          return;
        }

        if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
          mergeJob(jobId, {
            errorMessage: "Ожидание результата заняло слишком много времени.",
            isLoadingResult: false,
            isProcessing: false,
          });
          renderWorkspace();
          return;
        }

        await delay(POLL_INTERVAL_MS, signal);
      }
    }

    async function loadSelectedJob(job) {
      activeJob = { ...job, isLoadingResult: true, loadingMessage: "Загружаем данные задания." };
      activeTab = "summary";
      renderWorkspace();

      const token = beginSelection();
      const signal = pollingController.signal;

      try {
        const detail = await apiClient.getJobDetail(job.id, { signal });
        if (!isCurrentToken(token)) {
          return;
        }

        applyDetail(job.id, detail);
        const statusView = detail.status || {};

        if (statusView.result_available || normalizeStatus(statusView.status) === "RESULT_READY") {
          await loadJobPayload(job.id, token, signal, detail);
        } else if (isFailedStatus(statusView.status)) {
          mergeJob(job.id, {
            errorMessage: statusView.error_message || "Задание завершилось ошибкой.",
            isLoadingResult: false,
            isProcessing: false,
          });
          renderWorkspace();
        } else {
          mergeJob(job.id, {
            isLoadingResult: false,
            isProcessing: true,
            loadingMessage: "Ожидаем результат обработки.",
          });
          renderWorkspace();
          await pollJob(job.id, token, signal);
        }
      } catch (error) {
        if (error && (error.errorType === "request_cancelled" || error.name === "AbortError")) {
          return;
        }

        mergeJob(job.id, {
          errorMessage: error && error.message ? error.message : "Не удалось загрузить данные задания.",
          isLoadingResult: false,
          isProcessing: false,
        });
        renderWorkspace();
      }
    }

    function selectJob(job) {
      loadSelectedJob(job).catch(() => {
        mergeJob(job.id, {
          errorMessage: "Не удалось загрузить данные задания.",
          isLoadingResult: false,
          isProcessing: false,
        });
        renderWorkspace();
      });
    }

    async function loadJobs(options) {
      if (historyController) {
        historyController.abort();
      }

      historyController = new AbortController();
      jobsState = "loading";
      jobListError = "";
      renderWorkspace();

      try {
        const history = await apiClient.listJobs({ signal: historyController.signal });
        const loadedJobs = asArray(history.jobs).map(createHistoryJob);
        const preservedActive = activeJob;
        jobs = loadedJobs.map((job) => {
          if (preservedActive && preservedActive.id === job.id) {
            return { ...job, ...preservedActive };
          }

          return job;
        });

        if (options && options.preserveActive && preservedActive && !jobs.some((job) => job.id === preservedActive.id)) {
          jobs = [preservedActive, ...jobs];
        }

        jobsState = "loaded";
      } catch (error) {
        if (error && (error.errorType === "request_cancelled" || error.name === "AbortError")) {
          return;
        }

        jobsState = "error";
        jobListError = error && error.message ? error.message : "Не удалось загрузить список файлов.";
      }

      renderWorkspace();
    }

    function openWorkspace(job) {
      activeJob = job || null;
      activeTab = "summary";
      overlay.classList.remove("is-hidden");
      backdrop.classList.remove("is-hidden");
      document.body.classList.add("has-modal");
      renderWorkspace();
      closeButton.focus();
    }

    function openWithJob(payload) {
      const job = createUploadJob(payload);
      jobs = [job, ...jobs.filter((item) => item.id !== job.id)];
      jobsState = "loaded";
      openWorkspace(job);

      const token = beginSelection();
      pollJob(job.id, token, pollingController.signal).catch((error) => {
        if (error && (error.errorType === "request_cancelled" || error.name === "AbortError")) {
          return;
        }

        mergeJob(job.id, {
          errorMessage: error && error.message ? error.message : "Не удалось дождаться результата.",
          isLoadingResult: false,
          isProcessing: false,
        });
        renderWorkspace();
      });
      loadJobs({ preserveActive: true }).catch(() => undefined);
    }

    function openWithoutSelection() {
      activeJob = null;
      openWorkspace(null);
      loadJobs({ preserveActive: false }).catch(() => undefined);
    }

    function closeWorkspace() {
      if (pollingController) {
        pollingController.abort();
      }

      overlay.classList.add("is-hidden");
      backdrop.classList.add("is-hidden");
      document.body.classList.remove("has-modal");
      openJobsButton.focus();
    }

    function copyWithTextArea(markdown) {
      const textArea = document.createElement("textarea");
      textArea.value = markdown;
      document.body.appendChild(textArea);
      textArea.select();
      document.execCommand("copy");
      textArea.remove();
    }

    async function copyMarkdown() {
      if (!activeJob || !activeJob.markdown) {
        showToast("Markdown пока недоступен");
        return;
      }

      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(activeJob.markdown);
        } else {
          copyWithTextArea(activeJob.markdown);
        }
      } catch (error) {
        copyWithTextArea(activeJob.markdown);
      }

      showToast("Markdown скопирован");
    }

    function downloadMarkdown() {
      if (!activeJob || !activeJob.markdown) {
        showToast("Markdown пока недоступен");
        return;
      }

      const blob = new Blob([activeJob.markdown], { type: "text/markdown;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${activeJob.id}.md`;
      document.body.appendChild(link);
      link.click();
      URL.revokeObjectURL(link.href);
      link.remove();
      showToast("Markdown скачан");
    }

    openJobsButton.addEventListener("click", openWithoutSelection);
    closeButton.addEventListener("click", closeWorkspace);
    backdrop.addEventListener("click", closeWorkspace);
    copyButton.addEventListener("click", () => {
      copyMarkdown().catch(() => showToast("Не удалось скопировать Markdown"));
    });
    downloadButton.addEventListener("click", downloadMarkdown);

    tabButtons.forEach((button) => {
      button.addEventListener("click", () => {
        activeTab = button.dataset.resultTab;
        renderActiveTab();
      });
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !overlay.classList.contains("is-hidden")) {
        closeWorkspace();
      }
    });

    return {
      close: closeWorkspace,
      open: openWorkspace,
      openWithJob,
    };
  }

  window.Stage19AWorkspace = {
    init: initWorkspace,
  };
})();
