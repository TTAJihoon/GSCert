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

  // .vuln-url 클릭 → 직전 input.vuln-input 체크 토글
  function wireToggleUrls(root) {
    root.querySelectorAll(".vuln-url").forEach((el) => {
      el.style.cursor = "pointer";
      el.addEventListener("click", (e) => {
        const vuln = e.currentTarget.closest(".vuln");
        if (!vuln) return;
        const checkbox = vuln.previousElementSibling;
        if (checkbox && checkbox.classList && checkbox.classList.contains("vuln-input")) {
          checkbox.checked = !checkbox.checked;
          checkbox.setAttribute("aria-expanded", checkbox.checked ? "true" : "false");
        }
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
  const inlineScript = `
    (function(){
      function cssEscape(s){ if(window.CSS&&CSS.escape) return CSS.escape(s); return (s||"").replace(/[^a-zA-Z0-9_-]/g,"\\\\$&"); }

      function findToggleCheckbox(el){
        // 1) 원본 구조: .vuln-url 포함 .vuln 의 '직전 형제'가 input.vuln-input
        var vuln = el.closest(".vuln");
        if(!vuln) return null;
        var prev = vuln.previousElementSibling;
        if (prev && prev.classList && prev.classList.contains("vuln-input")) return prev;

        // 2) 예외: 구조가 달라졌을 경우, 같은 컨테이너 내 가장 가까운 input.vuln-input 탐색
        var candidate = vuln.parentElement ? vuln.parentElement.querySelector("input.vuln-input") : null;
        return candidate || null;
      }

      function wireToggleUrls(root) {
        root.querySelectorAll(".vuln-url").forEach(function(el){
          // a 태그일 수 있으므로 기본 이동 방지
          el.addEventListener("click", function(e){
            e.preventDefault();
            e.stopPropagation();
            var checkbox = findToggleCheckbox(e.currentTarget);
            if(checkbox){
              checkbox.checked = !checkbox.checked;
              checkbox.setAttribute("aria-expanded", checkbox.checked ? "true":"false");
            }
          });
          // 커서 표시 (원본에 없으면)
          if (!el.style.cursor) el.style.cursor = "pointer";
        });
      }

      function wireTabs(root) {
        root.querySelectorAll(".vuln-tabs").forEach(function(tabs){
          var nav = tabs.querySelector(".vuln-tabs-nav");
          if(!nav) return;
          var buttons = nav.querySelectorAll("button[role='tab']");
          var panels  = tabs.querySelectorAll(".vuln-tab");

          function show(btn){
            // 버튼 상태
            buttons.forEach(function(b){ b.classList.remove("active"); b.setAttribute("aria-selected","false"); });
            btn.classList.add("active"); btn.setAttribute("aria-selected","true");

            // 패널 표시/숨김 (원본 CSS가 없더라도 보장되도록 명시적 display 제어)
            var id = btn.getAttribute("aria-controls") || "";
            var panel = id ? tabs.querySelector("#"+cssEscape(id)) : null;
            panels.forEach(function(p){ p.style.display = (p===panel) ? "" : "none"; });
          }

          // 초기 활성 탭
          var initBtn = Array.prototype.find.call(buttons, function(b){ return b.getAttribute("aria-selected")==="true"; }) || buttons[0];
          if(initBtn) show(initBtn);

          // 클릭 이벤트
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
      if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
      } else {
        init();
      }
    })();
  `;

  return `<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<title>Invicti 분석 스니펫</title>
<style>${css}</style>
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

    // 전역 스타일 비활성화(누수 방지)
    disableGlobalInvictiStyle();

    // Shadow DOM 준비
    if (!host) return;
    if (!shadowRoot) shadowRoot = host.attachShadow({ mode: "open" });
    shadowRoot.innerHTML = ""; // 초기화

    const cssText = (App.state && App.state.reportCss) ? App.state.reportCss : "";
    const styleEl = document.createElement("style");
    styleEl.textContent = cssText;

    const container = document.createElement("div");
    container.className = "invicti-root";              // 단순 래퍼
    container.innerHTML = row.invicti_analysis || '<div class="text-gray-400">표시할 내용이 없습니다.</div>';

    shadowRoot.appendChild(styleEl);
    shadowRoot.appendChild(container);

    // 내부 인터랙션 연결
    wireInteractions(shadowRoot);

    // 팝업 열기
    openModal();

    // 버튼 배선
    closeBtn && (closeBtn.onclick = closeModal);
    backdrop && (backdrop.onclick = closeModal);
    downloadBtn && (downloadBtn.onclick = function () {
      const html = buildDownloadHtml(container.innerHTML);
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
