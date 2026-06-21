(function () {
  const DEFAULT_TIMEOUT_MS = 30000;
  const UPLOAD_TIMEOUT_MS = 120000;

  const ERROR_MESSAGES = {
    artifact_access_denied: "Артефакт недоступен для просмотра.",
    artifact_not_found: "Артефакт не найден.",
    artifact_write_failed: "Не удалось подготовить файл результата.",
    internal_error: "Сервер не смог обработать запрос.",
    invalid_input: "Проверьте выбранный файл или параметры запроса.",
    job_failed: "Обработка документа завершилась ошибкой.",
    job_not_found: "Задание не найдено.",
    malformed_result_payload: "Результат сохранён в неожиданном формате.",
    network_timeout: "Сервер не ответил вовремя.",
    request_cancelled: "Запрос отменён.",
    result_unavailable: "Результат пока недоступен.",
    too_large_upload: "Файл больше допустимого лимита.",
    unsupported_file: "Формат файла не поддерживается.",
    validation_error: "Сервер вернул неожиданный ответ.",
  };

  class ApiClientError extends Error {
    constructor(message, options) {
      super(message);
      this.name = "ApiClientError";
      this.status = options && options.status ? options.status : null;
      this.errorType = options && options.errorType ? options.errorType : "internal_error";
      this.payload = options && options.payload ? options.payload : null;
    }
  }

  function endpoint(path) {
    return path.startsWith("/") ? path : `/${path}`;
  }

  function messageForError(errorType, fallbackMessage) {
    if (errorType && ERROR_MESSAGES[errorType]) {
      return ERROR_MESSAGES[errorType];
    }

    if (fallbackMessage && errorType !== "internal_error") {
      return fallbackMessage;
    }

    return "Не удалось выполнить запрос к API.";
  }

  function errorTypeForStatus(status) {
    if (status === 413) {
      return "too_large_upload";
    }

    if (status === 415) {
      return "unsupported_file";
    }

    if (status === 404) {
      return "job_not_found";
    }

    if (status === 422 || status === 400) {
      return "invalid_input";
    }

    return "internal_error";
  }

  async function parseResponsePayload(response) {
    const contentType = response.headers.get("content-type") || "";

    if (!contentType.includes("application/json")) {
      return null;
    }

    try {
      return await response.json();
    } catch (error) {
      return null;
    }
  }

  function throwFromPayload(response, payload) {
    const errorType =
      payload && typeof payload.error_type === "string"
        ? payload.error_type
        : errorTypeForStatus(response.status);
    const fallbackMessage =
      payload && typeof payload.error_message === "string" ? payload.error_message : "";

    throw new ApiClientError(messageForError(errorType, fallbackMessage), {
      status: response.status,
      errorType,
      payload,
    });
  }

  async function requestJson(path, options) {
    const settings = options || {};
    const controller = new AbortController();
    let timedOut = false;
    let externalAbortHandler = null;
    const timeoutId = window.setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, settings.timeoutMs || DEFAULT_TIMEOUT_MS);

    if (settings.signal) {
      if (settings.signal.aborted) {
        window.clearTimeout(timeoutId);
        throw new ApiClientError(ERROR_MESSAGES.request_cancelled, {
          errorType: "request_cancelled",
        });
      }

      externalAbortHandler = () => controller.abort();
      settings.signal.addEventListener("abort", externalAbortHandler, { once: true });
    }

    try {
      const response = await fetch(endpoint(path), {
        method: settings.method || "GET",
        body: settings.body,
        signal: controller.signal,
        headers: settings.headers,
      });
      const payload = await parseResponsePayload(response);

      if (!response.ok) {
        throwFromPayload(response, payload);
      }

      if (payload === null || typeof payload !== "object") {
        throw new ApiClientError(ERROR_MESSAGES.validation_error, {
          status: response.status,
          errorType: "validation_error",
          payload,
        });
      }

      return payload;
    } catch (error) {
      if (error instanceof ApiClientError) {
        throw error;
      }

      if (error && error.name === "AbortError") {
        const errorType = timedOut ? "network_timeout" : "request_cancelled";
        throw new ApiClientError(ERROR_MESSAGES[errorType], { errorType });
      }

      throw new ApiClientError("API недоступен. Проверьте, что сервер запущен.", {
        errorType: "network_unavailable",
      });
    } finally {
      window.clearTimeout(timeoutId);
      if (externalAbortHandler && settings.signal) {
        settings.signal.removeEventListener("abort", externalAbortHandler);
      }
    }
  }

  function uploadDocument(file, options) {
    const form = new FormData();
    form.append("file", file, file.name);
    return requestJson("/documents", {
      method: "POST",
      body: form,
      timeoutMs: UPLOAD_TIMEOUT_MS,
      signal: options && options.signal,
    });
  }

  function listJobs(options) {
    return requestJson("/jobs?limit=50&offset=0", {
      signal: options && options.signal,
    });
  }

  function getJobDetail(jobId, options) {
    return requestJson(`/jobs/${encodeURIComponent(jobId)}`, {
      signal: options && options.signal,
    });
  }

  function getJobStatus(jobId, options) {
    return requestJson(`/jobs/${encodeURIComponent(jobId)}/status`, {
      signal: options && options.signal,
    });
  }

  function getJobResult(jobId, options) {
    return requestJson(`/jobs/${encodeURIComponent(jobId)}/result`, {
      signal: options && options.signal,
    });
  }

  function getJobMarkdown(jobId, options) {
    return requestJson(`/jobs/${encodeURIComponent(jobId)}/markdown`, {
      signal: options && options.signal,
    });
  }

  window.Stage19BApiClient = {
    ApiClientError,
    getJobDetail,
    getJobMarkdown,
    getJobResult,
    getJobStatus,
    listJobs,
    messageForError,
    uploadDocument,
  };
})();
