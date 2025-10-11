(function (window) {
  const App = (window.SecurityApp = window.SecurityApp || {});
  App.popup = App.popup || {};

  let modal, host, closeBtn, backdrop, downloadBtn;
  let shadowRoot = null;
  let disabledGlobalStyle = false;

  function $$() {
    modal      = modal      || document.getElementById("modal");
    host       = host       || document.getElementById("modalContent");
    closeBtn   = closeBtn   || document.getElementById("closeModal");
    downloadBtn= downloadBtn|| document.getElementById("downloadHtml");
    backdrop   = backdrop   || document.querySelector("#modal .modal-backdrop");
  }

  function disableGlobalInvictiStyle() {
    const style = document.getElementById("invicti-dynamic-styles"); // 주입 위치
    if (style && !style.disabled) {
      style.disabled = true; // 전역 누수 차단
      disabledGlobalStyle = true;
    }
  }
  function restoreGlobalInvictiStyle() {
    const style = document.getElementById("invicti-dynamic-styles");
    if (style && disabledGlobalStyle) {
      style.disabled = false;
    }
    disabledGlobalStyle = false;
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
    document.removeEventListener("keydown", escHandler);
    // Shadow DOM 정리
    if (shadowRoot) { shadowRoot.innerHTML = ""; }
    restoreGlobalInvictiStyle();
  }
  function escHandler(e){ if (e.key === "Escape") closeModal(); }

  // ====== 상호작용 배선 (ShadowRoot 내부) ======
  function cssEscape(sel) {
    if (window.CSS && CSS.escape) return CSS.escape(sel);
    return (sel || "").replace(/[^a-zA-Z0-9_-]/g, "\\$&");
  }

  function buildFixCSS() {
    return `
    /* 레이아웃 깨짐 방지 기본 */
    *, *::before, *::after { box-sizing: border-box; }
    html, body { width: 100%; height: 100%; }
    img, svg, canvas, video, iframe, table { max-width: 100%; height: auto; }
    pre { white-space: pre-wrap; word-break: break-word; overflow: auto; }

    /* Invicti 리포트 쪽 그리드/컨테이너 보정 (부트스트랩류 음수 마진/너비 누수 차단) */
    .container, .container-fluid {
      margin-left: 0 !important;
      margin-right: 0 !important;
      padding-left: 8px !important;
      padding-right: 8px !important;
      max-width: 100% !important;
      width: 100% !important;
    }
    .row {
      margin-left: 0 !important;
      margin-right: 0 !important;
    }
    [class^="col-"], [class*=" col-"], .col {
      padding-left: 8px !important;
      padding-right: 8px !important;
      min-width: 0; /* 긴 코드블록 등으로 인한 col 폭 깨짐 방지 */
    }

    /* 100vw 사용 폭이 Shadow DOM 컨테이너를 밀어내는 현상 방지 */
    [style*="100vw"] { width: 100% !important; }

    /* 폼류 요소들 간격 과도 방지 */
    input, button, select, textarea { max-width: 100%; }
  `;
}
  
  // .vuln-url 클릭 → 직전 input.vuln-input 체크 토글
  function wireToggleUrls(root) {
    root.querySelectorAll(".vuln-url").forEach((el) => {
      el.style.cursor = "pointer";
      el.addEventListener("click", (e) => {
        // a/href 이동 등 방지
        e.preventDefault();
        e.stopPropagation();

        const vuln = e.currentTarget.closest(".vuln");
        if (!vuln) return;
        const checkbox = vuln.previousElementSibling;
        if (checkbox && checkbox.classList && checkbox.classList.contains("vuln-input")) {
          checkbox.checked = !checkbox.checked;
          checkbox.setAttribute("aria-expanded", checkbox.checked ? "true" : "false");
        }
      });
    });

    // (신규) .vuln-more.row 클릭 시 전파 방지: 다른 토글과 간섭 방지
    root.querySelectorAll(".vuln-more.row").forEach((el) => {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
      });
    });
  }

  // .vuln-tabs-nav 버튼 클릭 → 해당 패널만 표시
  function wireTabs(root) {
    root.querySelectorAll(".vuln-tabs").forEach((tabs) => {
      const nav = tabs.querySelector(".vuln-tabs-nav");
      if (!nav) return;

      const buttons = nav.querySelectorAll("button[role='tab']");
      const panels  = tabs.querySelectorAll(".vuln-tab");

      function showPanelByButton(btn) {
        // 버튼 상태
        buttons.forEach(b => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");

        // 패널 표시/숨김
        const targetId = btn.getAttribute("aria-controls") || "";
        const panel = tabs.querySelector("#" + cssEscape(targetId));
        panels.forEach(p => { p.style.display = (p === panel) ? "" : "none"; });
      }

      // 초기 표시: [aria-selected="true"]가 가리키는 패널
      const initial = Array.from(buttons).find(b => b.getAttribute("aria-selected") === "true") || buttons[0];
      if (initial) showPanelByButton(initial);

      // 클릭 배선
      buttons.forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.preventDefault();
          showPanelByButton(btn);
        });
      });
    });
  }

  // 팝업 내부 DOM에 각종 상호작용 배선
  function wireInteractions(root) {
    wireToggleUrls(root);
    wireTabs(root);
  }

  // ====== 다운로드용 HTML 생성 (원본 CSS + 내장 스크립트 포함) ======
  function buildDownloadHtml(bodyHtml) {
    const css = (App.state && App.state.reportCss) ? App.state.reportCss : "";
    const fixCss = buildFixCSS(); // 위에서 추가한 함수 재사용

    const inlineScript = `
    (function(){
      function cssEscape(s){ if(window.CSS&&CSS.escape) return CSS.escape(s); return (s||"").replace(/[^a-zA-Z0-9_-]/g,"\\\\$&"); }

      function findToggleCheckbox(el){
        var vuln = el.closest(".vuln");
        if(!vuln) return null;
        var prev = vuln.previousElementSibling;
        if (prev && prev.classList && prev.classList.contains("vuln-input")) return prev;
        var candidate = vuln.parentElement ? vuln.parentElement.querySelector("input.vuln-input") : null;
        return candidate || null;
      }

      function wireToggleUrls(root) {
        root.querySelectorAll(".vuln-url").forEach(function(el){
          el.addEventListener("click", function(e){
            e.preventDefault();
            e.stopPropagation();
            var checkbox = findToggleCheckbox(e.currentTarget);
            if(checkbox){
              checkbox.checked = !checkbox.checked;
              checkbox.setAttribute("aria-expanded", checkbox.checked ? "true":"false");
            }
          });
        });
        // .vuln-more.row 클릭 시 전파 방지
        root.querySelectorAll(".vuln-more.row").forEach(function(el){
          el.addEventListener("click", function(e){ e.stopPropagation(); });
        });
      }

      function wireTabs(root) {
        root.querySelectorAll(".vuln-tabs").forEach(function(tabs){
          var nav = tabs.querySelector(".vuln-tabs-nav");
          if(!nav) return;
          var buttons = nav.querySelectorAll("button[role='tab']");
          var panels  = tabs.querySelectorAll(".vuln-tab");

          function show(btn){
            buttons.forEach(function(b){ b.classList.remove("active"); b.setAttribute("aria-selected","false"); });
            btn.classList.add("active"); btn.setAttribute("aria-selected","true");

            var id = btn.getAttribute("aria-controls") || "";
            var panel = id ? tabs.querySelector("#"+cssEscape(id)) : null;
            panels.forEach(function(p){ p.style.display = (p===panel) ? "" : "none"; });
          }

          var initBtn = Array.prototype.find.call(buttons, function(b){ return b.getAttribute("aria-selected")==="true"; }) || buttons[0];
          if(initBtn) show(initBtn);

          buttons.forEach(function(b){
            b.addEventListener("click", function(e){ e.preventDefault(); show(b); });
          });
        });
      }

      function init(){
        var root = document;
        wireToggleUrls(root);
        wireTabs(root);
      }
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
      else init();
    })();
  `;

    return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Invicti 분석 스니펫</title>
<style>${css}</style>
<style>${fixCss}</style>
</head>
<body>
${bodyHtml}
<script>${inlineScript}</script>
</body>
</html>`;
}

  App.popup.showInvictiAnalysis = function (rowId) {
    $$();

    const rows = (App.state && App.state.currentData) || [];
    const row = rows.find((r) => r.id === rowId);
    if (!row) { App.showError("행 데이터를 찾을 수 없습니다."); return; }

    disableGlobalInvictiStyle();

    if (!host) return;
    if (!shadowRoot) shadowRoot = host.attachShadow({ mode: "open" });
    shadowRoot.innerHTML = "";

    const cssText = (App.state && App.state.reportCss) ? App.state.reportCss : "";

    // 원본 CSS
    const styleOriginal = document.createElement("style");
    styleOriginal.textContent = cssText;

    // (신규) 보정 CSS
    const styleFix = document.createElement("style");
    styleFix.textContent = buildFixCSS();

    const container = document.createElement("div");
    container.className = "invicti-root";
    container.innerHTML = row.invicti_analysis || '<div class="text-gray-400">표시할 내용이 없습니다.</div>';

    shadowRoot.appendChild(styleOriginal);
    shadowRoot.appendChild(styleFix);          // ← 보정 CSS 주입
    shadowRoot.appendChild(container);

    wireInteractions(shadowRoot);

    openModal();

    closeBtn && (closeBtn.onclick = closeModal);
    backdrop && (backdrop.onclick = closeModal);
    downloadBtn && (downloadBtn.onclick = function () {
      const html = buildDownloadHtml(container.innerHTML);  // 아래 2번 패치한 함수
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([html], { type: "text/html;charset=utf-8" }));
      const safe = (row.invicti_report || "invicti_section").replace(/[\\/:*?"<>|]/g, "_").slice(0, 80);
      a.download = `${safe}.html`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(a.href);
      a.remove();
    });
  };

  // 초기 공통 이벤트
  document.addEventListener("DOMContentLoaded", () => {
    $$();
  });
})(window);
