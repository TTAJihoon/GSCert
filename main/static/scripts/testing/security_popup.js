(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  // ---------- 공용 모달 ----------
  let modal, backdrop, shell, host, closeBtn, downloadBtn;
  let shadowRoot = null;
  let disabledGlobalStyle = false;

  function ensureModal() {
    modal = document.getElementById("modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "modal";
      modal.className = "fixed inset-0 z-50 hidden";
      modal.innerHTML = `
        <div class="modal-backdrop fixed inset-0 bg-black bg-opacity-50"></div>
        <div class="modal-shell absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
                     bg-white rounded-lg shadow-xl overflow-hidden w-[80vw] h-[80vh]">
          <div id="modalContent" class="h-full overflow-auto p-3"></div>
          <div class="flex items-center justify-end gap-2 border-t px-3 py-2">
            <button type="button" id="downloadHtml"
                    class="inline-flex items-center rounded-md border px-3 py-1.5 text-sm bg-white hover:bg-gray-50">
              다운로드
            </button>
            <button type="button" id="closeModal"
                    class="inline-flex items-center rounded-md px-3 py-1.5 text-sm bg-blue-600 text-white hover:bg-blue-700">
              닫기
            </button>
          </div>
        </div>`;
      document.body.appendChild(modal);
    }
    backdrop   = modal.querySelector(".modal-backdrop");
    shell      = modal.querySelector(".modal-shell");
    host       = modal.querySelector("#modalContent");
    closeBtn   = modal.querySelector("#closeModal");
    downloadBtn= modal.querySelector("#downloadHtml");

    shell.style.width = "80vw";
    shell.style.height = "80vh";
    host.style.overflow = "auto";
    host.style.padding = "12px";
  }

  function openModal() {
    modal.classList.remove("hidden");
    document.body.classList.add("overflow-hidden");
    document.addEventListener("keydown", escHandler);
  }
  function closeModal() {
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
    document.removeEventListener("keydown", escHandler);
    if (shadowRoot) shadowRoot.innerHTML = "";
    restoreGlobalInvictiStyle();
  }
  function escHandler(e){ if (e.key === "Escape") closeModal(); }

  function disableGlobalInvictiStyle() {
    const style = document.getElementById("invicti-dynamic-styles");
    if (style && !style.disabled) { style.disabled = true; disabledGlobalStyle = true; }
  }
  function restoreGlobalInvictiStyle() {
    const style = document.getElementById("invicti-dynamic-styles");
    if (style && disabledGlobalStyle) style.disabled = false;
    disabledGlobalStyle = false;
  }

  // ---------- Invicti 분석(HTML)용: 스타일/인터랙션 ----------
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
        e.preventDefault();
        e.stopPropagation();
        const checkbox = findToggleCheckbox(e.currentTarget);
        if (checkbox) {
          checkbox.checked = !checkbox.checked;
          checkbox.setAttribute("aria-expanded", checkbox.checked ? "true" : "false");
        }
      });
    });
    root.querySelectorAll(".vuln-more.row").forEach((el) => {
      el.addEventListener("click", (e) => e.stopPropagation());
    });
  }

  function wireTabs(root) {
    root.querySelectorAll(".vuln-tabs").forEach((tabs) => {
      const nav = tabs.querySelector(".vuln-tabs-nav");
      if (!nav) return;
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

      buttons.forEach((b)=>{
        b.addEventListener("click", (e)=>{ e.preventDefault(); show(b); });
      });
    });
  }

  function wireInteractions(root) {
    wireToggleUrls(root);
    wireTabs(root);
  }

  // 다운로드용: 원본 CSS + 보정 CSS + 인터랙션 스크립트 포함 HTML 생성
  function buildDownloadHtml(bodyHtml) {
    const reportCss = (App.state && App.state.reportCss) ? App.state.reportCss : "";
    const fixCss = buildFixCSS();
    const inlineScript = `
      (function(){
        function cssEscape(s){ if(window.CSS&&CSS.escape) return CSS.escape(s); return (s||"").replace(/[^a-zA-Z0-9_-]/g,"\\\\$&"); }
        function findToggleCheckbox(el){
          var vuln = el.closest(".vuln"); if(!vuln) return null;
          var prev = vuln.previousElementSibling;
          if(prev && prev.classList && prev.classList.contains("vuln-input")) return prev;
          return vuln.parentElement ? vuln.parentElement.querySelector("input.vuln-input") : null;
        }
        function wireToggleUrls(root){
          root.querySelectorAll(".vuln-url").forEach(function(el){
            el.addEventListener("click", function(e){
              e.preventDefault(); e.stopPropagation();
              var checkbox = findToggleCheckbox(e.currentTarget);
              if(checkbox){
                checkbox.checked = !checkbox.checked;
                checkbox.setAttribute("aria-expanded", checkbox.checked ? "true" : "false");
              }
            });
          });
          root.querySelectorAll(".vuln-more.row").forEach(function(el){
            el.addEventListener("click", function(e){ e.stopPropagation(); });
          });
        }
        function wireTabs(root){
          root.querySelectorAll(".vuln-tabs").forEach(function(tabs){
            var nav = tabs.querySelector(".vuln-tabs-nav"); if(!nav) return;
            var buttons = nav.querySelectorAll("button[role='tab']");
            var panels  = tabs.querySelectorAll(".vuln-tab");
            function show(btn){
              buttons.forEach(function(b){ b.classList.remove("active"); b.setAttribute("aria-selected","false"); });
              btn.classList.add("active"); btn.setAttribute("aria-selected","true");
              var id = btn.getAttribute("aria-controls") || "";
              var panel = id ? tabs.querySelector("#"+cssEscape(id)) : null;
              panels.forEach(function(p){ p.style.display = (p===panel) ? "" : "none"; });
            }
            var initial = Array.prototype.find.call(buttons, function(b){ return b.getAttribute("aria-selected")==="true"; }) || buttons[0];
            if(initial) show(initial);
            buttons.forEach(function(b){ b.addEventListener("click", function(e){ e.preventDefault(); show(b); }); });
          });
        }
        function init(){ var root=document; wireToggleUrls(root); wireTabs(root); }
        if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init); else init();
      })();
    `;
    return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8">
<title>Invicti 분석 스니펫</title>
<style>${reportCss}</style>
<style>${fixCss}</style>
</head><body>
${bodyHtml}
<script>${inlineScript}</script>
</body></html>`;
  }

  // ---------- 공개 API ----------
  // 1) Invicti 분석 팝업: HTML 미리보기(Shadow DOM)
  App.popup.showInvictiAnalysis = function (rowId) {
    ensureModal();

    const rows = (App.state && App.state.currentData) || [];
    const row  = rows.find((r) => r.id === rowId);
    if (!row) { alert("행 데이터를 찾을 수 없습니다."); return; }

    // 전역 원본 CSS 누수 방지
    disableGlobalInvictiStyle();

    if (!shadowRoot) shadowRoot = host.attachShadow({ mode: "open" });
    shadowRoot.innerHTML = "";

    const reportCss = (App.state && App.state.reportCss) ? App.state.reportCss : "";
    const styleOriginal = document.createElement("style");
    styleOriginal.textContent = reportCss;

    const styleFix = document.createElement("style");
    styleFix.textContent = buildFixCSS();

    const container = document.createElement("div");
    container.className = "invicti-root";
    container.innerHTML = row.invicti_analysis || '<div class="text-gray-400">표시할 내용이 없습니다.</div>';

    shadowRoot.appendChild(styleOriginal);
    shadowRoot.appendChild(styleFix);
    shadowRoot.appendChild(container);

    wireInteractions(shadowRoot);

    // 버튼
    downloadBtn.onclick = function () {
      const html = buildDownloadHtml(container.innerHTML);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
      const safe = (row.invicti_report || "invicti_section").replace(/[\\/:*?"<>|]/g, "_").slice(0, 100);
      a.download = `${safe}.html`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    };
    closeBtn.onclick = closeModal;
    backdrop.onclick = closeModal;

    openModal();
  };

  // 2) GPT 추천 팝업: 프롬프트(템플릿 리터럴) 표시
  App.popup.showGptPrompt = function (rowId) {
    ensureModal();

    const rows = (App.state && App.state.currentData) || [];
    const row  = rows.find((r) => r.id === rowId);
    const rowJson = row && row.vuln_detail_json ? row.vuln_detail_json : null;
    const globalJson = (App.state && App.state.firstVulnDetailJson) || null;
    const vjson = rowJson || globalJson || {};

    // 텍스트 프롬프트 (멀티라인 템플릿)
    const prompt = `다음은 보안성 결함을 찾아주는 도구의 결과 데이터(json)입니다.
다음 json 값에 대한 추천 수정 방안을 간략히 알려주세요.

아래는 json 값입니다.
${JSON.stringify(vjson, null, 2)}
`;

    // Shadow DOM 불필요 → 일반 텍스트 렌더
    host.innerHTML = "";
    const pre = document.createElement("pre");
    pre.style.whiteSpace = "pre-wrap";
    pre.style.wordBreak = "break-word";
    pre.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, monospace";
    pre.style.fontSize = "12px";
    pre.style.margin = "0";
    pre.textContent = prompt;
    host.appendChild(pre);

    downloadBtn.onclick = function () {
      const blob = new Blob([prompt], { type: "text/plain;charset=utf-8" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const base = (row && (row.invicti_report || row.title)) || "gpt_prompt";
      const safe = base.replace(/[\\/:*?"<>|]/g, "_").slice(0, 100);
      a.download = `${safe}.txt`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    };
    closeBtn.onclick = closeModal;
    backdrop.onclick = closeModal;

    openModal();
  };

  document.addEventListener("DOMContentLoaded", ensureModal);
})(window);
