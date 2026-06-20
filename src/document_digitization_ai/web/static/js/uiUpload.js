(function () {
  function formatFileSize(size) {
    if (!Number.isFinite(size) || size <= 0) {
      return "0 KB";
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

  function createJobForFile(file, sampleJob, previewUrl) {
    return {
      ...sampleJob,
      id: "job-demo-current-upload",
      fileName: file.name,
      createdAt: "Текущая сессия",
      status: "needs_review",
      statusLabel: "Требует проверки",
      previewKind: file.type.startsWith("image/") ? "image" : "placeholder",
      previewUrl: file.type.startsWith("image/") ? previewUrl : "",
      warningCount: sampleJob.warningCount,
      metadata: {
        ...sampleJob.metadata,
        sourceFile: file.name,
        fileSize: formatFileSize(file.size),
      },
    };
  }

  function initUpload(options) {
    const data = window.Stage19ASampleData;
    const dropzone = document.getElementById("dropzone");
    const fileInput = document.getElementById("fileInput");
    const chooseFileButton = document.getElementById("chooseFileButton");
    const selectedFilePanel = document.getElementById("selectedFilePanel");
    const selectedFileName = document.getElementById("selectedFileName");
    const selectedFileSize = document.getElementById("selectedFileSize");
    const previewFrame = document.getElementById("previewFrame");
    const clearFileButton = document.getElementById("clearFileButton");
    const settingsPanel = document.getElementById("settingsPanel");
    const analyzeButton = document.getElementById("analyzeButton");
    const uploadNote = document.getElementById("uploadNote");
    let selectedFile = null;
    let previewUrl = null;

    function resetPreview() {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }

      previewFrame.innerHTML = "<span>Предпросмотр</span>";
    }

    function clearSelectedFile() {
      selectedFile = null;
      fileInput.value = "";
      selectedFilePanel.classList.add("is-hidden");
      settingsPanel.classList.add("is-hidden");
      analyzeButton.disabled = true;
      analyzeButton.textContent = "Анализировать";
      uploadNote.textContent = "Выберите файл для просмотра результата.";
      resetPreview();
    }

    function setSelectedFile(file) {
      if (!file) {
        clearSelectedFile();
        return;
      }

      selectedFile = file;
      selectedFileName.textContent = file.name;
      selectedFileSize.textContent = formatFileSize(file.size);
      selectedFilePanel.classList.remove("is-hidden");
      settingsPanel.classList.remove("is-hidden");
      analyzeButton.disabled = false;
      uploadNote.textContent = "Файл выбран. Можно запускать анализ.";

      resetPreview();

      if (file.type.startsWith("image/")) {
        previewUrl = URL.createObjectURL(file);
        const image = document.createElement("img");
        image.src = previewUrl;
        image.alt = "Локальный предпросмотр выбранного изображения";
        previewFrame.replaceChildren(image);
      }
    }

    function openFileDialog() {
      fileInput.click();
    }

    function handleDrop(event) {
      event.preventDefault();
      dropzone.classList.remove("is-drag-over");
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      setSelectedFile(file);
    }

    function runAnalyzeSimulation() {
      if (!selectedFile || analyzeButton.disabled) {
        return;
      }

      analyzeButton.disabled = true;
      analyzeButton.textContent = "Анализируем...";
      uploadNote.textContent = "Готовим демо-результат.";

      window.setTimeout(() => {
        analyzeButton.disabled = false;
        analyzeButton.textContent = "Анализировать";
        uploadNote.textContent = "Демо-результат открыт в рабочей области.";
        options.onAnalyze(createJobForFile(selectedFile, data.currentJob, previewUrl));
      }, 850);
    }

    chooseFileButton.addEventListener("click", (event) => {
      event.stopPropagation();
      openFileDialog();
    });
    dropzone.addEventListener("click", openFileDialog);
    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        openFileDialog();
      }
    });
    fileInput.addEventListener("change", () => setSelectedFile(fileInput.files[0]));
    clearFileButton.addEventListener("click", clearSelectedFile);
    analyzeButton.addEventListener("click", runAnalyzeSimulation);

    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dropzone.classList.add("is-drag-over");
      });
    });

    ["dragleave", "dragend"].forEach((eventName) => {
      dropzone.addEventListener(eventName, () => {
        dropzone.classList.remove("is-drag-over");
      });
    });

    dropzone.addEventListener("drop", handleDrop);

    return {
      clearSelectedFile,
    };
  }

  window.Stage19AUpload = {
    init: initUpload,
  };
})();
