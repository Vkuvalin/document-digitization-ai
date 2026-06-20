(function () {
  function getStatusClass(status) {
    if (status === "complete") {
      return "status-pill-success";
    }

    if (status === "failed") {
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

  function renderJobList(container, jobs, activeJobId, onSelect) {
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
      const button = document.createElement("button");
      button.className = "job-card";
      button.type = "button";
      button.classList.toggle("is-selected", job.id === activeJobId);
      button.setAttribute("aria-pressed", String(job.id === activeJobId));

      const header = document.createElement("div");
      header.className = "job-card-header";

      const titleBlock = document.createElement("div");
      titleBlock.appendChild(createTextElement("strong", "", job.fileName));
      titleBlock.appendChild(createTextElement("small", "", `${job.documentType} · ${job.createdAt}`));

      const status = createTextElement("span", `status-pill ${getStatusClass(job.status)}`, job.statusLabel);
      header.append(titleBlock, status);

      const meta = document.createElement("div");
      meta.className = "job-meta-row";
      meta.appendChild(createTextElement("span", "", formatWarningCount(job.warningCount)));

      button.append(header, meta);
      button.addEventListener("click", () => onSelect(job));
      container.appendChild(button);
    });
  }

  window.Stage19AJobs = {
    formatWarningCount,
    getStatusClass,
    renderJobList,
  };
})();
