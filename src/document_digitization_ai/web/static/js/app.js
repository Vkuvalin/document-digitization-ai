(function () {
  function initInfoModal() {
    const data = window.Stage19ASampleData;
    const modal = document.getElementById("infoModal");
    const backdrop = document.getElementById("infoBackdrop");
    const title = document.getElementById("infoTitle");
    const body = document.getElementById("infoBody");
    const closeButton = document.getElementById("closeInfoButton");
    const titles = {
      what: "Что это",
      pricing: "Цены",
      help: "Помощь",
      privacy: "Конфиденциальность",
      terms: "Условия",
      login: "Войти",
    };

    function open(panelName) {
      title.textContent = titles[panelName] || "Информация";
      body.textContent = data.infoPanels[panelName] || "Информация появится позже.";
      modal.classList.remove("is-hidden");
      backdrop.classList.remove("is-hidden");
      document.body.classList.add("has-modal");
      closeButton.focus();
    }

    function close() {
      modal.classList.add("is-hidden");
      backdrop.classList.add("is-hidden");
      document.body.classList.remove("has-modal");
    }

    document.querySelectorAll("[data-info-panel]").forEach((button) => {
      button.addEventListener("click", () => open(button.dataset.infoPanel));
    });

    document.getElementById("loginButton").addEventListener("click", () => open("login"));
    closeButton.addEventListener("click", close);
    backdrop.addEventListener("click", close);

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !modal.classList.contains("is-hidden")) {
        close();
      }
    });
  }

  function initApp() {
    const workspace = window.Stage19AWorkspace.init();
    window.Stage19AUpload.init({
      onAnalyze: workspace.openWithJob,
    });
    initInfoModal();

    document.getElementById("brandButton").addEventListener("click", () => {
      window.scrollTo({ top: 0, behavior: "smooth" });
    });

    document.getElementById("currentYear").textContent = String(new Date().getFullYear());
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
  } else {
    initApp();
  }
})();
