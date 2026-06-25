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

  function setButtonBusy(button, text) {
    button.disabled = true;
    button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span>${text}`;
  }

  function setButtonReady(button) {
    button.disabled = false;
    button.textContent = "Анализировать";
  }

  function initUpload(options) {
    const apiClient = options.apiClient;
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
    let isSubmitting = false;

    function resetPreview() {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
        previewUrl = null;
      }

      previewFrame.innerHTML = "<span>Предпросмотр</span>";
    }

    function clearSelectedFile(options) {
      const force = Boolean(options && options.force);
      if (isSubmitting && !force) {
        return;
      }

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
      if (isSubmitting) {
        return;
      }

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
      analyzeButton.textContent = "Анализировать";
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
      if (!isSubmitting) {
        fileInput.click();
      }
    }

    function handleDrop(event) {
      event.preventDefault();
      dropzone.classList.remove("is-drag-over");
      const file = event.dataTransfer.files && event.dataTransfer.files[0];
      setSelectedFile(file);
    }

    function createUploadContext(file) {
      const workspacePreviewUrl = file.type.startsWith("image/") ? URL.createObjectURL(file) : "";

      return {
        fileName: file.name,
        fileSize: formatFileSize(file.size),
        mimeType: file.type || "application/octet-stream",
        previewKind: workspacePreviewUrl ? "image" : "placeholder",
        previewUrl: workspacePreviewUrl,
        ownsPreviewUrl: Boolean(workspacePreviewUrl),
      };
    }

    async function runAnalyze() {
      if (!selectedFile || isSubmitting) {
        return;
      }

      isSubmitting = true;
      setButtonBusy(analyzeButton, "Загружаем");
      uploadNote.textContent = "Загружаем файл и запускаем анализ.";

      const uploadContext = createUploadContext(selectedFile);

      try {
        const submitResponse = await apiClient.uploadDocument(selectedFile);

        if (!submitResponse.accepted || !submitResponse.job_id) {
          const apiError = submitResponse.error || {};
          throw new apiClient.ApiClientError(
            apiClient.messageForError(apiError.error_type, apiError.error_message),
            {
              errorType: apiError.error_type || "validation_error",
              payload: submitResponse,
            },
          );
        }

        uploadNote.textContent = "Файл принят. Ожидаем результат в рабочей области.";
        options.onAnalyze({
          submit: submitResponse,
          upload: uploadContext,
        });
        clearSelectedFile({ force: true });
      } catch (error) {
        if (uploadContext.previewUrl) {
          URL.revokeObjectURL(uploadContext.previewUrl);
        }

        uploadNote.textContent =
          error && error.message ? error.message : "Не удалось отправить файл на анализ.";
      } finally {
        isSubmitting = false;
        if (selectedFile) {
          setButtonReady(analyzeButton);
        } else {
          analyzeButton.disabled = true;
          analyzeButton.textContent = "Анализировать";
        }
      }
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
    analyzeButton.addEventListener("click", () => {
      runAnalyze().catch(() => {
        uploadNote.textContent = "Не удалось отправить файл на анализ.";
        setButtonReady(analyzeButton);
      });
    });

    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        if (!isSubmitting) {
          dropzone.classList.add("is-drag-over");
        }
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
