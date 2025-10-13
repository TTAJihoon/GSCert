(function (window, document) {
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  
  window.App = window.App || {};
  window.App.popup = AppNS.popup;

  // ====== 기존 모달 재사용 ======
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

    // 요구사항: 80vw x 80vh, 내부 스크롤, 여백 컴팩트
    shell.style.width = "80vw";
    shell.style.height = "80vh";
    host.style.overflow = "auto";
    host.style.padding = "12px";

    if (!modal._gptHandlersBound) {
      const close = () => closeModal();
      closeBtn.addEventListener("click", close);
      backdrop.addEventListener("click", close);
      document.addEventListener("keydown", function esc(e) {
        if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
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
  // 호출: App.popup.showGptRecommendation(rowId)
  AppNS.popup.showGptRecommendation = function (rowId) {
    if (!ensureModal()) return;

    const state = (window.App && window.App.state) || (window.SecurityApp && window.SecurityApp.state) || {};
    const rows = state.currentData || [];
    const row = rows.find(r => r.id === rowId);

    // 우선순위: 행 단위 JSON → 전역(firstVulnDetailJson)
    const rowJson = row && row.vuln_detail_json ? row.vuln_detail_json : null;
    const globalJson = state.firstVulnDetailJson || null;
    const vjson = rowJson || globalJson || {};

    const prompt = `다음은 Invicti 원본 HTML의 한 결함 섹션(snippet)에서 추출한 데이터입니다.
- 이 섹션 내부에 포함된 div.vuln-detail *하나*만 대상입니다.
- 결과는 JSON으로만 답해주세요. 불필요한 설명/코드는 넣지 마세요.

요구사항:
1) vuln-detail 안의 표를 "열 정의(columns)/행(rows)" 구조의 JSON으로 유지하세요.
2) "url"은 증명 URL 링크 주소만 값으로 넣어 주세요.
3) ".vuln-tab.vuln-req1-tab" 내부 pre(있으면 code) 텍스트를 "request"로 넣어 주세요.
4) ".vuln-tab.vuln-resp1-tab" 내부 pre(있으면 code) 텍스트를 "response"로 넣어 주세요.

아래는 제가 미리 추출해둔 값입니다(JSON 그대로 사용 가능).
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
