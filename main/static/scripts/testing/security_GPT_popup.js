(function (window, document) {
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  AppNS.gpt = AppNS.gpt || {};

  let modal, backdrop, shell, host, closeBtn;

  function escHandler(e) { if (e.key === "Escape") closeModal(); }

  // 모달 구성요소 확보 + Shadow DOM 충돌 처리
  function ensureModal() {
    if (!modal) modal = document.getElementById("modal");
    if (modal) {
      backdrop = modal.querySelector(".modal-backdrop");
      shell = modal.querySelector(".modal-shell");

      let contentHost = modal.querySelector("#modalContent");
      if (contentHost && contentHost.shadowRoot) {
        console.log("Shadow DOM detected. Re-creating modal content area.");
        const newHost = document.createElement("div");
        newHost.id = "modalContent";
        newHost.className = "h-full overflow-auto p-3";
        contentHost.parentNode.replaceChild(newHost, contentHost);
        host = newHost;
      } else {
        host = contentHost;
      }

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

    // ChatGPT 스타일 컨테이너 클래스 부여(없으면 추가)
    host.classList && host.classList.add("gpt-modal");
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

  // 공통 템플릿: ChatGPT 느낌 말풍선 + 툴바(복사 버튼)
  function buildGptMessageHTML({ title = "GPT 응답", bodyHTML = "", variant = "default" }) {
    const isError = variant === "error";
    return `
      <div class="gpt-msg${isError ? " gpt-error" : ""}">
        <div class="gpt-avatar" aria-hidden="true">🤖</div>
        <div class="gpt-bubble">
          <div class="gpt-toolbar">
            <div class="gpt-title">${title}</div>
            <div class="gpt-actions">
              <button class="gpt-btn" data-action="copy" type="button">복사</button>
            </div>
          </div>
          <div class="gpt-body">
            ${bodyHTML}
          </div>
        </div>
      </div>
    `;
  }

  // 콘텐츠 표시 + 복사 버튼 바인딩
  function displayContent(content) {
    if (!host) {
      console.error("Modal host element is not available to display content.");
      return;
    }
    host.innerHTML = content;

    // 복사 버튼 핸들러
    host.querySelectorAll(".gpt-btn[data-action='copy']").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const pre = host.querySelector(".gpt-body pre");
        if (!pre) return;
        const text = pre.innerText;
        try {
          await navigator.clipboard.writeText(text);
          btn.textContent = "복사됨";
        } catch {
          btn.textContent = "실패";
        } finally {
          setTimeout(() => (btn.textContent = "복사"), 1200);
        }
      });
    });
  }

  /**
   * GPT API를 호출하고 결과를 캐싱하며 팝업에 표시
   * @param {string} rowId - 테이블 행의 고유 ID
   */
  async function getGptRecommendation(rowId) {
    if (!ensureModal()) return;

    const state = (window.SecurityApp && window.SecurityApp.state) || {};
    const row = (state.currentData || []).find((r) => r.id === rowId);

    if (!row) {
      const html = buildGptMessageHTML({
        title: "오류",
        bodyHTML:
          `<pre class="whitespace-pre-wrap">해당 행의 데이터를 찾을 수 없습니다.</pre>`,
        variant: "error",
      });
      displayContent(html);
      openModal();
      return;
    }

    // 1) 캐시 존재 시 즉시 표시
    if (row.gpt_response) {
      const html = buildGptMessageHTML({
        title: "🤖 GPT 추천 수정 방안 (저장된 답변)",
        bodyHTML: `<pre class="whitespace-pre-wrap">${row.gpt_response}</pre>`,
      });
      displayContent(html);
      openModal();
      return;
    }

    // 2) 프롬프트 유효성 검사
    if (!row.gpt_prompt) {
      const html = buildGptMessageHTML({
        title: "오류",
        bodyHTML:
          `<pre class="whitespace-pre-wrap">GPT에게 보낼 프롬프트 데이터가 없습니다.</pre>`,
        variant: "error",
      });
      displayContent(html);
      openModal();
      return;
    }

    // 3) 로딩 상태
    const loading = buildGptMessageHTML({
      title: "생성 중...",
      bodyHTML: `
        <div class="text-center py-6">
          <div class="inline-flex items-center px-4 py-2 font-semibold leading-6 text-sm rounded-md text-gray-600 bg-white border border-gray-200">
            <i class="fas fa-spinner fa-spin mr-2"></i> GPT 추천 수정 방안을 생성 중입니다...
          </div>
        </div>
      `,
    });
    displayContent(loading);
    openModal();

    // 4) 백엔드 호출
    try {
      const response = await fetch("/security/gpt/recommend/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: row.gpt_prompt }),
      });

      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || `서버에서 오류가 발생했습니다: ${response.status}`);
      }

      // 5) 성공: 캐시 + 표시
      row.gpt_response = result.response;
      const success = buildGptMessageHTML({
        title: "🤖 GPT 추천 수정 방안",
        bodyHTML: `<pre class="whitespace-pre-wrap">${result.response}</pre>`,
      });
      displayContent(success);
    } catch (error) {
      // 6) 실패 표시
      console.error("GPT 요청 실패:", error);
      const err = buildGptMessageHTML({
        title: "⚠️ 요청 실패",
        bodyHTML: `<pre class="whitespace-pre-wrap">${error.message}</pre>`,
        variant: "error",
      });
      displayContent(err);
    }
  }

  AppNS.gpt.getGptRecommendation = getGptRecommendation;

})(window, document);
