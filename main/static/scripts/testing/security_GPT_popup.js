(function (window, document) {
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  AppNS.gpt = AppNS.gpt || {};

  let modal, backdrop, shell, host, closeBtn;

  function escHandler(e) { if (e.key === "Escape") closeModal(); }

  function ensureModal() {
    if (!modal) modal = document.getElementById("modal");
    if (modal) {
      backdrop  = modal.querySelector(".modal-backdrop");
      shell     = modal.querySelector(".modal-shell");
      host      = modal.querySelector("#modalContent");
      closeBtn  = modal.querySelector("#closeModal");
    }
    if (!modal || !backdrop || !shell || !host || !closeBtn) {
        console.error("Modal components not found");
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
   * GPT 답변을 화면에 표시하는 함수
   * @param {string} content - 표시할 HTML 또는 텍스트 콘텐츠
   */
  function displayContent(content) {
    if (!host) return;
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

    // 1. 캐시된 응답 확인
    if (row.gpt_response) {
      const content = `
        <div class="p-3 prose max-w-none">
          <h3 class="font-bold text-lg mb-2 text-gray-800">🤖 GPT 추천 수정 방안 (캐시됨)</h3>
          <pre class="whitespace-pre-wrap bg-gray-50 p-4 rounded-md text-sm text-gray-700 leading-relaxed">${row.gpt_response}</pre>
        </div>
      `;
      displayContent(content);
      openModal();
      return; // 캐시된 데이터 표시 후 함수 종료
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
      console.log("Response from server:", result); // 서버 응답을 콘솔에 기록

      if (!response.ok) {
        throw new Error(result.error || `서버에서 오류가 발생했습니다: ${response.status}`);
      }
      
      // 5. 성공 시, 응답을 캐싱하고 팝업에 표시
      row.gpt_response = result.response; // 답변을 행 데이터에 저장 (캐싱)

      const successContent = `
        <div class="p-3 prose max-w-none">
          <h3 class="font-bold text-lg mb-2 text-gray-800">🤖 GPT 추천 수정 방안</h3>
          <pre class="whitespace-pre-wrap bg-gray-50 p-4 rounded-md text-sm text-gray-700 leading-relaxed">${result.response}</pre>
        </div>
      `;
      displayContent(successContent);

    } catch (error) {
      // 6. 실패 시, 에러 메시지를 팝업에 표시
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
