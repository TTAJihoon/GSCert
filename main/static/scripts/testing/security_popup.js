(function (window) {
  // ---- 공개 API 네임스페이스(테이블/버튼에서 호출) ----
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  // ---- 상태/DOM ----
  let modal, backdrop, shell, host, closeBtn, downloadBtn;
  let shadowRoot = null;
  let disabledGlobalStyle = false;

  // 보정 CSS: 부트스트랩류 .row 음수 마진, 100vw 누수 등으로 깨짐 방지
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

  // 팝업 모달 마크업이 없으면 생성 (80vw/80vh, 내부 스크롤, 상단 타이틀 없음, 여백 컴팩트)
  function ensureModal() {
    modal = document.getElementById("modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "modal";
      modal.className = "fixed inset-0 z-50 hidden";
      modal.innerHTML = `
        <div class="modal-backdrop fixed inset-0 bg-gray-500 bg-opacity-50"></div>
        <div class="modal-shell absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2
                     bg-white rounded-lg shadow-xl overflow-hidden w-[80vw] h-[80vh]">
          <div id="modalContent" class="h-full overflow-auto p-3"></div>
          <div class="flex items-center justify-end gap-2 border-t px-3 py-2">
            <button type="button" id="downloadHtml"
                    class="inline-flex items-center rounded-md border px-3 py-1.5 text-sm bg-white hover:bg-gray-50">
              HTML 다운로드
            </button>
            <button type="button" id="closeModal"
                    class="inline-flex items-center rounded-md px-3 py-1.5 text-sm bg-blue-600 text-white hover:bg-blue-700">
              닫기
            </button>
          </div>
        </div>`;
      document.body.appendChild(modal);
    }
    // DOM 캐시
    backdrop   = modal.querySelector(".modal-backdrop");
    shell      = modal.querySelector(".modal-shell");
    host       = modal.querySelector("#modalContent");
    closeBtn   = modal.querySelector("#closeModal");
    downloadBtn= modal.querySelector("#downloadHtml");
    // 크기/스크롤 보증(보완)
    shell.style.width = "80vw";
    shell.style.height = "80vh";
    host.style.overflow = "auto";
    host.style.padding = "12px";
  }

  // 전역으로 주입된 원본 CSS 비활성화(팝업 동안만) → 레이아웃 누수 방지
  function disableGlobalInvictiStyle() {
    const style = document.getElementById("invicti-dynamic-styles");
    if (style && !style.disabled) { style.disabled = true; disabledGlobalStyle = true; }
  }
  function restoreGlobalInvictiStyle() {
    const style = document.getElementById("invicti-dynamic-styles");
    if (style && disabledGlobalStyle) style.disabled = false;
    disabledGlobalStyle = false;
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
    // Shadow DOM 정리
    if (shadowRoot) shadowRoot.innerHTML = "";
    restoreGlobalInvictiStyle();
  }
  function escHandler(e){ if (e.key === "Escape") closeModal(); }

  // ========= 상호작용 배선 =========
  function cssEscape(sel) {
    if (window.CSS && CSS.escape) return CSS.escape(sel);
    return (sel || "").replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  // .vuln-url: 바로 앞 형제 input.vuln-input 토글(펼치기/접기)
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
    // .vuln-more.row 클릭 시 전파 방지(레이아웃 깨짐 방지)
    root.querySelectorAll(".vuln-more.row").forEach((el) => {
      el.addEventListener("click", (e) => e.stopPropagation());
    });
  }

  // .vuln-tabs-nav: 버튼(active)에 따라 대응 패널(.vuln-tab.*)만 표시
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

  // ========= 다운로드 HTML 생성(원본 CSS + 보정 CSS + 배선 스크립트 내장) =========
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
              if(checkbox){ checkbox.checked = !checkbox.checked; checkbox.setAttribute("aria-expanded", checkbox.checked ? "true" : "false"); }
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

  // ========= 공개 API: 테이블의 "Invicti 분석" 버튼에서 호출 =========
  App.popup.showInvictiAnalysis = function (rowId) {
    ensureModal();

    // rows는 /security/invicti/parse/ 응답을 사용(이미 별도 스크립트에서 setData/주입) :contentReference[oaicite:3]{index=3}
    const rows = (App.state && App.state.currentData) || [];
    const row  = rows.find((r) => r.id === rowId);
    if (!row) { alert("행 데이터를 찾을 수 없습니다."); return; }

    // 팝업 동안 전역 원본 CSS 비활성화(누수 방지)
    disableGlobalInvictiStyle();

    // Shadow DOM 격리 렌더링
    if (!shadowRoot) shadowRoot = host.attachShadow({ mode: "open" });
    shadowRoot.innerHTML = "";

    const reportCss = (App.state && App.state.reportCss) ? App.state.reportCss : ""; // 원본 CSS 주입
    const styleOriginal = document.createElement("style");
    styleOriginal.textContent = reportCss;

    const styleFix = document.createElement("style");   // 레이아웃 보정
    styleFix.textContent = buildFixCSS();

    const container = document.createElement("div");    // 내용 컨테이너
    container.className = "invicti-root";
    container.innerHTML = row.invicti_analysis || '<div class="text-gray-400">표시할 내용이 없습니다.</div>';

    shadowRoot.appendChild(styleOriginal);
    shadowRoot.appendChild(styleFix);
    shadowRoot.appendChild(container);

    // 내부 상호작용 배선
    wireInteractions(shadowRoot);

    // 모달 열기
    openModal();

    // 버튼 배선
    closeBtn.onclick = closeModal;
    backdrop.onclick = closeModal;
    downloadBtn.onclick = function () {
      const html = buildDownloadHtml(container.innerHTML);
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
      const safe = (row.invicti_report || "invicti_section").replace(/[\\/:*?"<>|]/g, "_").slice(0, 80);
      a.download = `${safe}.html`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    };
  };

  function toSafeName(name, fallback) {
    const base = (name || fallback || "invicti_section").toString().trim();
    return base.replace(/[\\/:*?"<>|]/g, "_").slice(0, 120) || "invicti_section";
  }

  // 모든 행을 HTML로 만든 뒤 zip으로 묶어서 저장
  App.popup.downloadAllHtmlZip = async function () {
    try {
      if (typeof JSZip === "undefined") {
        alert("JSZip이 로드되지 않았습니다. security.html에 JSZip 스크립트 태그를 추가하세요.");
        return;
      }
      const rows = (App.state && App.state.currentData) || [];
      if (!rows.length) {
        alert("다운로드할 데이터가 없습니다. 먼저 HTML 파일을 업로드/분석하세요.");
        return;
      }

      const zip = new JSZip();
      const folder = zip.folder("invicti_html") || zip;

      for (const row of rows) {
        const bodyHtml = row.invicti_analysis || "<div>표시할 내용이 없습니다.</div>";
        const html = (typeof buildDownloadHtml === "function")
          ? buildDownloadHtml(bodyHtml)
          : bodyHtml; // 혹시 함수가 없으면 원문이라도 저장

        const fname = toSafeName(row.invicti_report || row.title || `row_${row.id}`, "invicti_section");
        folder.file(`${fname}.html`, html);
      }

      const now = new Date();
      const ts = [
        now.getFullYear(),
        String(now.getMonth() + 1).padStart(2, "0"),
        String(now.getDate()).padStart(2, "0"),
        String(now.getHours()).padStart(2, "0"),
        String(now.getMinutes()).padStart(2, "0")
      ].join("");

      const blob = await zip.generateAsync({ type: "blob" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `invicti_all_html_${ts}.zip`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    } catch (err) {
      console.error(err);
      alert("ZIP 생성 중 오류가 발생했습니다.");
    }
  };

  // 초기화(필요 시 다른 코드에서 호출 없이도 준비)
  document.addEventListener("DOMContentLoaded", ensureModal);
  document.addEventListener("DOMContentLoaded", () => {
    const btn = document.getElementById("downloadAllHtmlZip");
    if (btn) btn.addEventListener("click", App.popup.downloadAllHtmlZip);
  });
})(window);
