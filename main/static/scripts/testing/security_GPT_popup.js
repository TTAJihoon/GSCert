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

  async function getGptRecommendation(rowId) {
    if (!ensureModal()) return;

    const state = (window.SecurityApp && window.SecurityApp.state) || {};
    const row = (state.currentData || []).find(r => r.id === rowId);

    if (!row || !row.gpt_prompt) {
      host.innerHTML = `<div class="p-4 text-red-700 bg-red-100 border border-red-400 rounded-md"><strong>오류:</strong> GPT에게 보낼 프롬프트 데이터가 없습니다.</div>`;
      openModal();
      return;
    }

    // 1. 팝업을 열고 로딩 상태와 이펙트를 표시
    host.innerHTML = `
      <div class="text-center py-12">
        <div class="inline-flex items-center px-4 py-2 font-semibold leading-6 text-sm shadow rounded-md text-gray-600 bg-white">
          <i class="fas fa-spinner fa-spin mr-3 text-sky-500"></i>
          GPT 추천 수정 방안을 생성중...
        </div>
      </div>
    `;
    openModal();
    
    // 2. 백엔드 API 호출
    try {
      const response = await fetch('/security/gpt/recommend/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ prompt: row.gpt_prompt }),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.error || `서버에서 오류가 발생했습니다: ${response.status}`);
      }
      
      // 3. 성공 시, 응답 내용을 팝업에 표시
      // 응답에 포함된 개행 문자를 <br> 태그로 변환하여 줄바꿈을 유지합니다.
      const formattedResponse = result.response.replace(/\n/g, '<br>');
      host.innerHTML = `
        <div class="p-3 prose max-w-none">
          <h3 class="font-bold text-lg mb-2 text-gray-800">🤖 GPT 추천 수정 방안</h3>
          <div class="bg-gray-50 p-4 rounded-md text-sm text-gray-700 leading-relaxed">${formattedResponse}</div>
        </div>
      `;

    } catch (error) {
      // 4. 실패 시, 에러 메시지를 팝업에 표시
      console.error('GPT 요청 실패:', error);
      host.innerHTML = `
        <div class="p-4 text-red-800 bg-red-50 border border-red-300 rounded-md">
          <strong class="font-bold">⚠️ 요청 실패</strong>
          <p class="mt-1 text-sm">${error.message}</p>
        </div>
      `;
    }
  }

  AppNS.gpt.getGptRecommendation = getGptRecommendation;

})(window, document);
