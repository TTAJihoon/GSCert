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
        newHost.className = "flex-1 min-h-0 overflow-auto p-3";
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

    shell.style.width = "80vw";
    shell.style.height = "80vh";
    shell.style.display = "flex";
    shell.style.flexDirection = "column";
    host.className = "flex-1 min-h-0 overflow-auto p-3 gpt-modal";
    host.style.flex = "1 1 auto";
    host.style.minHeight = "0";
    host.style.height = "auto";
    host.style.overflow = "auto";
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

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function renderInlineMarkdown(value) {
    let html = escapeHtml(value);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/\*([^*]+)\*/g, "<em>$1</em>");
    return html;
  }

  function isMarkdownTable(lines, index) {
    if (index + 1 >= lines.length) return false;
    const header = lines[index].trim();
    const separator = lines[index + 1].trim();
    return (
      header.startsWith("|") &&
      header.endsWith("|") &&
      /^\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(separator)
    );
  }

  function splitTableRow(line) {
    return line
      .trim()
      .replace(/^\|/, "")
      .replace(/\|$/, "")
      .split("|")
      .map((cell) => cell.trim());
  }

  function renderMarkdown(rawText) {
    const lines = String(rawText || "").replace(/\r\n/g, "\n").split("\n");
    const html = [];

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      const trimmed = line.trim();

      if (!trimmed) {
        continue;
      }

      if (isMarkdownTable(lines, i)) {
        const headers = splitTableRow(lines[i]);
        i += 2;
        const rows = [];
        while (i < lines.length && lines[i].trim().startsWith("|") && lines[i].trim().endsWith("|")) {
          rows.push(splitTableRow(lines[i]));
          i += 1;
        }
        i -= 1;

        html.push("<div class=\"gpt-table-wrap\"><table class=\"gpt-md-table\"><thead><tr>");
        headers.forEach((header) => html.push(`<th>${renderInlineMarkdown(header)}</th>`));
        html.push("</tr></thead><tbody>");
        rows.forEach((row) => {
          html.push("<tr>");
          row.forEach((cell) => html.push(`<td>${renderInlineMarkdown(cell)}</td>`));
          html.push("</tr>");
        });
        html.push("</tbody></table></div>");
        continue;
      }

      const heading = trimmed.match(/^(#{1,4})\s+(.+)$/);
      if (heading) {
        const level = Math.min(heading[1].length + 2, 6);
        html.push(`<h${level}>${renderInlineMarkdown(heading[2])}</h${level}>`);
        continue;
      }

      if (/^[-*]\s+/.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^[-*]\s+/.test(lines[i].trim())) {
          items.push(lines[i].trim().replace(/^[-*]\s+/, ""));
          i += 1;
        }
        i -= 1;
        html.push("<ul>");
        items.forEach((item) => html.push(`<li>${renderInlineMarkdown(item)}</li>`));
        html.push("</ul>");
        continue;
      }

      if (/^\d+\.\s+/.test(trimmed)) {
        const items = [];
        while (i < lines.length && /^\d+\.\s+/.test(lines[i].trim())) {
          items.push(lines[i].trim().replace(/^\d+\.\s+/, ""));
          i += 1;
        }
        i -= 1;
        html.push("<ol>");
        items.forEach((item) => html.push(`<li>${renderInlineMarkdown(item)}</li>`));
        html.push("</ol>");
        continue;
      }

      html.push(`<p>${renderInlineMarkdown(trimmed)}</p>`);
    }

    return html.join("");
  }

  // 공통 템플릿: AI 응답 말풍선 + 툴바(복사 버튼)
  function buildGptMessageHTML({ title = "AI 응답", bodyHTML = "", variant = "default" }) {
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
        const body = host.querySelector(".gpt-body");
        if (!body) return;
        const text = body.dataset.rawText || body.innerText;
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

  function updateGptMarkdown(rawText, { streaming = false } = {}) {
    const body = host && host.querySelector(".gpt-body");
    if (!body) return;
    body.dataset.rawText = rawText || "";
    body.classList.toggle("gpt-streaming", Boolean(streaming));
    body.innerHTML = rawText
      ? renderMarkdown(rawText)
      : `<p class="gpt-muted">AI 추천 수정 방안을 생성 중입니다...</p>`;
    body.scrollTop = body.scrollHeight;
  }

  /**
   * AI API를 호출하고 결과를 캐싱하며 팝업에 표시
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
        title: "🤖 AI 추천 수정 방안 (저장된 답변)",
        bodyHTML: renderMarkdown(row.gpt_response),
      });
      displayContent(html);
      const body = host && host.querySelector(".gpt-body");
      if (body) body.dataset.rawText = row.gpt_response;
      openModal();
      return;
    }

    // 2) 프롬프트 유효성 검사
    if (!row.gpt_prompt) {
      const html = buildGptMessageHTML({
        title: "오류",
        bodyHTML:
          `<pre class="whitespace-pre-wrap">AI에게 보낼 프롬프트 데이터가 없습니다.</pre>`,
        variant: "error",
      });
      displayContent(html);
      openModal();
      return;
    }

    // 3) 로딩 상태
    const loading = buildGptMessageHTML({
      title: "생성 중...",
      bodyHTML: `<p class="gpt-muted">AI 추천 수정 방안을 생성 중입니다...</p>`,
    });
    displayContent(loading);
    openModal();

    // 4) 백엔드 호출
    try {
      const response = await fetch("/security/gpt/recommend/stream/", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: row.gpt_prompt }),
      });

      if (!response.ok) {
        let message = `서버에서 오류가 발생했습니다: ${response.status}`;
        try {
          const result = await response.json();
          message = result.error || message;
        } catch {
          const text = await response.text();
          message = text || message;
        }
        throw new Error(message);
      }
      if (!response.body) {
        throw new Error("브라우저가 스트리밍 응답을 지원하지 않습니다.");
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let rawText = "";
      updateGptMarkdown(rawText, { streaming: true });

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        rawText += decoder.decode(value, { stream: true });
        updateGptMarkdown(rawText, { streaming: true });
      }
      rawText += decoder.decode();
      updateGptMarkdown(rawText, { streaming: false });

      // 5) 성공: 캐시 + 표시
      row.gpt_response = rawText;
      const title = host && host.querySelector(".gpt-title");
      if (title) title.textContent = "🤖 AI 추천 수정 방안";
    } catch (error) {
      // 6) 실패 표시
      console.error("AI 요청 실패:", error);
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
