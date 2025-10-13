(function (window, document) {
  // 네임스페이스를 안전하게 생성합니다.
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  AppNS.gpt = AppNS.gpt || {};

  window.App = window.App || {};
  window.App.popup = AppNS.popup;
  window.App.gpt = AppNS.gpt;

  // ====== 모달 관련 변수 및 함수 ======
  let modal, backdrop, shell, host, closeBtn;

  function escHandler(e) {
    if (e.key === "Escape") closeModal();
  }

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
    if (!modal._gptHandlersBound) {
      closeBtn.addEventListener("click", closeModal);
      backdrop.addEventListener("click", closeModal);
      modal._gptHandlersBound = true;
    }
    return true;
  }

  function openModal() {
    if (!modal) return;
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
    document.addEventListener("keydown", escHandler);
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    if (host) host.innerHTML = "";
    document.removeEventListener("keydown", escHandler);
  }

  // ====== GPT 추천 팝업 표시 함수 ======
  function showGptRecommendation(rowId) {
    if (!ensureModal()) return;

    const state = (window.SecurityApp && window.SecurityApp.state) || {};
    const row = (state.currentData || []).find(r => r.id === rowId);

    if (!row || !row.vuln_detail_json) {
        console.error("해당 행의 상세 JSON 데이터를 찾을 수 없습니다.", rowId);
        host.textContent = "오류: 해당 결함의 상세 데이터를 찾을 수 없습니다.";
        openModal();
        return;
    }

    const vjson = row.vuln_detail_json;
    const headerText = vjson.header ? `
- 아래는 해당 결함의 헤더(div.vuln-desc-header) 정보입니다.
${vjson.header}
` : '';

    const prompt = `(생략)...`; // 이전과 동일한 프롬프트 내용

    host.innerHTML = "";
    const pre = document.createElement("pre");
    pre.style.cssText = "white-space: pre-wrap; word-break: break-word; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; margin: 0;";
    pre.textContent = prompt;
    host.appendChild(pre);
    openModal();
  }

  // ====== '추천' 버튼 클릭 핸들러 ======
  /**
   * '추천' 버튼 클릭 시 호출되어 팝업 표시 함수를 실행합니다.
   * @param {string} rowId - 테이블 행의 고유 ID
   */
  function getGptRecommendation(rowId) {
    showGptRecommendation(rowId);
  }

  // 외부에 함수를 노출시켜 HTML의 onclick 속성에서 찾을 수 있도록 합니다.
  AppNS.popup.showGptRecommendation = showGptRecommendation;
  AppNS.gpt.getGptRecommendation = getGptRecommendation;

})(window, document);
