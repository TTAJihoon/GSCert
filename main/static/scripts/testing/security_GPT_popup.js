(function (window, document) {
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  
  window.App = window.App || {};
  window.App.popup = AppNS.popup;

  let modal, backdrop, shell, host, closeBtn;

  function ensureModal() {
    if (!modal) modal = document.getElementById("modal");
    if (modal) {
      backdrop  = backdrop  || modal.querySelector(".modal-backdrop");
      shell     = shell     || modal.querySelector(".modal-shell");
      host      = host      || modal.querySelector("#modalContent");
      closeBtn  = closeBtn  || modal.querySelector("#closeModal");
    }
    if (!modal || !backdrop || !shell || !host || !closeBtn) {
      console.warn("[gpt_popup] #modal 구조가 예상과 다릅니다.");
      return false;
    }

    shell.style.width = "80vw";
    shell.style.height = "80vh";
    host.style.overflow = "auto";
    host.style.padding = "12px";

    if (!modal._gptHandlersBound) {
      const close = () => closeModal();
      closeBtn.addEventListener("click", close);
      backdrop.addEventListener("click", close);
      document.addEventListener("keydown", function esc(e) {
        if (e.key === "Escape") { close(); } // esc 이벤트 리스너는 계속 유지되도록 수정
      });
      modal._gptHandlersBound = true;
    }
    return true;
  }

  function openModal() {
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
  }
  function closeModal() {
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    if (host) host.innerHTML = "";
  }

  // ====== GPT 추천 팝업 ======
  AppNS.popup.showGptRecommendation = function (rowId) {
    if (!ensureModal()) return;

    const state = (window.SecurityApp && window.SecurityApp.state) || {};
    const rows = state.currentData || [];
    const row = rows.find(r => r.id === rowId);

    if (!row || !row.vuln_detail_json) {
        console.error("해당 행의 상세 JSON 데이터를 찾을 수 없습니다.", rowId);
        host.textContent = "오류: 해당 결함의 상세 데이터를 찾을 수 없습니다.";
        openModal();
        return;
    }

    const vjson = row.vuln_detail_json;
    const headerText = vjson.header ? `
${vjson.header}
` : '';

    const prompt = `다음은 보안성 도구에서 발견된 ${headerText} 결함에 대한 데이터입니다.
아래 json 값을 확인하여 추천 수정 방안을 가볍게 제안해주세요.
${JSON.stringify(vjson, null, 2)}
`;

    // 텍스트만 표시 (Shadow DOM, 스타일 보정 등 불필요)
    host.innerHTML = "";
    const pre = document.createElement("pre");
    pre.style.whiteSpace = "pre-wrap";
    pre.style.wordBreak = "break-word";
    pre.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, monospace";
    pre.style.fontSize = "12px";
    pre.style.margin = "0";
    pre.textContent = prompt;
    host.appendChild(pre);

    openModal();
  };

})(window, document);
