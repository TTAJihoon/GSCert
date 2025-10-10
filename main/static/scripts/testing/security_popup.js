(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  let modal, modalContent, closeBtn, backdrop, downloadBtn;

  function ensureDom() {
    modal        = modal        || document.getElementById("modal");
    modalContent = modalContent || document.getElementById("modalContent");
    closeBtn     = closeBtn     || document.getElementById("closeModal");
    downloadBtn  = downloadBtn  || document.getElementById("downloadHtml");
    backdrop     = backdrop     || document.querySelector("#modal .modal-backdrop");
  }

  function openModal() {
    ensureDom();
    if (!modal) return;
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
  }

  function closeModal() {
    ensureDom();
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    if (modalContent) modalContent.innerHTML = "";
    document.removeEventListener("keydown", escHandler);
  }

  function escHandler(e) {
    if (e.key === "Escape") closeModal();
  }

  // 모달 내 여백/스크롤 등 최소한의 오버라이드
  function injectModalOverrides() {
    const id = "invicti-modal-overrides";
    if (document.getElementById(id)) return;
    const style = document.createElement("style");
    style.id = id;
    style.textContent = `
      #modal .modal-shell { width: 80vw; height: 80vh; }
      #modal #modalContent { padding: 0.75rem; }
      #modal #modalContent .container-fluid { margin: 0 !important; padding: 0.5rem !important; }
      #modal #modalContent pre { white-space: pre-wrap; overflow: auto; }
    `;
    document.head.appendChild(style);
  }

  // 원본 리포트의 inline onclick 제거로 사라진 동작을 JS로 보완
  // (vuln-url 클릭 -> 직전 형제 input.vuln-input 체크 토글)
  function wireInvictiInteractions(root) {
    if (!root) return;
    root.querySelectorAll(".vuln-url").forEach((el) => {
      el.style.cursor = "pointer";
      el.addEventListener("click", (e) => {
        const vuln = e.currentTarget.closest(".vuln");
        if (!vuln) return;
        const checkbox = vuln.previousElementSibling;
        if (checkbox && checkbox.classList && checkbox.classList.contains("vuln-input")) {
          checkbox.checked = !checkbox.checked;
          checkbox.setAttribute("aria-expanded", checkbox.checked ? "true" : "false");
          // CSS : input.vuln-input:checked ~ .vuln .vuln-detail {display:block;} 에 의존
        }
      });
    });
  }

  App.popup.showInvictiAnalysis = function (rowId) {
    ensureDom();
    injectModalOverrides();

    const rows = (App.state && App.state.currentData) || [];
    const row = rows.find((r) => r.id === rowId);
    if (!row) { App.showError("행 데이터를 찾을 수 없습니다."); return; }

    // 원본 스타일은 전역(App.state.reportCss)으로 이미 주입됨.
    // 모달에는 HTML만 그대로 넣습니다.
    const html = row.invicti_analysis || '<div class="text-gray-400">표시할 내용이 없습니다.</div>';
    modalContent.innerHTML = html;

    // vuln-url 클릭 동작 복원
    wireInvictiInteractions(modalContent);

    // 열기
    openModal();

    // 닫기/다운로드 바인딩
    closeBtn && (closeBtn.onclick = closeModal);
    backdrop && (backdrop.onclick = closeModal);
    document.addEventListener("keydown", escHandler);

    downloadBtn && (downloadBtn.onclick = function () {
      const bodyHtml = modalContent.innerHTML;
      const cssText = (App.state && App.state.reportCss) ? `<style>${App.state.reportCss}</style>` : "";
      const doc = `<!doctype html><html lang="ko"><head><meta charset="utf-8">${cssText}</head><body>${bodyHtml}</body></html>`;
      const blob = new Blob([doc], { type: "text/html" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `${(row.invicti_report || "invicti_section")}.html`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    });
  };
})(window);
