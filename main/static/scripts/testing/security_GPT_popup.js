(function (window, document) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  // ====== 기존 모달 재사용 ======
  let modal, backdrop, shell, host, closeBtn;
  let shadowRoot = null;           // 분석 팝업에서만 사용
  let disabledGlobalStyle = false; // 전역 Invicti CSS 임시 비활성화

  function ensureModal() {
    modal     = modal     || document.getElementById("modal");
    backdrop  = backdrop  || modal?.querySelector(".modal-backdrop");
    shell     = shell     || modal?.querySelector(".modal-shell");
    host      = host      || modal?.querySelector("#modalContent");
    closeBtn  = closeBtn  || modal?.querySelector("#closeModal");

    if (!modal || !backdrop || !shell || !host || !closeBtn) {
      console.warn("[popup_addon] #modal 구조가 예상과 다릅니다.");
      return false;
    }
    // 팝업 크기/스크롤/여백 (요구사항 고정)
    shell.style.width = "80vw";
    shell.style.height = "80vh";
    host.style.overflow = "auto";
    host.style.padding = "12px";

    // 닫기 핸들러는 중복 바인딩 방지
    if (!modal._popupAddonHandlers) {
      const close = () => closeModal();
      closeBtn.addEventListener("click", close);
      backdrop.addEventListener("click", close);
      document.addEventListener("keydown", function esc(e){
        if (e.key === "Escape") { close(); document.removeEventListener("keydown", esc); }
      });
      modal._popupAddonHandlers = true;
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
    // 분석 팝업에서만 쓰는 Shadow DOM/스타일 복구
    if (shadowRoot) shadowRoot.innerHTML = "";
    restoreGlobalInvictiStyle();
    // 내용 초기화
    host.innerHTML = "";
  }

  // ====== 분석 팝업에서: 전역 Invicti CSS 누수 방지 ======
  function disableGlobalInvictiStyle() {
    // 기존 코드가 페이지에 주입한 원본 스타일의 id를 사용
    const style = document.getElementById("invicti-dynamic-styles");
    if (style && !style.disabled) { style.disabled = true; disabledGlobalStyle = true; }
  }
  function restoreGlobalInvictiStyle() {
    const style = document.getElementById("invicti-dynamic-styles");
    if (style && disabledGlobalStyle) style.disabled = false;
    disabledGlobalStyle = false;
  }

  // ====== 레이아웃 보정 CSS (Shadow DOM에서만 사용) ======
  function buildFixCSS() {
    return `
      *, *::before, *::after { box-sizing: border-box; }
      html, body { width: 100%; height: 100%; }
      pre { white-space: pre-wrap; word-break: break-word; overflow: auto; }
      img, svg, canvas, video, iframe, table { max-width: 100%; height: auto; }
      .container, .container-fluid {
        margin-left: 0 !important; margin-right: 0 !important;
        padding-left: 8px !important; padding-right: 8px !important;
        max-width: 100% !important; width: 100% !important;
      }
      .row { margin-left: 0 !important; margin-right: 0 !important; }
      [class^="col-"], [class*=" col-"], .col {
        padding-left: 8px !important; padding-right: 8px !important; min-width: 0;
      }
      [style*="100vw"] { width: 100% !important; }
      input, button, select, textarea { max-width: 100%; }
    `;
  }

  // ====== Invicti 인터랙션 (토글/탭) ======
  function cssEscape(sel) {
    if (window.CSS && CSS.escape) return CSS.escape(sel);
    return (sel || "").replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }
  function wireToggleUrls(root) {
    function findToggleCheckbox(el){
      const vuln = el.closest(".vuln");
      if (!vuln) return null;
      const prev = vuln.previousElementSibling;
      if (prev && prev.classList && prev.classList.contains("vuln-input")) return prev;
      return vuln.parentElement ? vuln.parentElement.querySelector("input.vuln-input") : null;
    }
    root.querySelectorAll(".vuln-url").forEach((el) => {
      el.style.cursor = "pointer";
      el.addEventListener("click", (e) => {
        e.preventDefault(); e.stopPropagation();
        const checkbox = findToggleCheckbox(e.currentTarget);
        if (checkbox) {
          checkbox.checked = !checkbox.checked;
          checkbox.setAttribute("aria-expanded", checkbox.checked ? "true" : "false");
        }
      });
    });
    // 레이아웃 깨짐 방지(전파 차단)
    root.querySelectorAll(".vuln-more.row").forEach((el) => {
      el.addEventListener("click", (e) => e.stopPropagation());
    });
  }
  function wireTabs(root) {
    root.querySelectorAll(".vuln-tabs").forEach((tabs) => {
      const nav = tabs.querySelector(".vuln-tabs-nav"); if (!nav) return;
      const buttons = nav.querySelectorAll("button[role='tab']");
      const panels  = tabs.querySelectorAll(".vuln-tab");
      function show(btn){
        buttons.forEach((b)=>{ b.classList.remove("active"); b.setAttribute("aria-selected","false"); });
        btn.classList.add("active"); btn.setAttribute("aria-selected","true");
        const id = btn.getAttribute("aria-controls") || "";
        const panel = id ? tabs.querySelector("#" + cssEscape(id)) : null;
        panels.forEach((p)=>{ p.style.display = (p === panel) ? "" : "none"; });
      }
      const initial = Array.from(buttons).find(b => b.getAttribute("aria-selected")==="true") || buttons[0];
      if (initial) show(initial);
      buttons.forEach((b)=> b.addEventListener("click", (e)=>{ e.preventDefault(); show(b); }));
    });
  }
  function wireInteractions(root) { wireToggleUrls(root); wireTabs(root); }

  // ====== 공개 API: 분석 팝업 (원본 CSS 유지 + Shadow DOM) ======
  App.popup.showInvictiAnalysis = function (rowId) {
    if (!ensureModal()) return;

    const rows = (App.state && App.state.currentData) || [];
    const row  = rows.find((r) => r.id === rowId);
    if (!row) { alert("행 데이터를 찾을 수 없습니다."); return; }

    // 전역 Invicti 스타일 누수 차단
    disableGlobalInvictiStyle();

    // Shadow DOM으로 격리 렌더링
    if (!shadowRoot) shadowRoot = host.attachShadow({ mode: "open" });
    shadowRoot.innerHTML = "";

    const styleOriginal = document.createElement("style");
    styleOriginal.textContent = (App.state && App.state.reportCss) || "";

    const styleFix = document.createElement("style");
    styleFix.textContent = buildFixCSS();

    const container = document.createElement("div");
    container.className = "invicti-root";
    container.innerHTML = row.invicti_analysis || '<div class="text-gray-400">표시할 내용이 없습니다.</div>';

    shadowRoot.append(styleOriginal, styleFix, container);
    wireInteractions(shadowRoot);

    openModal();
  };

  // ====== 공개 API: GPT 추천 팝업 (멀티라인 텍스트) ======
  App.popup.showGptPrompt = function (rowId) {
    if (!ensureModal()) return;

    const rows = (App.state && App.state.currentData) || [];
    const row  = rows.find((r) => r.id === rowId);
    const rowJson   = row && row.vuln_detail_json ? row.vuln_detail_json : null;
    const globalJson= (App.state && App.state.firstVulnDetailJson) || null;
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
