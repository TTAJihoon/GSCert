(function (window, document) {
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  AppNS.gpt = AppNS.gpt || {};

  let modal, backdrop, shell, host, closeBtn;

  function escHandler(e) { if (e.key === "Escape") closeModal(); }

  /**
   * 모달 컴포넌트를 찾고, Shadow DOM 문제를 해결하기 위해 필요 시 초기화합니다.
   */
  function ensureModal() {
    if (!modal) modal = document.getElementById("modal");
    if (modal) {
      backdrop = modal.querySelector(".modal-backdrop");
      shell = modal.querySelector(".modal-shell");
      
      // --- Shadow DOM 충돌 해결 로직 ---
      let contentHost = modal.querySelector("#modalContent");
      if (contentHost && contentHost.shadowRoot) {
        // Invicti 팝업이 사용했던 Shadow DOM이 남아있으면, 해당 div를 새로 만들어서 교체합니다.
        console.log("Shadow DOM detected. Re-creating modal content area.");
        const newHost = document.createElement('div');
        newHost.id = 'modalContent';
        newHost.className = 'h-full overflow-auto p-3'; // 기존 클래스 유지
        contentHost.parentNode.replaceChild(newHost, contentHost);
        host = newHost;
      } else {
        host = contentHost;
      }
      // --- 로직 종료 ---

      closeBtn = modal.querySelector("#closeModal");
    }

    if (!modal || !backdrop || !shell || !host || !closeBtn) {
      console.error("Modal components could not be initialized.");
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

  /**
   * 팝업의 컨텐츠를 안전하게 표시하는 함수
   * @param {string} content - 표시할 HTML 콘텐츠
   */
  function displayContent(content) {
    if (!host) {
      console.error("Modal host element is not available to display content.");
      return;
    }
    host.innerHTML = content;
  }

  /**
   * GPT API를 호출하고 결과를 캐싱하며 팝업에 표시하는 비동기 함수
   * @param {string} rowId - 테이블 행의 고유 ID
   */
  async function getGptRecommendation(rowId) {
    if (!ensureModal()) return;

    const state = (window.SecurityApp && window.SecurityApp.state) || {};
    const row = (state.currentData || []).find(r => r.id === rowId);

    if (!row) {
      displayContent(`<div class="p-4 text-red-700 bg-red-100 border border-red-400 rounded-md"><strong>오류:</strong> 해당 행의 데이터를 찾을 수 없습니다.</div>`);
      openModal();
      return;
    }

    // 1. 캐시된 응답이 있으면 즉시 표시
    if (row.gpt_response) {
      const cachedContent = `
        <div class="p-3">
          <h3 class="font-bold text-lg mb-2 text-gray-800">🤖 GPT 추천 수정 방안 (저장된 답변)</h3>
          <pre class="whitespace-pre-wrap bg-gray-50 p-4 rounded-md text-sm text-gray-700 leading-relaxed font-sans">${row.gpt_response}</pre>
        </div>
      `;
      displayContent(cachedContent);
      openModal();
      return;
    }
    
    // 2. 캐시가 없을 경우: 프롬프트 유효성 검사
    if (!row.gpt_prompt) {
      displayContent(`<div class="p-4 text-red-700 bg-red-100 border border-red-400 rounded-md"><strong>오류:</strong> GPT에게 보낼 프롬프트 데이터가 없습니다.</div>`);
      openModal();
      return;
    }

    // 3. 로딩 상태 표시
    const loadingContent = `
      <div class="text-center py-12">
        <div class="inline-flex items-center px-4 py-2 font-semibold leading-6 text-sm shadow rounded-md text-gray-600 bg-white">
          <i class="fas fa-spinner fa-spin mr-3 text-sky-500"></i>
          GPT 추천 수정 방안을 생성중...
        </div>
      </div>
    `;
    displayContent(loadingContent);
    openModal();
    
    // 4. 백엔드 API 호출
    try {
      const response = await fetch('/security/gpt/recommend/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: row.gpt_prompt }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || `서버에서 오류가 발생했습니다: ${response.status}`);
      }
      
      // 5. 성공 시, 응답을 캐싱하고 <pre> 태그를 사용해 안전하게 표시
      row.gpt_response = result.response; 

      const successContent = `
        <div class="p-3">
          <h3 class="font-bold text-lg mb-2 text-gray-800">🤖 GPT 추천 수정 방안</h3>
          <pre class="whitespace-pre-wrap bg-gray-50 p-4 rounded-md text-sm text-gray-700 leading-relaxed font-sans">${result.response}</pre>
        </div>
      `;
      displayContent(successContent);

    } catch (error) {
      // 6. 실패 시, 에러 메시지 표시
      console.error('GPT 요청 실패:', error);
      const errorContent = `
        <div class="p-4 text-red-800 bg-red-50 border border-red-300 rounded-md">
          <strong class="font-bold">⚠️ 요청 실패</strong>
          <p class="mt-1 text-sm">${error.message}</p>
        </div>
      `;
      displayContent(errorContent);
    }
  }

  AppNS.gpt.getGptRecommendation = getGptRecommendation;

})(window, document);
