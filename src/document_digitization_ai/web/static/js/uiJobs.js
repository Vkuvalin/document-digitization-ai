(function () {
  function normalizeStatus(status) {
    return String(status || "").trim().toUpperCase();
  }

  function getStatusClass(status) {
    const normalized = normalizeStatus(status);

    if (
      normalized === "COMPLETE" ||
      normalized === "RESULT_READY" ||
      normalized === "VALIDATION_SUCCEEDED" ||
      normalized === "SUCCEEDED"
    ) {
      return "status-pill-success";
    }

    if (
      normalized === "FAILED" ||
      normalized === "CANCELLED" ||
      normalized === "ERROR" ||
      normalized === "VALIDATION_FAILED" ||
      normalized === "VALIDATION_ERROR"
    ) {
      return "status-pill-danger";
    }

    return "status-pill-warning";
  }

  function createTextElement(tagName, className, text) {
    const element = document.createElement(tagName);

    if (className) {
      element.className = className;
    }

    element.textContent = text;
    return element;
  }

  function formatWarningCount(count) {
    const absoluteCount = Math.abs(count);
    const lastTwoDigits = absoluteCount % 100;
    const lastDigit = absoluteCount % 10;

    if (lastTwoDigits >= 11 && lastTwoDigits <= 14) {
      return `${count} предупреждений`;
    }

    if (lastDigit === 1) {
      return `${count} предупреждение`;
    }

    if (lastDigit >= 2 && lastDigit <= 4) {
      return `${count} предупреждения`;
    }

    return `${count} предупреждений`;
  }

  function renderJobList(container, jobs, activeJobId, onSelect, onDelete) {
    container.replaceChildren();

    if (!jobs.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      const inner = document.createElement("div");
      inner.appendChild(createTextElement("strong", "", "Файлов пока нет"));
      inner.appendChild(createTextElement("p", "", "Здесь появятся последние обработанные документы."));
      empty.appendChild(inner);
      container.appendChild(empty);
      return;
    }

    jobs.forEach((job) => {
      const card = document.createElement("article");
      card.className = "job-card";
      card.tabIndex = 0;
      card.setAttribute("role", "button");
      card.classList.toggle("is-selected", job.id === activeJobId);
      card.setAttribute("aria-pressed", String(job.id === activeJobId));

      if (onDelete) {
        const deleteButton = document.createElement("button");
        deleteButton.className = "job-card-delete";
        deleteButton.type = "button";
        deleteButton.setAttribute("aria-label", `Удалить ${job.fileName || "файл"}`);
        deleteButton.textContent = "×";
        deleteButton.addEventListener("click", (event) => {
          event.stopPropagation();
          onDelete(job);
        });
        deleteButton.addEventListener("keydown", (event) => {
          event.stopPropagation();
        });
        card.appendChild(deleteButton);
      }

      const header = document.createElement("div");
      header.className = "job-card-header";

      const titleBlock = document.createElement("div");
      titleBlock.appendChild(createTextElement("strong", "", job.fileName || "Документ"));
      titleBlock.appendChild(
        createTextElement(
          "small",
          "",
          `${job.documentType || "Тип не определён"} · ${job.createdAt || "Дата неизвестна"}`,
        ),
      );

      const status = createTextElement(
        "span",
        `status-pill ${getStatusClass(job.status)}`,
        job.statusLabel || "Статус неизвестен",
      );
      header.append(titleBlock, status);

      const meta = document.createElement("div");
      meta.className = "job-meta-row";
      meta.appendChild(createTextElement("span", "", formatWarningCount(job.warningCount || 0)));

      card.append(header, meta);
      card.addEventListener("click", () => onSelect(job));
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onSelect(job);
        }
      });
      container.appendChild(card);
    });
  }

  window.Stage19AJobs = {
    formatWarningCount,
    getStatusClass,
    renderJobList,
  };
})();
