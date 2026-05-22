(function (window, document) {
  const AppNS = (window.SecurityApp = window.SecurityApp || {});
  AppNS.popup = AppNS.popup || {};
  AppNS.gpt = AppNS.gpt || {};

  let modal, backdrop, shell, host, closeBtn, downloadBtn;
  let typewriterTimer = null;
  let visibleText = "";
  let targetText = "";
  let keepStreamingCaret = false;
  let loadingTimer = null;
  let loadingStartedAt = 0;

  const TYPEWRITER_INTERVAL_MS = 18;
  const TYPEWRITER_BASE_STEP = 2;
  const TYPEWRITER_FAST_STEP = 6;
  const LOADING_INTERVAL_MS = 500;
  const LOADING_STEPS = [
    "보고서 내용을 읽는 중입니다.",
    "취약점 근거를 정리하는 중입니다.",
    "결함 여부를 판단하는 중입니다.",
    "수정 방안을 구성하는 중입니다.",
    "첫 응답을 기다리는 중입니다.",
  ];

  function escHandler(e) { if (e.key === "Escape") closeModal(); }

  // 모달 구성요소 확보 + Shadow DOM 충돌 처리
  function ensureModal() {
    if (!modal) modal = document.getElementById("modal");
    if (modal) {
      backdrop = modal.querySelector(".modal-backdrop");
      shell = modal.querySelector(".modal-shell");

      let contentHost = modal.querySelector("#modalContent");
      if (contentHost && contentHost.shadowRoot) {
        if (AppNS.popup && typeof AppNS.popup.releaseInvictiModal === "function") {
          AppNS.popup.releaseInvictiModal();
        }
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
      downloadBtn = modal.querySelector("#downloadHtml");
    }

    if (!modal || !backdrop || !shell || !host || !closeBtn) {
      console.error("Modal components could not be initialized.");
      return false;
    }

    if (AppNS.popup && typeof AppNS.popup.releaseInvictiModal === "function") {
      AppNS.popup.releaseInvictiModal();
    }
    closeBtn.onclick = closeModal;
    backdrop.onclick = closeModal;

    shell.style.width = "80vw";
    shell.style.height = "80vh";
    shell.style.display = "flex";
    shell.style.flexDirection = "column";
    host.className = "flex-1 min-h-0 overflow-auto p-3 gpt-modal";
    host.style.flex = "1 1 auto";
    host.style.minHeight = "0";
    host.style.height = "auto";
    host.style.overflow = "auto";
    configureMarkdownDownload({ enabled: false });
    return true;
  }

  function openModal() {
    if (!modal) return;
    modal.dataset.modalOwner = "gpt";
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
    document.addEventListener("keydown", escHandler);
  }

  function closeModal() {
    if (!modal) return;
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    resetTypewriter();
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

  function toSafeFileName(value, fallback = "ai_recommendation") {
    const base = String(value || fallback).trim() || fallback;
    return base.replace(/[\\/:*?"<>|]/g, "_").slice(0, 120) || fallback;
  }

  function getDownloadBaseName(row) {
    if (!row) return "ai_recommendation";
    return row.invicti_report || row.title || row.name || row.id || "ai_recommendation";
  }

  function configureMarkdownDownload({ rawText = "", fileName = "ai_recommendation", enabled = false } = {}) {
    if (!downloadBtn) return;
    downloadBtn.textContent = "MD 다운로드";
    downloadBtn.disabled = !enabled;
    downloadBtn.classList.toggle("opacity-50", !enabled);
    downloadBtn.classList.toggle("cursor-not-allowed", !enabled);
    downloadBtn.title = enabled
      ? "AI 추천 수정 방안을 Markdown 파일로 다운로드합니다."
      : "AI 추천 수정 방안이 생성되면 다운로드할 수 있습니다.";
    downloadBtn.onclick = function () {
      const body = host && host.querySelector(".gpt-body");
      const markdown = ((body && body.dataset.rawText) || rawText || "").trim();
      if (!markdown) {
        alert("다운로드할 AI 추천 수정 방안이 없습니다.");
        return;
      }
      const a = document.createElement("a");
      const safe = toSafeFileName(fileName);
      a.href = URL.createObjectURL(new Blob([markdown], { type: "text/markdown;charset=utf-8" }));
      a.download = `${safe}.md`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    };
  }

  function renderInlineMarkdown(value) {
    let html = escapeHtml(value);
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    html = html.replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>");
    html = html.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    return html;
  }

  function normalizeMarkdown(rawText) {
    let text = String(rawText || "").replace(/\r\n/g, "\n").trimStart();
    text = text.replace(/^\s*```(?:markdown|md|gfm)?\s*\n?/i, "");
    text = text.replace(/\n?```\s*$/i, "");
    return text;
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
    const lines = normalizeMarkdown(rawText).split("\n");
    const html = [];

    for (let i = 0; i < lines.length; i += 1) {
      const line = lines[i];
      const trimmed = line.trim();

      if (!trimmed) {
        continue;
      }

      if (/^```/.test(trimmed)) {
        const lang = trimmed.replace(/^```/, "").trim();
        const codeLines = [];
        i += 1;
        while (i < lines.length && !/^```/.test(lines[i].trim())) {
          codeLines.push(lines[i]);
          i += 1;
        }
        html.push(`<pre class="gpt-code-block"${lang ? ` data-lang="${escapeHtml(lang)}"` : ""}><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
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

      if (/^>\s?/.test(trimmed)) {
        const quotes = [];
        while (i < lines.length && /^>\s?/.test(lines[i].trim())) {
          quotes.push(lines[i].trim().replace(/^>\s?/, ""));
          i += 1;
        }
        i -= 1;
        html.push(`<blockquote>${quotes.map((item) => `<p>${renderInlineMarkdown(item)}</p>`).join("")}</blockquote>`);
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

      const paragraph = [trimmed];
      while (
        i + 1 < lines.length &&
        lines[i + 1].trim() &&
        !isMarkdownTable(lines, i + 1) &&
        !/^(#{1,4})\s+/.test(lines[i + 1].trim()) &&
        !/^[-*]\s+/.test(lines[i + 1].trim()) &&
        !/^\d+\.\s+/.test(lines[i + 1].trim()) &&
        !/^>\s?/.test(lines[i + 1].trim()) &&
        !/^```/.test(lines[i + 1].trim())
      ) {
        i += 1;
        paragraph.push(lines[i].trim());
      }
      html.push(`<p>${paragraph.map((item) => renderInlineMarkdown(item)).join("<br>")}</p>`);
    }

    return html.join("");
  }

  function extractAiErrorMessage(rawText) {
    const trimmed = String(rawText || "").trim();
    if (trimmed.startsWith("__GSCERT_AI_RATE_LIMIT__:")) {
      return trimmed.replace(/^__GSCERT_AI_RATE_LIMIT__:\s*/, "");
    }
    if (trimmed.startsWith("__GSCERT_AI_ERROR__:")) {
      return trimmed.replace(/^__GSCERT_AI_ERROR__:\s*/, "");
    }
    const bracketError = trimmed.match(/^\[(?:오류|\?\?)\]\s*([\s\S]*)$/);
    if (bracketError) {
      return bracketError[1] || "AI 추천 생성 중 오류가 발생했습니다.";
    }
    return "";
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
    resetTypewriter();
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
    targetText = rawText || "";
    keepStreamingCaret = Boolean(streaming);
    const body = host && host.querySelector(".gpt-body");
    if (body) body.dataset.rawText = targetText;

    if (!targetText) {
      visibleText = "";
      renderGptBodyFrame();
      return;
    }

    if (!typewriterTimer) {
      typewriterTimer = window.setInterval(renderGptBodyFrame, TYPEWRITER_INTERVAL_MS);
    }
    renderGptBodyFrame();
  }

  function resetTypewriter() {
    if (typewriterTimer) {
      window.clearInterval(typewriterTimer);
      typewriterTimer = null;
    }
    stopLoadingProgress();
    visibleText = "";
    targetText = "";
    keepStreamingCaret = false;
  }

  function buildLoadingHTML() {
    return `
      <div class="gpt-loading" aria-live="polite">
        <div class="gpt-loading-top">
          <span class="gpt-spinner" aria-hidden="true"></span>
          <div>
            <div class="gpt-loading-title">AI 추천 수정 방안을 생성 중입니다</div>
            <div class="gpt-loading-step" data-loading-step>보고서 내용을 읽는 중입니다.</div>
          </div>
        </div>
        <div class="gpt-loading-bar" aria-hidden="true"><span></span></div>
        <div class="gpt-loading-meta">
          <span data-loading-elapsed>0초 경과</span>
          <span>첫 응답을 받으면 바로 표시됩니다.</span>
        </div>
      </div>
    `;
  }

  function startLoadingProgress() {
    stopLoadingProgress();
    loadingStartedAt = Date.now();
    renderLoadingProgress();
    loadingTimer = window.setInterval(renderLoadingProgress, LOADING_INTERVAL_MS);
  }

  function stopLoadingProgress() {
    if (loadingTimer) {
      window.clearInterval(loadingTimer);
      loadingTimer = null;
    }
    loadingStartedAt = 0;
  }

  function renderLoadingProgress() {
    const body = host && host.querySelector(".gpt-body");
    if (!body || targetText) return;

    if (!body.querySelector(".gpt-loading")) {
      body.innerHTML = buildLoadingHTML();
    }

    const elapsedSeconds = loadingStartedAt
      ? Math.max(Math.floor((Date.now() - loadingStartedAt) / 1000), 0)
      : 0;
    const stepIndex = Math.min(
      Math.floor(elapsedSeconds / 4),
      LOADING_STEPS.length - 1
    );

    const step = body.querySelector("[data-loading-step]");
    const elapsed = body.querySelector("[data-loading-elapsed]");
    if (step) step.textContent = LOADING_STEPS[stepIndex];
    if (elapsed) elapsed.textContent = `${elapsedSeconds}초 경과`;
  }

  function renderGptBodyFrame() {
    const body = host && host.querySelector(".gpt-body");
    if (!body) return;

    if (targetText) {
      stopLoadingProgress();
    }

    const remaining = Math.max(targetText.length - visibleText.length, 0);
    if (remaining > 0) {
      const step = remaining > 120 ? TYPEWRITER_FAST_STEP : TYPEWRITER_BASE_STEP;
      visibleText = targetText.slice(0, visibleText.length + step);
    }

    const isTyping = visibleText.length < targetText.length;
    body.dataset.rawText = targetText;
    body.classList.toggle("gpt-streaming", keepStreamingCaret || isTyping);
    body.innerHTML = visibleText
      ? renderMarkdown(visibleText)
      : buildLoadingHTML();
    body.scrollTop = body.scrollHeight;

    if (!visibleText) {
      renderLoadingProgress();
    }

    if (!keepStreamingCaret && !isTyping && typewriterTimer) {
      window.clearInterval(typewriterTimer);
      typewriterTimer = null;
    }
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
      configureMarkdownDownload({ enabled: false });
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
      configureMarkdownDownload({
        rawText: row.gpt_response,
        fileName: getDownloadBaseName(row),
        enabled: true,
      });
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
      configureMarkdownDownload({ enabled: false });
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
    resetTypewriter();
    configureMarkdownDownload({
      fileName: getDownloadBaseName(row),
      enabled: false,
    });
    const loading = buildGptMessageHTML({
      title: "생성 중...",
      bodyHTML: buildLoadingHTML(),
    });
    displayContent(loading);
    openModal();
    startLoadingProgress();

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

      const errorMessage = extractAiErrorMessage(rawText);
      if (errorMessage) {
        throw new Error(errorMessage);
      }
      const trimmedText = rawText.trim();
      if (!trimmedText) {
        throw new Error("AI 추천 응답이 비어 있습니다. 잠시 후 다시 시도해 주세요.");
      }

      // 5) 성공: 캐시 + 표시
      row.gpt_response = rawText;
      configureMarkdownDownload({
        rawText,
        fileName: getDownloadBaseName(row),
        enabled: true,
      });
      const title = host && host.querySelector(".gpt-title");
      if (title) title.textContent = "🤖 AI 추천 수정 방안";
    } catch (error) {
      // 6) 실패 표시
      stopLoadingProgress();
      console.error("AI 요청 실패:", error);
      const err = buildGptMessageHTML({
        title: "⚠️ 요청 실패",
        bodyHTML: `<pre class="whitespace-pre-wrap">${error.message}</pre>`,
        variant: "error",
      });
      displayContent(err);
      configureMarkdownDownload({
        fileName: getDownloadBaseName(row),
        enabled: false,
      });
    }
  }

  AppNS.gpt.getGptRecommendation = getGptRecommendation;
  AppNS.gpt.releaseModal = function () {
    resetTypewriter();
    const contentHost = document.querySelector("#modalContent");
    if (contentHost && !contentHost.shadowRoot) {
      contentHost.innerHTML = "";
    }
  };

})(window, document);
