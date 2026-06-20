(function () {
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
    const lines = markdown.split(/\r?\n/);
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

    return `<article class="markdown-preview">${output.join("")}</article>`;
  }

  function renderFields(fields) {
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
    return tables
      .map((table) => {
        const headers = table.columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("");
        const rows = table.rows
          .map((row) => `<tr>${row.map((cell) => `<td>${escapeHtml(cell)}</td>`).join("")}</tr>`)
          .join("");

        return `
          <h3>${escapeHtml(table.name)}</h3>
          <div class="table-wrap">
            <table>
              <thead><tr>${headers}</tr></thead>
              <tbody>${rows}</tbody>
            </table>
          </div>
        `;
      })
      .join("");
  }

  function initWorkspace() {
    const data = window.Stage19ASampleData;
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
    let jobs = [...data.jobs];
    let activeJob = null;
    let activeTab = "summary";
    let toastTimer = null;

    function showToast(message) {
      window.clearTimeout(toastTimer);
      toast.textContent = message;
      toast.classList.remove("is-hidden");
      toastTimer = window.setTimeout(() => {
        toast.classList.add("is-hidden");
      }, 2200);
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
        image.alt = `Предпросмотр файла ${activeJob.fileName}`;
        preview.replaceChildren(image);
      } else {
        preview.innerHTML = `
          <div class="preview-placeholder">
            <strong>${escapeHtml(activeJob.documentType)}</strong>
            <span>${escapeHtml(activeJob.fileName)}</span>
          </div>
        `;
      }

      meta.innerHTML = `
        <div class="meta-row"><span>Файл</span><strong>${escapeHtml(activeJob.fileName)}</strong></div>
        <div class="meta-row"><span>Тип</span><strong>${escapeHtml(activeJob.documentType)}</strong></div>
        <div class="meta-row"><span>Создан</span><strong>${escapeHtml(activeJob.createdAt)}</strong></div>
        <div class="meta-row"><span>Уверенность</span><strong>${escapeHtml(activeJob.metadata.confidence)}</strong></div>
      `;
    }

    function renderSummary() {
      const metadata = activeJob.metadata;

      return `
        <div class="summary-card-grid">
          <div class="summary-card"><span>Тип документа</span><strong>${escapeHtml(activeJob.documentType)}</strong></div>
          <div class="summary-card"><span>Язык</span><strong>${escapeHtml(metadata.language)}</strong></div>
          <div class="summary-card"><span>Проверка</span><strong>${escapeHtml(metadata.validationStatus)}</strong></div>
          <div class="summary-card"><span>Поля</span><strong>${escapeHtml(metadata.fieldCount)}</strong></div>
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

      if (!activeJob) {
        tabPanel.replaceChildren();
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
        tabPanel.innerHTML = renderMarkdown(activeJob.markdown);
      } else {
        tabPanel.innerHTML = renderSummary();
      }
    }

    function renderJobList() {
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

    function selectJob(job) {
      activeJob = job;
      activeTab = "summary";
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

    function openWithJob(job) {
      jobs = [job, ...data.jobs.filter((item) => item.id !== job.id)];
      openWorkspace(job);
    }

    function openWithoutSelection() {
      jobs = [...data.jobs];
      openWorkspace(null);
    }

    function closeWorkspace() {
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
      if (!activeJob) {
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
      if (!activeJob) {
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
      open: openWorkspace,
      openWithJob,
      close: closeWorkspace,
    };
  }

  window.Stage19AWorkspace = {
    init: initWorkspace,
  };
})();
